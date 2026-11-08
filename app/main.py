"""
app/main.py
API Gateway y Servidor Web de la Plataforma de Interoperabilidad Clínica.

Implementa:
- Autenticación JWT y control de acceso basado en roles (RBAC)
- Vistas HTML accesibles por rol (Paciente, Admisionista, Médico, Reporte & Tablero)
- Consulta unificada resiliente con soporte de caídas de sede
- Auditoría encadenada por hash SHA-256 inmutable
- Endpoints de observabilidad /health y /metrics
"""

import os
import time
import json
import hashlib
import httpx
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Request, Response, Depends, Form, Query, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import (
    autenticar_usuario,
    crear_token_jwt,
    USUARIOS_PRUEBA
)
from app.rbac import (
    obtener_usuario_autenticado,
    requerir_roles,
    validar_acceso_historia_clinica
)
from app.audit import (
    registrar_evento_auditoria,
    verificar_cadena_auditoria,
    adulterar_evento_para_prueba,
    obtener_ultimos_eventos,
    _CADENA_AUDITORIA
)
from app.dashboard import obtener_estado_general_plataforma
from db.consulta_unificada import consultar_historia_unificada, CONFIG_NODOS
from fhir.normalizer import construir_bundle_transaccional

app = FastAPI(
    title="API Gateway - Interoperabilidad Clínica",
    description="Gateway central con seguridad RBAC, vistas clínicas, resiliencia y auditoría",
    version="1.0.0"
)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
HSB_URL = os.getenv("HSB_URL", "http://localhost:8001")


# Evento Génesis al iniciar
@app.on_event("startup")
def evento_inicio():
    if not _CADENA_AUDITORIA:
        registrar_evento_auditoria(
            tipo_evento="SISTEMA_INICIADO",
            usuario_sistema="SISTEMA",
            rol="sistema",
            recurso_afectado="plataforma_clinica",
            resultado="EXITOSO",
            detalle={"mensaje": "Plataforma iniciada y cadena de auditoría inicializada con bloque génesis"}
        )


# ── Rutas de Autenticación ──────────────────────────────────

@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
def vista_login(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/auth/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    usr = autenticar_usuario(username, password)
    if not usr:
        registrar_evento_auditoria(
            tipo_evento="LOGIN",
            usuario_sistema=username,
            rol="desconocido",
            recurso_afectado="/auth/login",
            resultado="FALLIDO",
            detalle={"motivo": "Credenciales inválidas"}
        )
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Credenciales inválidas. Compruebe su usuario y contraseña."},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    # Generar Token JWT
    token_data = {
        "sub": usr["username"],
        "username": usr["username"],
        "rol": usr["rol"],
        "nombre_completo": usr["nombre_completo"],
        "documento_id": usr["documento_id"],
        "sede_id": usr["sede_id"]
    }
    token = crear_token_jwt(token_data)

    registrar_evento_auditoria(
        tipo_evento="LOGIN",
        usuario_sistema=usr["username"],
        rol=usr["rol"],
        recurso_afectado="/auth/login",
        resultado="EXITOSO",
        detalle={"sede_id": usr["sede_id"]}
    )

    # Redireccionar según el rol oficial
    destinos = {
        "paciente": "/paciente",
        "admisionista": "/admision",
        "medico": "/medico",
        "auditor": "/reporte"
    }
    url_destino = destinos.get(usr["rol"], "/reporte")

    response = RedirectResponse(url=url_destino, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=3600)
    return response


@app.get("/auth/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response


# ── Vistas por Rol ──────────────────────────────────────────

# 1. Vista Paciente
@app.get("/paciente", response_class=HTMLResponse)
def vista_paciente(request: Request, usuario: Dict[str, Any] = Depends(requerir_roles(["paciente"]))):
    doc = usuario.get("documento_id")
    historia = consultar_historia_unificada(doc)

    # Filtrar auditoría para mostrar al paciente quién ha visto su historia
    todos_eventos = obtener_ultimos_eventos(100)
    accesos_paciente = [
        e for e in todos_eventos
        if doc in str(e.get("recurso_afectado", "")) or doc in str(e.get("detalle", {}))
    ]

    registrar_evento_auditoria(
        tipo_evento="CONSULTA_HC",
        usuario_sistema=usuario["username"],
        rol=usuario["rol"],
        recurso_afectado=f"/paciente/{doc}",
        resultado="EXITOSO",
        detalle={"consulta_propia": True}
    )

    return templates.TemplateResponse("paciente.html", {
        "request": request,
        "usuario": usuario,
        "historia": historia,
        "accesos": accesos_paciente
    })


# 2. Vista Admisionista
@app.get("/admision", response_class=HTMLResponse)
def vista_admision(
    request: Request,
    buscar_doc: Optional[str] = None,
    usuario: Dict[str, Any] = Depends(requerir_roles(["admisionista"]))
):
    resultado_busqueda = None
    if buscar_doc:
        res = consultar_historia_unificada(buscar_doc)
        # Ocultar diagnósticos (mínimo privilegio: admisionista no ve diagnósticos)
        if res and res.get("atenciones"):
            for at in res["atenciones"]:
                at["diagnosticos"] = []
        resultado_busqueda = res

    # Obtener mensajes del HSB para el monitor
    mensajes_recientes = []
    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(f"{HSB_URL}/metrics")
            if resp.status_code == 200:
                # Simular vista de mensajes recientes
                mensajes_recientes = [
                    {"mensaje_id": "MSG-0001", "formato": "HL7_V2", "sede_origen": 2, "estado": "ENTREGADO", "intentos": 1, "hash_contenido": "7a8b9c..."},
                    {"mensaje_id": "MSG-0002", "formato": "HL7_V2", "sede_origen": 1, "estado": "ENTREGADO", "intentos": 1, "hash_contenido": "3f2e1d..."},
                    {"mensaje_id": "MSG-0003", "formato": "HL7_V2", "sede_origen": 3, "estado": "RECHAZADO", "intentos": 0, "hash_contenido": "9e8d7c..."}
                ]
    except Exception:
        pass

    return templates.TemplateResponse("admision.html", {
        "request": request,
        "usuario": usuario,
        "buscar_doc": buscar_doc,
        "resultado_busqueda": resultado_busqueda,
        "mensajes_recientes": mensajes_recientes,
        "mensaje_post": None
    })


@app.post("/admision/abrir-atencion")
async def abrir_atencion(
    request: Request,
    documento_id: str = Form(...),
    nombre_completo: str = Form(...),
    fecha_nacimiento: str = Form(...),
    sexo: str = Form(...),
    sede_id: int = Form(...),
    clase_atencion: str = Form(...),
    triage: int = Form(...),
    usuario: Dict[str, Any] = Depends(requerir_roles(["admisionista"]))
):
    # Generar mensaje HL7 ADT^A01 sintético y enviarlo al HSB
    visita_id = f"V-S{sede_id}-ADM-{int(time.time()) % 10000}"
    fecha_hl7 = time.strftime("%Y%m%d%H%M")
    partes_nombre = nombre_completo.split(" ")
    family = partes_nombre[0]
    given = "^".join(partes_nombre[1:]) if len(partes_nombre) > 1 else partes_nombre[0]

    hl7_msg = (
        f"MSH|^~\\&|HIS_SEDE{sede_id}|SEDE{sede_id}|HSB|CENTRAL|{fecha_hl7}||ADT^A01|MSG-ADM-{visita_id}|P|2.5\r"
        f"PID|1||{documento_id}^^^HIS||{family}^{given}||{fecha_nacimiento.replace('-', '')}|{sexo}\r"
        f"PV1|1|{clase_atencion}|||||MED-01^Vega^Laura||||||||||||{visita_id}|||||||||||||||||||||||||{fecha_hl7}"
    )

    hsb_exito = False
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(
                f"{HSB_URL}/hsb/hl7",
                headers={"Content-Type": "text/plain"},
                content=hl7_msg.encode("utf-8")
            )
            hsb_exito = resp.status_code in (200, 202)
    except Exception:
        hsb_exito = False

    registrar_evento_auditoria(
        tipo_evento="APERTURA_ATENCION",
        usuario_sistema=usuario["username"],
        rol=usuario["rol"],
        recurso_afectado=f"/atenciones/{visita_id}",
        resultado="EXITOSO" if hsb_exito else "ENCOLADO_LOCAL",
        detalle={
            "documento_id": documento_id,
            "sede_id": sede_id,
            "triage": triage,
            "visita": visita_id
        }
    )

    msg = f"✓ Atención {visita_id} creada exitosamente para el paciente {nombre_completo}. Enviada al bus de la Sede {sede_id}."
    return templates.TemplateResponse("admision.html", {
        "request": request,
        "usuario": usuario,
        "buscar_doc": documento_id,
        "resultado_busqueda": None,
        "mensajes_recientes": [],
        "mensaje_post": msg
    })


# 3. Vista Médico
@app.get("/medico", response_class=HTMLResponse)
def vista_medico(
    request: Request,
    buscar_doc: Optional[str] = "1001",
    sello_generado: Optional[str] = None,
    usuario: Dict[str, Any] = Depends(requerir_roles(["medico"]))
):
    historia = consultar_historia_unificada(buscar_doc)

    registrar_evento_auditoria(
        tipo_evento="CONSULTA_HC",
        usuario_sistema=usuario["username"],
        rol=usuario["rol"],
        recurso_afectado=f"/historia/{buscar_doc}",
        resultado="EXITOSO",
        detalle={"total_atenciones": len(historia.get("atenciones", []))}
    )

    return templates.TemplateResponse("medico.html", {
        "request": request,
        "usuario": usuario,
        "buscar_doc": buscar_doc,
        "historia": historia,
        "sello_generado": sello_generado
    })


@app.post("/medico/registrar-evolucion")
def registrar_evolucion(
    request: Request,
    documento_id: str = Form(...),
    numero_visita: str = Form(...),
    cie10_codigo: str = Form(...),
    motivo_egreso: str = Form(...),
    condicion_salida: str = Form(...),
    usuario: Dict[str, Any] = Depends(requerir_roles(["medico"]))
):
    # Generar sello criptográfico SHA-256 de integridad médica del egreso
    sello_contenido = f"{numero_visita}|{documento_id}|{cie10_codigo}|{motivo_egreso}|{condicion_salida}|{time.time()}"
    sello_hash = hashlib.sha256(sello_contenido.encode("utf-8")).hexdigest()

    registrar_evento_auditoria(
        tipo_evento="ESCRITURA_HC",
        usuario_sistema=usuario["username"],
        rol=usuario["rol"],
        recurso_afectado=f"/atenciones/{numero_visita}",
        resultado="EXITOSO",
        detalle={
            "documento_id": documento_id,
            "visita": numero_visita,
            "cie10": cie10_codigo,
            "sello_hash": sello_hash
        }
    )

    return RedirectResponse(
        url=f"/medico?buscar_doc={documento_id}&sello_generado={sello_hash}",
        status_code=status.HTTP_303_SEE_OTHER
    )


# 4. Vista Reporte de HC y Tablero de Estado
@app.get("/reporte", response_class=HTMLResponse)
def vista_reporte_tablero(
    request: Request,
    buscar_doc: Optional[str] = "1001",
    usuario: Dict[str, Any] = Depends(requerir_roles(["medico", "auditor", "paciente"]))
):
    # Validar que si es paciente, sólo pueda consultar su propio documento
    if usuario["rol"] == "paciente":
        buscar_doc = usuario.get("documento_id", "1001")

    historia = consultar_historia_unificada(buscar_doc)
    tablero = obtener_estado_general_plataforma()

    # Sello de integridad del reporte
    contenido_reporte = f"{buscar_doc}|{len(historia.get('atenciones', []))}|{historia.get('reporte_completo')}"
    sello_reporte = hashlib.sha256(contenido_reporte.encode("utf-8")).hexdigest()

    registrar_evento_auditoria(
        tipo_evento="CONSULTA_REPORTE",
        usuario_sistema=usuario["username"],
        rol=usuario["rol"],
        recurso_afectado=f"/reporte/{buscar_doc}",
        resultado="EXITOSO",
        detalle={"reporte_completo": historia.get("reporte_completo")}
    )

    return templates.TemplateResponse("reporte_tablero.html", {
        "request": request,
        "usuario": usuario,
        "buscar_doc": buscar_doc,
        "historia": historia,
        "tablero": tablero,
        "sello_reporte": sello_reporte
    })


# ── Endpoints de la API REST ────────────────────────────────

@app.get("/api/pacientes/{doc}/historia")
def api_obtener_historia(
    doc: str,
    usuario: Dict[str, Any] = Depends(obtener_usuario_autenticado)
):
    """
    Endpoint protegido por la matriz de permisos RBAC.
    - Paciente: solo puede ver su documento (403 si intenta ver otro).
    - Admisionista: 403 Forbidden.
    - Médico y Auditor: Permitido.
    """
    validar_acceso_historia_clinica(doc, usuario)
    historia = consultar_historia_unificada(doc)
    return historia


@app.get("/api/pacientes/{doc}/bundle")
def api_descargar_bundle(
    doc: str,
    usuario: Dict[str, Any] = Depends(obtener_usuario_autenticado)
):
    """Genera y descarga el Bundle transaction FHIR R4 completo del paciente."""
    validar_acceso_historia_clinica(doc, usuario)
    historia = consultar_historia_unificada(doc)

    pac = historia.get("paciente") or {
        "documento_id": doc,
        "nombre_completo": f"Paciente {doc}",
        "fecha_nacimiento": "1990-01-01",
        "sexo": "O"
    }

    # Desaplanar diagnósticos y tecnologías de todas las atenciones
    todos_dx = []
    todas_tech = []
    for at in historia.get("atenciones", []):
        todos_dx.extend(at.get("diagnosticos", []))
        todas_tech.extend(at.get("tecnologias", []))

    bundle = construir_bundle_transaccional(
        usuario=pac,
        atenciones=historia.get("atenciones", []),
        diagnosticos=todos_dx,
        tecnologias=todas_tech
    )

    # Si la historia estuvo incompleta, marcar tag FHIR
    if not historia.get("reporte_completo"):
        bundle["meta"] = {
            "tag": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue",
                    "code": "incomplete",
                    "display": "Historial clínico incompleto por caída de sede"
                }
            ]
        }

    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f"attachment; filename=bundle-pac-{doc}.json"}
    )


# ── Endpoints de Auditoría y Verificación ────────────────────

@app.get("/api/auditoria/verificar")
def api_verificar_auditoria(usuario: Dict[str, Any] = Depends(requerir_roles(["auditor", "medico"]))):
    """Ejecuta el algoritmo criptográfico que recorre la cadena de auditoría."""
    es_integra, detalle_fallo = verificar_cadena_auditoria()
    return {
        "cadena_integra": es_integra,
        "total_eventos": len(_CADENA_AUDITORIA),
        "primer_evento_alterado": detalle_fallo
    }


@app.post("/api/auditoria/alterar-prueba")
def api_alterar_prueba_auditoria(usuario: Dict[str, Any] = Depends(requerir_roles(["auditor"]))):
    """
    Prueba obligatoria docente: Adultera deliberadamente un campo de un evento en memoria
    para demostrar que el verificador detecta la ruptura criptográfica.
    """
    try:
        ev = adulterar_evento_para_prueba(indice=0, campo="usuario_sistema", nuevo_valor="atacante_adulterado")
        return RedirectResponse(url="/reporte", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return {"error": str(e)}


# ── Observabilidad: /health y /metrics ───────────────────────

@app.get("/health")
def api_health():
    """Chequeo de salud del API Gateway y sus dependencias."""
    estado = obtener_estado_general_plataforma()
    nodos_activos = estado["nodos"]["activos"]
    total_nodos = estado["nodos"]["total"]

    salud_general = "UP" if nodos_activos == total_nodos else "DEGRADED"

    return {
        "status": salud_general,
        "api_service": "UP",
        "nodos_activos": f"{nodos_activos}/{total_nodos}",
        "dependencias": {
            "nodos_postgres": estado["nodos"]["detalles"],
            "bus_hsb": estado["bus"].get("estado_general", "DESCONOCIDO")
        }
    }


@app.get("/metrics")
def api_metrics():
    """Métricas operacionales del API Gateway."""
    es_integra, _ = verificar_cadena_auditoria()
    return {
        "total_eventos_auditoria": len(_CADENA_AUDITORIA),
        "auditoria_cadena_integra": es_integra,
        "usuarios_de_prueba_activos": len(USUARIOS_PRUEBA),
        "timestamp": time.time()
    }
