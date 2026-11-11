"""
app/main.py
API Gateway y vistas por rol de la Plataforma de Interoperabilidad Clínica.

- Autenticación JWT y permisos por rol en la API (no solo en la pantalla).
- Cuatro vistas: Paciente, Admisionista, Médico y Reporte de HC (con tablero de estado).
- Regla de oro: ninguna vista habla con las bases de las sedes.
    * Lecturas: consulta unificada (db/consulta_unificada.py) a través de esta API.
    * Escrituras: se envían al HSB (/hsb/json), que valida, traduce, publica en FHIR y
      guarda en la sede, sea PostgreSQL o MongoDB.
- Auditoría encadenada por hash en la base central; cada escritura devuelve su sello.
"""

import os
import json
import time
import hashlib
import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import autenticar_usuario, crear_token_jwt, USUARIOS_PRUEBA
from app import usuarios
from app.rbac import obtener_usuario_autenticado, requerir_roles, validar_acceso_historia_clinica
from app.audit import (registrar_evento_auditoria, verificar_cadena_auditoria, adulterar_evento_para_prueba,
                       obtener_ultimos_eventos, estado_auditoria, obtener_cadena)
from app.dashboard import obtener_estado_general_plataforma
from concurrent.futures import ThreadPoolExecutor

from db.consulta_unificada import consultar_historia_unificada
from db.repositorio import todos_los_repositorios
from fhir.normalizer import construir_bundle
from traductor.catalogo_57 import CAMPOS_57, SEDES
from traductor.dominios import DOMINIOS
from traductor.traductor import tabla_57_legible

app = FastAPI(title="API Gateway - Interoperabilidad Clínica",
              description="Gateway con RBAC, vistas por rol, consulta unificada y auditoría encadenada",
              version="2.0.0")

os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["DOMINIOS"] = DOMINIOS
templates.env.globals["SEDES"] = SEDES
HSB_URL = os.getenv("HSB_URL", "http://localhost:8001")


def render(nombre: str, contexto: dict, status_code: int = 200):
    request = contexto.get("request")
    try:
        return templates.TemplateResponse(request=request, name=nombre, context=contexto, status_code=status_code)
    except TypeError:
        return templates.TemplateResponse(nombre, contexto, status_code=status_code)


@app.exception_handler(FastAPIHTTPException)
async def manejar_http(request: Request, exc: FastAPIHTTPException):
    """En las vistas HTML, 401 lleva al login y 403 muestra un aviso; en /api responde JSON."""
    es_html = "text/html" in request.headers.get("accept", "") and not request.url.path.startswith("/api")
    if es_html and exc.status_code == 401:
        return RedirectResponse(url="/login?error=Inicie+sesión+para+continuar", status_code=303)
    if exc.detail == "CAMBIO_CLAVE_REQUERIDO":
        if es_html:
            return RedirectResponse(url="/cambiar-clave", status_code=303)
        return JSONResponse(status_code=403, content={"detail": "Debe cambiar su contraseña temporal",
                                                      "motivos": ["Debe cambiar su contraseña temporal"]})
    if es_html and exc.status_code == 403:
        return render("error.html", {"request": request, "codigo": 403, "titulo": "Acceso denegado",
                                     "mensaje": "Su perfil no tiene permiso para abrir esta sección.",
                                     "nota": "El intento quedó registrado en la auditoría del sistema."}, status_code=403)
    if es_html and exc.status_code == 404:
        return render("error.html", {"request": request, "codigo": 404, "titulo": "No encontrado",
                                     "mensaje": str(exc.detail), "nota": None}, status_code=404)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.on_event("startup")
def inicio():
    try:
        usuarios.inicializar()
    except Exception as e:  # la base central puede tardar en aceptar conexiones
        print(f"Aviso: no se pudieron inicializar las cuentas todavía ({e})")
    registrar_evento_auditoria("SISTEMA_INICIADO", "SISTEMA", "sistema", "plataforma_clinica", "EXITOSO",
                               {"mensaje": "API Gateway iniciada"})


def _ahora() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _enviar_al_hsb(registro: Dict[str, Any], sede: int, tipo: str) -> Dict[str, Any]:
    """Toda escritura clínica entra por el bus (validación, FHIR, idempotencia, reintentos)."""
    try:
        resp = httpx.post(f"{HSB_URL}/hsb/json", params={"sede": sede},
                          json={"tipo_mensaje": tipo, "registro": registro}, timeout=20.0)
        datos = resp.json()
        datos["http"] = resp.status_code
        return datos
    except Exception as e:
        return {"estado": "error", "motivo": f"HSB no disponible: {e.__class__.__name__}", "http": 503}


# ── Autenticación ─────────────────────────────────────────────────────────

@app.get("/", response_class=RedirectResponse)
def raiz():
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
def vista_login(request: Request, error: Optional[str] = None):
    return render("login.html", {"request": request, "error": error})


@app.post("/auth/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    usr = autenticar_usuario(username, password)
    if not usr:
        registrar_evento_auditoria("LOGIN", username, "desconocido", "/auth/login", "FALLIDO",
                                   {"motivo": "Credenciales inválidas"})
        return render("login.html", {"request": request, "error": "Credenciales inválidas."}, status_code=401)
    token = _token_de(usr)
    registrar_evento_auditoria("LOGIN", usr["username"], usr["rol"], "/auth/login", "EXITOSO", {"sede_id": usr["sede_id"]})
    destino = {"paciente": "/paciente", "admisionista": "/admision", "medico": "/medico", "auditor": "/panel",
               "administrador": "/panel"}
    url = "/cambiar-clave" if usr.get("debe_cambiar_clave") else destino.get(usr["rol"], "/reporte")
    resp = RedirectResponse(url=url, status_code=303)
    resp.set_cookie(key="access_token", value=token, httponly=True, samesite="lax", max_age=3600)
    return resp


def _token_de(usr: Dict[str, Any]) -> str:
    return crear_token_jwt({k: usr.get(k) for k in ("username", "rol", "nombre_completo", "documento_id", "sede_id",
                                                     "debe_cambiar_clave")} | {"sub": usr["username"]})


DESTINO_ROL = {"paciente": "/paciente", "admisionista": "/admision", "medico": "/medico", "auditor": "/panel",
               "administrador": "/panel"}


@app.get("/cambiar-clave", response_class=HTMLResponse)
def vista_cambiar_clave(request: Request, usuario: Dict[str, Any] = Depends(obtener_usuario_autenticado)):
    return render("cambiar_clave.html", {"request": request, "usuario": usuario, "error": None,
                                         "obligatorio": bool(usuario.get("debe_cambiar_clave"))})


@app.post("/cambiar-clave", response_class=HTMLResponse)
def guardar_cambio_clave(request: Request, actual: str = Form(...), nueva: str = Form(...), confirmar: str = Form(...),
                         usuario: Dict[str, Any] = Depends(obtener_usuario_autenticado)):
    obligatorio = bool(usuario.get("debe_cambiar_clave"))
    try:
        if nueva != confirmar:
            raise usuarios.ErrorUsuario(["la confirmación no coincide con la nueva contraseña"])
        actualizado = usuarios.cambiar_clave(usuario["username"], actual, nueva)
    except usuarios.ErrorUsuario as e:
        registrar_evento_auditoria("CAMBIO_CLAVE", usuario["username"], usuario["rol"], "/cambiar-clave", "FALLIDO",
                                   {"motivos": e.motivos})
        return render("cambiar_clave.html", {"request": request, "usuario": usuario, "obligatorio": obligatorio,
                                             "error": "; ".join(e.motivos).capitalize()}, status_code=422)
    registrar_evento_auditoria("CAMBIO_CLAVE", usuario["username"], usuario["rol"], "/cambiar-clave", "EXITOSO", {})
    resp = RedirectResponse(url=DESTINO_ROL.get(actualizado["rol"], "/reporte"), status_code=303)
    resp.set_cookie(key="access_token", value=_token_de(actualizado), httponly=True, samesite="lax", max_age=3600)
    return resp


@app.get("/auth/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("access_token")
    return resp


# ── 1. Vista Paciente ─────────────────────────────────────────────────────

@app.get("/paciente", response_class=HTMLResponse)
def vista_paciente(request: Request, usuario: Dict[str, Any] = Depends(requerir_roles(["paciente"]))):
    doc = usuario["documento_id"]
    historia = consultar_historia_unificada(doc)
    registrar_evento_auditoria("CONSULTA_HC", usuario["username"], "paciente", f"/historia/{doc}", "EXITOSO",
                               {"documento_id": doc, "consulta_propia": True})
    accesos = obtener_ultimos_eventos(100, documento=doc)
    return render("paciente.html", {"request": request, "usuario": usuario, "historia": historia, "accesos": accesos})


# ── 2. Vista Admisionista ─────────────────────────────────────────────────

def _resumen_admision(doc: str) -> Dict[str, Any]:
    """Lo que puede ver admisión: dónde existe el paciente y sus datos de identificación. Sin diagnósticos."""
    h = consultar_historia_unificada(doc)
    atenciones = [{k: at.get(k) for k in ("numero_visita", "sede_id", "sede_origen", "motor_origen", "fecha_ingreso",
                                          "entorno_atencion", "clasificacion_triage", "estado", "entidad_salud")}
                  for at in h["atenciones"]]
    paciente = {c.clave: (h["paciente"] or {}).get(c.clave) for c in CAMPOS_57 if c.contenedor == "usuario"}
    paciente.update({k: (h["paciente"] or {}).get(k) for k in ("nombres", "apellidos")})
    return {"documento_id": doc, "encontrado": bool(h["paciente"]), "paciente": paciente if h["paciente"] else None,
            "sedes_con_registros": h["sedes_con_registros"], "sedes_no_disponibles": h["sedes_no_disponibles"],
            "inconsistencias": h["inconsistencias_entre_sedes"], "atenciones": atenciones,
            "reporte_completo": h["reporte_completo"]}


def _mensajes_bus(limite: int = 25) -> Dict[str, Any]:
    try:
        return httpx.get(f"{HSB_URL}/hsb/mensajes", params={"limite": limite}, timeout=5.0).json()
    except Exception as e:
        return {"mensajes": [], "error": f"HSB no disponible ({e.__class__.__name__})"}


@app.get("/admision", response_class=HTMLResponse)
def vista_admision(request: Request, buscar_doc: Optional[str] = None,
                   usuario: Dict[str, Any] = Depends(requerir_roles(["admisionista"]))):
    resultado = _resumen_admision(buscar_doc.strip()) if buscar_doc else None
    if buscar_doc:
        registrar_evento_auditoria("BUSQUEDA_PACIENTE", usuario["username"], "admisionista",
                                   f"/admision/{buscar_doc}", "EXITOSO", {"documento_id": buscar_doc})
    return render("admision.html", {"request": request, "usuario": usuario, "buscar_doc": buscar_doc,
                                    "resultado": resultado, "bus": _mensajes_bus(), "respuesta_hsb": None})


def _admitir(form: Dict[str, Any], usuario: Dict[str, Any], sede_defecto: int) -> Dict[str, Any]:
    """
    Registro/admisión común a la vista de Admisión y al Panel de administración:
    arma el registro con claves canónicas, lo envía al HSB y deja el evento de auditoría (sello).
    """
    form = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items() if v not in (None, "")}
    sede = int(form.pop("sede_id", sede_defecto) or sede_defecto)
    ahora = _ahora()
    form.setdefault("fecha_ingreso", ahora)
    if form.get("clasificacion_triage"):
        form.setdefault("fecha_triage", ahora)
    if form.get("nombres") or form.get("apellidos"):
        form["nombre_completo"] = " ".join(x for x in (form.get("nombres"), form.get("apellidos")) if x)
    form["voluntad_anticipada"] = "S" if form.get("voluntad_anticipada") else None
    form["numero_visita"] = f"V-S{sede}-ADM-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
    form["sede_id"] = sede
    cie10 = str(form.pop("cie10_codigo", "") or "").strip().upper()
    descripcion = form.pop("descripcion_cie10", None)
    if cie10:
        form["diagnosticos"] = [{"cie10_codigo": cie10, "descripcion_cie10": descripcion, "rol": "INGRESO",
                                 "tipo_diagnostico": "01", "fecha_diagnostico": ahora[:10]}]

    resp = _enviar_al_hsb({k: v for k, v in form.items() if v is not None}, sede, "ADMISION")
    ev = registrar_evento_auditoria("APERTURA_ATENCION", usuario["username"], usuario["rol"],
                                    f"/atenciones/{form['numero_visita']}",
                                    "EXITOSO" if resp.get("estado") in ("entregado", "reintentando") else "FALLIDO",
                                    {"documento_id": form.get("documento_id"), "sede_id": sede,
                                     "estado_hsb": resp.get("estado")})
    resp["sello"] = ev.get("hash_propio")
    resp["sede"] = sede
    resp["motor"] = SEDES[sede]["motor"]
    resp.setdefault("documento", form.get("documento_id"))
    if resp.get("estado") in ("entregado", "reintentando", "duplicado") and form.get("documento_id"):
        try:
            cuenta = usuarios.cuenta_paciente(form["documento_id"], form.get("nombre_completo") or form["documento_id"],
                                              sede, usuario)
            resp["cuenta_paciente"] = cuenta
            if cuenta["creada"]:
                registrar_evento_auditoria("USUARIO_CREADO", usuario["username"], usuario["rol"],
                                           f"/usuarios/{cuenta['username']}", "EXITOSO",
                                           {"documento_id": form["documento_id"], "rol_creado": "paciente",
                                            "origen": "ADMISION", "sede_id": sede})
        except Exception as e:
            resp["cuenta_paciente"] = {"username": form["documento_id"], "creada": False, "clave_temporal": None,
                                       "error": str(e)[:200]}
    return resp


@app.post("/admision/registrar", response_class=HTMLResponse)
async def registrar_admision(request: Request, usuario: Dict[str, Any] = Depends(requerir_roles(["admisionista"]))):
    """Registra o actualiza al paciente y abre la atención con triage. Viaja al HSB como JSON."""
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    resp = _admitir(form, usuario, usuario.get("sede_id") or 1)
    doc = resp.get("documento")
    return render("admision.html", {"request": request, "usuario": usuario, "buscar_doc": doc,
                                    "resultado": _resumen_admision(doc) if doc else None,
                                    "bus": _mensajes_bus(), "respuesta_hsb": resp})


# ── 3. Vista Médico ───────────────────────────────────────────────────────

@app.get("/medico", response_class=HTMLResponse)
def vista_medico(request: Request, buscar_doc: Optional[str] = None, sello: Optional[str] = None,
                 estado: Optional[str] = None, motivo: Optional[str] = None,
                 usuario: Dict[str, Any] = Depends(requerir_roles(["medico"]))):
    historia = None
    if buscar_doc:
        historia = consultar_historia_unificada(buscar_doc.strip())
        registrar_evento_auditoria("CONSULTA_HC", usuario["username"], "medico", f"/historia/{buscar_doc}", "EXITOSO",
                                   {"documento_id": buscar_doc, "total_atenciones": historia["total_atenciones_encontradas"]})
    return render("medico.html", {"request": request, "usuario": usuario, "buscar_doc": buscar_doc,
                                  "historia": historia, "sello": sello, "estado_escritura": estado,
                                  "motivo_escritura": motivo})


def _base_escritura(doc: str, visita: str) -> Dict[str, Any]:
    """Usuario y atención existentes (de la sede que corresponda) para escribir sobre ellos."""
    h = consultar_historia_unificada(doc)
    at = next((a for a in h["atenciones"] if a.get("numero_visita") == visita), None)
    if not h["paciente"] or not at:
        raise HTTPException(status_code=404, detail=f"La atención {visita} no existe para el paciente {doc} "
                                                    "o su sede no está disponible")
    usuario = {k: v for k, v in h["paciente"].items() if k not in ("fhir_patient_id",)}
    atencion = {k: v for k, v in at.items()
                if k not in ("tecnologias", "diagnosticos", "egreso", "sede_origen", "motor_origen", "fhir_encounter_id")}
    return {"usuario": usuario, "atencion": atencion, "sede": int(at["sede_id"]), "egreso_actual": at.get("egreso") or {},
            "diagnosticos": at.get("diagnosticos") or [], "tecnologias": at.get("tecnologias") or []}


def _escritura_medica(usuario: Dict[str, Any], doc: str, visita: str, accion: str,
                      parte: Dict[str, Any], detalle: Dict[str, Any]) -> RedirectResponse:
    base = _base_escritura(doc, visita)
    # El evento de auditoría va primero: su hash es el sello que se devuelve y se guarda
    ev = registrar_evento_auditoria("ESCRITURA_HC", usuario["username"], "medico", f"/atenciones/{visita}",
                                    "EXITOSO", {"documento_id": doc, "accion": accion, "sede_id": base["sede"],
                                                "profesional": usuario["documento_id"], **detalle})
    sello = ev.get("hash_propio") or ""
    # FHIR PUT reemplaza el recurso completo: se envía la atención entera (lo que ya había + lo nuevo)
    # para que el Encounter en HAPI no pierda diagnósticos, fórmulas ni egreso anteriores.
    registro = {"usuario": base["usuario"], "atencion": base["atencion"],
                "diagnosticos": base["diagnosticos"] + parte.get("diagnosticos", []),
                "tecnologias": base["tecnologias"] + parte.get("tecnologias", [])}
    if base["egreso_actual"] or "egreso" in parte:
        registro["egreso"] = {**base["egreso_actual"], **parte.get("egreso", {})}
    if "egreso" in parte:
        registro["egreso"]["sello_hash"] = sello
    resp = _enviar_al_hsb(registro, base["sede"], f"MEDICO_{accion}")
    motivo = "; ".join(resp.get("motivos") or []) or resp.get("motivo") or ""
    if resp.get("estado") not in ("entregado", "reintentando", "duplicado"):
        registrar_evento_auditoria("ESCRITURA_HC", usuario["username"], "medico", f"/atenciones/{visita}",
                                   "FALLIDO", {"documento_id": doc, "accion": accion, "motivo": motivo[:300]})
    q = httpx.QueryParams({"buscar_doc": doc, "sello": sello, "estado": resp.get("estado", "error"), "motivo": motivo[:300]})
    return RedirectResponse(url=f"/medico?{q}", status_code=303)


@app.post("/medico/diagnostico")
def registrar_diagnostico(documento_id: str = Form(...), numero_visita: str = Form(...),
                          cie10_codigo: str = Form(...), descripcion_cie10: str = Form(""),
                          rol: str = Form("INGRESO"), tipo_diagnostico: str = Form("01"),
                          usuario: Dict[str, Any] = Depends(requerir_roles(["medico"]))):
    dx = {"cie10_codigo": cie10_codigo.strip().upper(), "descripcion_cie10": descripcion_cie10.strip() or None,
          "rol": rol, "tipo_diagnostico": tipo_diagnostico, "fecha_diagnostico": _ahora()[:10]}
    return _escritura_medica(usuario, documento_id, numero_visita, "DIAGNOSTICO", {"diagnosticos": [dx]},
                             {"cie10": dx["cie10_codigo"], "rol": rol})


@app.post("/medico/formula")
async def registrar_formula(request: Request, usuario: Dict[str, Any] = Depends(requerir_roles(["medico"]))):
    form = {k: v.strip() for k, v in (await request.form()).items() if isinstance(v, str) and v.strip()}
    doc, visita = form.pop("documento_id"), form.pop("numero_visita")
    med = {k: form.get(k) for k in ("descripcion_medicamento", "dosis", "via_administracion", "frecuencia",
                                     "dias_tratamiento", "unidades_aplicadas", "finalidad_tecnologia") if form.get(k)}
    med["tipo"] = "MEDICAMENTO"
    med["id_personal_salud"] = usuario["documento_id"]   # campo 31: siempre quien firma, nunca otro
    return _escritura_medica(usuario, doc, visita, "FORMULA", {"tecnologias": [med]},
                             {"medicamento": med.get("descripcion_medicamento")})


@app.post("/medico/egreso")
async def registrar_egreso(request: Request, usuario: Dict[str, Any] = Depends(requerir_roles(["medico"]))):
    form = {k: v.strip() for k, v in (await request.form()).items() if isinstance(v, str) and v.strip()}
    doc, visita = form.pop("documento_id"), form.pop("numero_visita")
    egreso = {k: form.get(k) for k in ("fecha_salida", "condicion_salida", "diagnostico_muerte", "tipo_incapacidad",
                                        "dias_incapacidad", "dias_lic_maternidad", "alergias",
                                        "antecedentes_familiares", "riesgos_ocupacionales") if form.get(k)}
    egreso.setdefault("fecha_salida", _ahora())
    egreso["responsable_egreso"] = usuario["nombre_completo"]   # campo 50: quien firma
    parte: Dict[str, Any] = {"egreso": egreso}
    if form.get("diagnostico_egreso"):
        parte["diagnosticos"] = [{"cie10_codigo": form["diagnostico_egreso"].upper(), "rol": "EGRESO",
                                  "tipo_diagnostico": "01", "fecha_diagnostico": egreso["fecha_salida"][:10],
                                  "descripcion_cie10": form.get("descripcion_egreso") or None}]
    return _escritura_medica(usuario, doc, visita, "EGRESO", parte,
                             {"condicion_salida": egreso.get("condicion_salida"),
                              "diagnostico_egreso": form.get("diagnostico_egreso")})


# ── 4. Reporte de HC y tablero ────────────────────────────────────────────

def _sello_reporte(historia: Dict[str, Any]) -> str:
    """SHA-256 del contenido clínico del reporte (sin tiempos de respuesta, que cambian en cada consulta)."""
    contenido = {k: v for k, v in historia.items() if k not in ("detalle_sedes",)}
    return hashlib.sha256(json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


@app.get("/reporte", response_class=HTMLResponse)
def vista_reporte(request: Request, buscar_doc: Optional[str] = None, pestana: str = "reporte",
                  usuario: Dict[str, Any] = Depends(requerir_roles(["medico", "auditor", "paciente", "administrador"]))):
    if usuario["rol"] == "paciente":
        buscar_doc = usuario["documento_id"]       # el paciente solo ve el suyo
    buscar_doc = (buscar_doc or "1001").strip()
    historia = consultar_historia_unificada(buscar_doc)
    por_sede = []
    for s in sorted(SEDES):
        det = next((d for d in historia["detalle_sedes"] if d["sede_id"] == s), {})
        por_sede.append({"sede_id": s, "nombre": det.get("nombre_sede") or SEDES[s]["nombre"],
                         "motor": SEDES[s]["motor"], "disponible": det.get("disponible", False),
                         "atenciones": [a for a in historia["atenciones"] if a.get("sede_id") == s]})
    reciente = historia["atenciones"][0] if historia["atenciones"] else None
    registrar_evento_auditoria("CONSULTA_REPORTE", usuario["username"], usuario["rol"], f"/reporte/{buscar_doc}",
                               "EXITOSO", {"documento_id": buscar_doc, "reporte_completo": historia["reporte_completo"]})
    return render("reporte_tablero.html", {
        "request": request, "usuario": usuario, "buscar_doc": buscar_doc, "historia": historia,
        "por_sede": por_sede, "cobertura": historia.get("cobertura_57"),
        "tabla57": tabla_57_legible(historia.get("paciente") or {}, reciente),
        "sello_reporte": _sello_reporte(historia), "pestana": pestana,
        "tablero": obtener_estado_general_plataforma() if usuario["rol"] in ("medico", "auditor", "administrador") else None,
        "generado_en": _ahora()})


# ── 5. Panel de administración (vista en vivo de toda la plataforma) ───────

ROLES_PANEL = ["auditor", "administrador"]
TIPOS_FHIR = ["Patient", "Encounter", "Condition", "Observation", "MedicationRequest", "AllergyIntolerance",
              "Practitioner", "Organization"]
_CACHE_FHIR: Dict[str, Any] = {"t": 0.0, "datos": None}


def _conteo_fhir() -> Dict[str, Any]:
    """Cuántos recursos de cada tipo hay en HAPI (con caché de 10 s para no cargarlo en cada sondeo)."""
    if _CACHE_FHIR["datos"] and time.time() - _CACHE_FHIR["t"] < 10:
        return _CACHE_FHIR["datos"]
    hapi = os.getenv("HAPI_FHIR_URL", "http://localhost:8090/fhir")

    def contar(tipo):
        try:
            r = httpx.get(f"{hapi}/{tipo}", params={"_summary": "count"}, timeout=4.0)
            return tipo, r.json().get("total", 0) if r.status_code == 200 else None
        except Exception:
            return tipo, None
    with ThreadPoolExecutor(max_workers=len(TIPOS_FHIR)) as pool:
        recursos = dict(pool.map(contar, TIPOS_FHIR))
    datos = {"disponible": any(v is not None for v in recursos.values()),
             "recursos": {k: (v or 0) for k, v in recursos.items()}}
    _CACHE_FHIR.update(t=time.time(), datos=datos)
    return datos


def _resumen_panel() -> Dict[str, Any]:
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_estado = pool.submit(obtener_estado_general_plataforma)
        f_bus = pool.submit(_mensajes_bus, 25)
        f_eventos = pool.submit(obtener_ultimos_eventos, 15)
        f_fhir = pool.submit(_conteo_fhir)
        estado, bus, eventos, fhir = f_estado.result(), f_bus.result(), f_eventos.result(), f_fhir.result()
    detalles = estado["nodos"]["detalles"]
    m = estado["bus"]
    por_estado = m.get("mensajes_por_estado_persistidos") or {}
    aud = dict(estado["auditoria"])
    aud["eventos"] = [{k: e.get(k) for k in ("indice", "tipo_evento", "usuario_sistema", "rol", "recurso_afectado",
                                             "resultado", "timestamp", "hash_propio")} for e in eventos]
    return {
        "generado_en": _ahora(),
        "kpis": {
            "sedes_activas": estado["nodos"]["activos"], "sedes_total": estado["nodos"]["total"],
            "hapi": estado["hapi_fhir"], "cobertura_fhir_global": estado["cobertura_fhir_global"],
            "pacientes_total": sum(s["total_pacientes"] for s in detalles.values()),
            "pacientes_con_fhir": sum(s["pacientes_con_fhir"] for s in detalles.values()),
            "mensajes_recibidos": m.get("total_recibidos", 0),
            "mensajes_entregados": por_estado.get("ENTREGADO", m.get("total_entregados", 0)),
            "mensajes_rechazados": por_estado.get("RECHAZADO", m.get("total_rechazados", 0)),
            "mensajes_reintentando": por_estado.get("REINTENTANDO", 0),
            "mensajes_muertos": por_estado.get("MUERTO", m.get("total_mensajes_muertos", 0)),
            "duplicados": m.get("total_duplicados_detectados", 0),
            "latencia_media_ms": m.get("latencia_media_ms", 0.0), "porcentaje_fallidos": m.get("porcentaje_fallidos", 0.0),
            "mensajes_ultimo_minuto": m.get("mensajes_ultimo_minuto", 0),
            "eventos_auditoria": aud.get("total_eventos_registrados", 0), "auditoria_integra": aud.get("cadena_integra"),
        },
        "sedes": [{**{k: s.get(k) for k in ("sede_id", "nombre", "motor", "disponible", "total_pacientes",
                                             "pacientes_con_fhir", "porcentaje_cobertura", "latencia_ms", "error")},
                   "ciudad": SEDES[s["sede_id"]]["ciudad"]} for s in detalles.values()],
        "bus": {**m, "mensajes_por_estado": por_estado},
        "mensajes": [{k: x.get(k) for k in ("mensaje_id", "formato", "sede_origen", "tipo_mensaje", "estado", "intentos",
                                            "actualizado_en", "motivo_rechazo", "motor")} for x in bus.get("mensajes", [])],
        "auditoria": aud,
        "fhir": fhir,
    }


def _pacientes_panel(q: Optional[str], limite: int) -> Dict[str, Any]:
    """Pacientes de las 3 sedes fusionados por documento (consulta en paralelo; tolera sedes caídas)."""
    repos = todos_los_repositorios()

    def leer(repo):
        try:
            return repo, repo.listar_pacientes(q, limite), None
        except Exception as e:
            return repo, [], e
    with ThreadPoolExecutor(max_workers=len(repos)) as pool:
        resultados = list(pool.map(leer, repos))
    caidas = [r.sede_id for r, _, err in resultados if err]
    por_doc: Dict[str, Dict[str, Any]] = {}
    for repo, filas, _ in resultados:
        for f in filas:
            p = por_doc.setdefault(f["documento_id"], {
                "documento_id": f["documento_id"], "nombre_completo": None, "sexo": None, "edad": None,
                "unidad_edad": None, "municipio_residencia": None, "en_fhir": False, "total_atenciones": 0,
                "ultima_atencion": None, "_mov": "", "sedes": []})
            for k in ("nombre_completo", "sexo", "edad", "unidad_edad", "municipio_residencia"):
                if p[k] in (None, "") and f.get(k) not in (None, ""):
                    p[k] = f[k]
            en_fhir = bool(f.get("fhir_patient_id"))
            p["en_fhir"] = p["en_fhir"] or en_fhir
            p["total_atenciones"] += int(f.get("atenciones") or 0)
            ua = str(f.get("ultima_atencion") or "") or None
            if ua and (not p["ultima_atencion"] or ua > p["ultima_atencion"]):
                p["ultima_atencion"] = ua
            p["_mov"] = max(p["_mov"], str(f.get("movimiento") or ""))
            p["sedes"].append({"sede_id": repo.sede_id, "motor": repo.motor, "en_fhir": en_fhir,
                               "atenciones": int(f.get("atenciones") or 0)})
    pacientes = sorted(por_doc.values(), key=lambda p: p["_mov"], reverse=True)[:limite]
    for p in pacientes:
        p.pop("_mov")
        p["sedes"].sort(key=lambda s: s["sede_id"])
    return {"total": len(por_doc), "sedes_no_disponibles": caidas, "pacientes": pacientes}


@app.get("/panel", response_class=HTMLResponse)
def vista_panel(request: Request, usuario: Dict[str, Any] = Depends(requerir_roles(ROLES_PANEL))):
    registrar_evento_auditoria("CONSULTA_PANEL", usuario["username"], usuario["rol"], "/panel", "EXITOSO", {})
    return render("panel.html", {"request": request, "usuario": usuario, "resumen": _resumen_panel(),
                                 "pacientes": _pacientes_panel(None, 50), "usuarios": usuarios.listar(usuario)})


@app.get("/api/panel/resumen")
def api_panel_resumen(usuario: Dict[str, Any] = Depends(requerir_roles(ROLES_PANEL))):
    return _resumen_panel()


@app.get("/api/panel/pacientes")
def api_panel_pacientes(q: Optional[str] = None, limite: int = 50,
                        usuario: Dict[str, Any] = Depends(requerir_roles(ROLES_PANEL))):
    return _pacientes_panel((q or "").strip() or None, max(1, min(limite, 200)))


@app.post("/api/panel/registrar")
async def api_panel_registrar(request: Request, usuario: Dict[str, Any] = Depends(requerir_roles(ROLES_PANEL))):
    """Registro rápido desde el panel: mismo camino que Admisión (HSB -> FHIR -> sede)."""
    try:
        datos = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"estado": "error", "motivo": "JSON mal formado"})
    if not isinstance(datos, dict) or str(datos.get("sede_id")) not in {str(s) for s in SEDES}:
        return JSONResponse(status_code=422, content={"estado": "rechazado", "motivos": ["sede no válida: debe ser 1, 2 o 3"]})
    resp = _admitir({k: v for k, v in datos.items() if isinstance(v, (str, int, float))}, usuario, int(datos["sede_id"]))
    resp.pop("http", None)
    codigo = 422 if resp.get("estado") == "rechazado" else 503 if resp.get("estado") == "error" else 200
    return JSONResponse(status_code=codigo, content=resp)


@app.post("/api/panel/migrar")
def api_migrar(sede: Optional[int] = None, usuario: Dict[str, Any] = Depends(requerir_roles(["administrador"]))):
    """Publica en FHIR los registros legados (0 % antes de migrar, 100 % después). Pasa por el HSB."""
    if usuario.get("sede_id"):
        sede = int(usuario["sede_id"])          # un administrador de sede solo migra su sede
    try:
        r = httpx.post(f"{HSB_URL}/hsb/migrar", params={"sede": sede} if sede else None, timeout=300.0)
        datos = r.json()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"HSB no disponible ({e.__class__.__name__})"})
    registrar_evento_auditoria("MIGRACION_FHIR", usuario["username"], usuario["rol"], "/hsb/migrar", "EXITOSO",
                               {"sedes": [{k: s.get(k) for k in ("sede", "publicados", "cobertura_fhir")}
                                          for s in datos.get("sedes", [])]})
    _CACHE_FHIR["t"] = 0.0
    return datos


# ── Gestión de usuarios (panel) ───────────────────────────────────────────

def _respuesta_error(e) -> JSONResponse:
    return JSONResponse(status_code=e.status, content={"ok": False, "motivos": e.motivos})


def _paciente_existe(doc: str) -> bool:
    return bool(consultar_historia_unificada(doc).get("paciente"))


@app.get("/api/panel/usuarios")
def api_usuarios(q: Optional[str] = None, rol: Optional[str] = None, sede: Optional[int] = None,
                 usuario: Dict[str, Any] = Depends(requerir_roles(ROLES_PANEL))):
    return usuarios.listar(usuario, (q or "").strip() or None, rol or None, sede)


@app.post("/api/panel/usuarios")
async def api_crear_usuario(request: Request, usuario: Dict[str, Any] = Depends(requerir_roles(ROLES_PANEL))):
    try:
        datos = await request.json()
        nuevo, temporal = usuarios.crear(datos if isinstance(datos, dict) else {}, usuario, "PANEL", _paciente_existe)
    except usuarios.ErrorUsuario as e:
        registrar_evento_auditoria("USUARIO_CREADO", usuario["username"], usuario["rol"], "/usuarios",
                                   "DENEGADO" if e.status == 403 else "FALLIDO", {"motivos": e.motivos})
        return _respuesta_error(e)
    except ValueError:
        return JSONResponse(status_code=400, content={"ok": False, "motivos": ["JSON mal formado"]})
    registrar_evento_auditoria("USUARIO_CREADO", usuario["username"], usuario["rol"], f"/usuarios/{nuevo['username']}",
                               "EXITOSO", {"rol_creado": nuevo["rol"], "sede_id": nuevo["sede_id"], "origen": "PANEL",
                                           "documento_id": nuevo.get("documento_id")})
    return {"ok": True, "usuario": nuevo, "clave_temporal": temporal}


@app.post("/api/panel/usuarios/{username}/estado")
async def api_estado_usuario(username: str, request: Request,
                             usuario: Dict[str, Any] = Depends(requerir_roles(ROLES_PANEL))):
    try:
        datos = await request.json()
        u = usuarios.cambiar_estado(username, bool(datos.get("activo")), usuario)
    except usuarios.ErrorUsuario as e:
        return _respuesta_error(e)
    registrar_evento_auditoria("USUARIO_ACTIVADO" if u["activo"] else "USUARIO_DESACTIVADO", usuario["username"],
                               usuario["rol"], f"/usuarios/{username}", "EXITOSO", {})
    return {"ok": True, "usuario": u}


@app.post("/api/panel/usuarios/{username}/restablecer")
def api_restablecer_usuario(username: str, usuario: Dict[str, Any] = Depends(requerir_roles(ROLES_PANEL))):
    try:
        temporal = usuarios.restablecer(username, usuario)
    except usuarios.ErrorUsuario as e:
        return _respuesta_error(e)
    registrar_evento_auditoria("CLAVE_RESTABLECIDA", usuario["username"], usuario["rol"], f"/usuarios/{username}",
                               "EXITOSO", {})
    return {"ok": True, "clave_temporal": temporal}


# ── API REST ──────────────────────────────────────────────────────────────

@app.get("/api/pacientes/{doc}/historia")
def api_historia(doc: str, request: Request, usuario: Dict[str, Any] = Depends(obtener_usuario_autenticado)):
    validar_acceso_historia_clinica(doc, usuario, request)
    registrar_evento_auditoria("CONSULTA_HC", usuario["username"], usuario["rol"], f"/historia/{doc}", "EXITOSO",
                               {"documento_id": doc, "via": "api"})
    return consultar_historia_unificada(doc)


@app.get("/api/pacientes/{doc}/bundle")
def api_bundle(doc: str, request: Request, usuario: Dict[str, Any] = Depends(obtener_usuario_autenticado)):
    """Bundle FHIR R4 de la historia unificada (las 3 sedes) para descargar."""
    validar_acceso_historia_clinica(doc, usuario, request)
    historia = consultar_historia_unificada(doc)
    if not historia["paciente"]:
        raise HTTPException(status_code=404, detail=f"No hay registros del documento {doc} en las sedes disponibles")
    bundle = construir_bundle(historia["paciente"], historia["atenciones"])
    if not historia["reporte_completo"]:
        bundle["meta"] = {"tag": [{"system": "https://clinica.local/fhir/tags", "code": "incompleto",
                                   "display": historia["aviso_incompletitud"]}]}
    registrar_evento_auditoria("DESCARGA_BUNDLE", usuario["username"], usuario["rol"], f"/bundle/{doc}", "EXITOSO",
                               {"documento_id": doc, "recursos": len(bundle["entry"])})
    return JSONResponse(content=bundle, headers={"Content-Disposition": f"attachment; filename=bundle-pac-{doc}.json"})


@app.get("/api/catalogo-57")
def api_catalogo(usuario: Dict[str, Any] = Depends(obtener_usuario_autenticado)):
    from dataclasses import asdict
    return {"total": len(CAMPOS_57), "campos": [asdict(c) for c in CAMPOS_57]}


@app.get("/api/auditoria/verificar")
def api_verificar(usuario: Dict[str, Any] = Depends(requerir_roles(["auditor", "medico", "administrador"]))):
    return estado_auditoria()


@app.get("/api/auditoria/eventos")
def api_eventos(limite: int = 50, usuario: Dict[str, Any] = Depends(requerir_roles(["auditor", "administrador"]))):
    return obtener_ultimos_eventos(limite)


@app.post("/api/auditoria/alterar-prueba")
def api_alterar(indice: int = Form(1), usuario: Dict[str, Any] = Depends(requerir_roles(["auditor", "administrador"]))):
    """Demo: cambia una fila de auditoría sin recalcular su hash (como un UPDATE manual)."""
    adulterar_evento_para_prueba(indice=indice, campo="usuario_sistema", nuevo_valor="intruso_adulterado")
    return RedirectResponse(url="/reporte?pestana=tablero", status_code=303)


# ── Observabilidad ────────────────────────────────────────────────────────

@app.get("/health")
def api_health():
    estado = obtener_estado_general_plataforma()
    nodos = estado["nodos"]
    return {"status": "UP" if nodos["activos"] == nodos["total"] and estado["hapi_fhir"] == "UP" else "DEGRADED",
            "servicio": "api_gateway", "nodos_activos": f"{nodos['activos']}/{nodos['total']}",
            "dependencias": {"sedes": {k: {"motor": v["motor"], "estado": "UP" if v["disponible"] else "DOWN"}
                                       for k, v in nodos["detalles"].items()},
                             "hapi_fhir": estado["hapi_fhir"], "hsb": estado["bus"].get("estado_general"),
                             "auditoria_central": "UP" if estado["auditoria"]["disponible"] else "DOWN"}}


@app.get("/metrics")
def api_metrics():
    aud = estado_auditoria()
    estado = obtener_estado_general_plataforma()
    return {"total_eventos_auditoria": aud["total_eventos_registrados"], "auditoria_cadena_integra": aud["cadena_integra"],
            "eventos_auditoria_en_espera": aud["eventos_en_espera"],
            "cobertura_fhir_por_sede": {k: v["porcentaje_cobertura"] for k, v in estado["nodos"]["detalles"].items()},
            "cobertura_fhir_global": estado["cobertura_fhir_global"],
            "nodos_activos": estado["nodos"]["activos"], "usuarios_de_prueba": len(USUARIOS_PRUEBA),
            "timestamp": time.time()}
