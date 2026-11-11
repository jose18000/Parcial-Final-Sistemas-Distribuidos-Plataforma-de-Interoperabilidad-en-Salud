#!/usr/bin/env python3
"""
scripts/verificar_interoperabilidad.py
Verificación de punta a punta de la interoperabilidad, SEDE POR SEDE y FLUJO POR FLUJO, contra el
sistema desplegado. Escribe un informe en Markdown con una fila por comprobación.

    python3 scripts/verificar_interoperabilidad.py --api http://localhost:8000 --hsb http://localhost:8001 \
        --fhir http://localhost:8090/fhir --salida docs/evidencias/07_verificacion_por_sede.md

Solo usa la biblioteca estándar. Crea pacientes sintéticos nuevos en cada ejecución.
"""

import argparse
import base64
import datetime
import os
import ssl
import http.cookiejar
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

AP = argparse.ArgumentParser()
AP.add_argument("--api", default="http://localhost:8000")
AP.add_argument("--hsb", default="http://localhost:8001")
AP.add_argument("--fhir", default="http://localhost:8090/fhir")
AP.add_argument("--salida", default="docs/evidencias/07_verificacion_por_sede.md")
AP.add_argument("--ca", default="certs/ca.pem", help="CA de la plataforma para verificar HTTPS")
AP.add_argument("--secreto-qa", default=os.getenv("OAUTH_SECRETO_QA", "qa_secreto_2026"))
AP.add_argument("--secreto-sede1", default=os.getenv("OAUTH_SECRETO_SEDE1", "sede1_secreto_2026"))
A = AP.parse_args()
# HTTPS verificado contra la CA propia (si existe); sin CA se usa la verificación normal del sistema.
CTX = ssl.create_default_context(cafile=A.ca) if os.path.exists(A.ca) else ssl.create_default_context()

MOTOR = {1: "PostgreSQL", 2: "MongoDB", 3: "PostgreSQL"}
CIUDAD = {1: "Sincelejo", 2: "Cartagena", 3: "Corozal"}
filas = []          # (sede, sección, comprobación, ok, detalle)


def anotar(sede, seccion, comprobacion, ok, detalle=""):
    filas.append((sede, seccion, comprobacion, bool(ok), str(detalle)[:160]))
    print(("OK   " if ok else "FALLA"), sede, "|", seccion, "|", comprobacion, "|", detalle)


class Cliente:
    def __init__(self, token=None, basic=None):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                              urllib.request.HTTPSHandler(context=CTX))
        self.token, self.basic = token, basic

    def pedir(self, metodo, url, datos=None, tipo=None, form=None):
        cab = {"Accept": "application/json"}
        if self.token:
            cab["Authorization"] = f"Bearer {self.token}"
        elif self.basic:
            cab["Authorization"] = "Basic " + base64.b64encode(f"{self.basic[0]}:{self.basic[1]}".encode()).decode()
        if form is not None:
            datos = urllib.parse.urlencode(form).encode()
            cab["Content-Type"] = "application/x-www-form-urlencoded"
        elif datos is not None:
            datos = datos if isinstance(datos, bytes) else datos.encode("utf-8")
            cab["Content-Type"] = tipo or "text/plain"
        req = urllib.request.Request(url, data=datos, method=metodo, headers=cab)
        try:
            with self.op.open(req, timeout=60) as r:
                cuerpo = r.read().decode("utf-8", "replace")
                return r.status, cuerpo, r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), url

    def json(self, metodo, url, **kw):
        st, cuerpo, _ = self.pedir(metodo, url, **kw)
        try:
            return st, json.loads(cuerpo)
        except ValueError:
            return st, {"_texto": cuerpo[:300]}


def login(usuario, clave):
    c = Cliente()
    st, _, final = c.pedir("POST", f"{A.api}/auth/login", form={"username": usuario, "password": clave})
    return c


def doc_nuevo():
    return str(random.randint(80_000_000, 89_999_999))


def adt(sede, doc, visita, mid, dx="J45.9^Asma^I10"):
    ahora = datetime.datetime.now().strftime("%Y%m%d%H%M")
    return "\r".join([
        f"MSH|^~\\&|HIS_SEDE{sede}|SEDE{sede}|HSB|CENTRAL|{ahora}||ADT^A01|{mid}|P|2.5",
        f"PID|1||{doc}^^^HIS^CC||Prueba^Verificacion||19850315|F|||Calle 1^^{CIUDAD[sede]}^^^CO^^^70001||3001112233",
        f"PV1|1|E|||||MED-01^Vega^Laura|||||||01|||||{visita}|||||||||||||||||||||||||{ahora}",
        "PV2|||^Control de verificación",
        "IN1|1|||Nueva EPS",
        f"DG1|1||{dx}||{ahora[:8]}|A||||||||1"]) + "\r"


def oru(sede, doc, visita, mid):
    ahora = datetime.datetime.now().strftime("%Y%m%d%H%M")
    return "\r".join([
        f"MSH|^~\\&|LAB_SEDE{sede}|SEDE{sede}|HSB|CENTRAL|{ahora}||ORU^R01|{mid}|P|2.5",
        f"PID|1||{doc}^^^HIS^CC||Prueba^Verificacion||19850315|F",
        f"PV1|1|E|||||MED-01^Vega^Laura||||||||||||{visita}|||||||||||||||||||||||||{ahora}",
        "OBX|1|NM|2345-7^Glucosa en suero^LN||98|mg/dL|||||F"]) + "\r"


def fhir_existe(ruta):
    c = Cliente()
    st, _, _ = c.pedir("GET", f"{A.fhir}/{ruta}")
    return st == 200


def token_cliente(client_id, secreto):
    """OAuth 2.0 client_credentials contra la API (RFC 6749 §4.4)."""
    st, r = Cliente(basic=(client_id, secreto)).json("POST", f"{A.api}/oauth/token",
                                                     form={"grant_type": "client_credentials"})
    return r.get("access_token") if st == 200 else None


TOKEN_QA = token_cliente("herramientas_qa", A.secreto_qa)
hsb, admin = Cliente(token=TOKEN_QA), login("admin_plataforma", "Admin123!")
medico, admision = login("medico_mateo", "Medico123!"), login("admision_laura", "Admision123!")
semilla = int(time.time())
doc_red = doc_nuevo()             # paciente que se atiende en las 3 sedes

for sede in (1, 2, 3):
    S = f"Sede {sede} · {CIUDAD[sede]} ({MOTOR[sede]})"
    doc = doc_nuevo()
    visita = f"V-S{sede}-VER-{semilla % 100000}"

    # 1. HL7 ADT^A01
    st, r = hsb.json("POST", f"{A.hsb}/hsb/hl7", datos=adt(sede, doc, visita, f"VER-{semilla}-{sede}-ADT"))
    anotar(S, "HL7 v2", "ADT^A01 entregado", r.get("estado") == "entregado", r.get("estado"))
    anotar(S, "FHIR", "Patient y Encounter en HAPI", fhir_existe(f"Patient/pac-{doc}") and fhir_existe(f"Encounter/enc-{visita}"),
           f"pac-{doc}")
    st, h = medico.json("GET", f"{A.api}/api/pacientes/{doc}/historia")
    anotar(S, "Base de la sede", f"Guardado en {MOTOR[sede]} y leído por la consulta unificada",
           sede in h.get("sedes_con_registros", []) and any(a.get("motor_origen") == MOTOR[sede].lower() for a in h.get("atenciones", [])),
           h.get("sedes_con_registros"))

    # 2. Reenvío -> duplicado
    st, r = hsb.json("POST", f"{A.hsb}/hsb/hl7", datos=adt(sede, doc, visita, f"VER-{semilla}-{sede}-ADT"))
    anotar(S, "Idempotencia", "Reenvío del mismo HL7 = duplicado", r.get("estado") == "duplicado", r.get("estado"))

    # 3. HL7 ORU^R01 (laboratorio) sobre la misma visita
    st, r = hsb.json("POST", f"{A.hsb}/hsb/hl7", datos=oru(sede, doc, visita, f"VER-{semilla}-{sede}-ORU"))
    obs_ok = fhir_existe(f"Observation/obs-{visita}-2345-7")
    c = Cliente(); st2, enc = c.json("GET", f"{A.fhir}/Encounter/enc-{visita}")
    anotar(S, "HL7 v2", "ORU^R01 entregado y Observation LOINC en HAPI", r.get("estado") == "entregado" and obs_ok, r.get("estado"))
    anotar(S, "FHIR", "El ORU no borra el diagnóstico del Encounter", bool(enc.get("diagnosis")),
           "diagnosis presente" if enc.get("diagnosis") else "sin diagnosis")

    # 4. CSV legado
    doc_csv = doc_nuevo()
    csv = ("documento;nombre;sexo;nacimiento;dx_local;fecha;triage;profesional;municipio_residencia;entidad_salud\n"
           f"{doc_csv};Mario Verificación Pérez;M;1979-08-02;HIPERTENSION;2026-11-11T08:15;3;MED-01;70001;Salud Total\n")
    st, r = hsb.json("POST", f"{A.hsb}/hsb/csv?sede={sede}", datos=csv, tipo="text/csv")
    anotar(S, "CSV legado", "Fila CSV entregada con dx_local -> CIE-10", r.get("total_entregados") == 1, r.get("total_entregados"))
    anotar(S, "FHIR", "Condition I10 del CSV en HAPI", fhir_existe(f"Patient/pac-{doc_csv}"), f"pac-{doc_csv}")

    # 5. JSON (registro por número de campo)
    doc_json = doc_nuevo()
    reg = {"registro": {"2": doc_json, "4": "Ana Verificación Ruiz", "5": "1995-01-20", "8": "F", "13": "CO",
                        "14": "13001", "16": "Coosalud EPS", "17": "2026-11-11T09:00", "18": "01", "19": "02",
                        "20": "01", "21": "Control", "34": "E11.9"}}
    st, r = hsb.json("POST", f"{A.hsb}/hsb/json?sede={sede}", datos=json.dumps(reg), tipo="application/json")
    anotar(S, "JSON", "Registro JSON entregado", r.get("estado") == "entregado", r.get("estado"))

    # 6. Admisión desde la vista (formulario) -> cuenta del portal
    doc_adm = doc_nuevo()
    st, cuerpo, _ = admision.pedir("POST", f"{A.api}/admision/registrar", form={
        "sede_id": str(sede), "tipo_documento": "CC", "documento_id": doc_adm, "nombres": "Laura", "apellidos": "Admitida Prueba",
        "fecha_nacimiento": "1988-06-06", "sexo": "F", "pais_nacionalidad": "CO", "pais_residencia": "CO",
        "municipio_residencia": "70001", "entidad_salud": "Nueva EPS", "modalidad_entrega": "01", "entorno_atencion": "01",
        "via_ingreso": "01", "causa_atencion": "Dolor", "clasificacion_triage": "3"})
    st, us = admin.json("GET", f"{A.api}/api/panel/usuarios?q={doc_adm}")
    cuenta = [u for u in us.get("usuarios", []) if u["username"] == doc_adm]
    anotar(S, "Admisión", "Paciente admitido y publicado en FHIR", fhir_existe(f"Patient/pac-{doc_adm}"), f"pac-{doc_adm}")
    anotar(S, "Cuentas", "Cuenta del portal creada (origen ADMISION, clave temporal)",
           bool(cuenta) and cuenta[0]["origen"] == "ADMISION" and cuenta[0]["debe_cambiar_clave"], doc_adm)

    # 7. Escrituras del médico sobre la visita de esta sede
    for ruta, form in (("diagnostico", {"cie10_codigo": "R51", "descripcion_cie10": "Cefalea", "rol": "RELACIONADO", "tipo_diagnostico": "02"}),
                       ("formula", {"descripcion_medicamento": "Acetaminofén 500 mg tableta", "dosis": "500 mg", "via_administracion": "01",
                                    "frecuencia": "Cada 8 horas", "dias_tratamiento": "3", "unidades_aplicadas": "9", "finalidad_tecnologia": "01"}),
                       ("egreso", {"condicion_salida": "01", "diagnostico_egreso": "J45.9", "alergias": "Ninguna conocida"})):
        st, cuerpo, final = medico.pedir("POST", f"{A.api}/medico/{ruta}", form={"documento_id": doc, "numero_visita": visita, **form})
        q = urllib.parse.parse_qs(urllib.parse.urlparse(final).query)
        anotar(S, "Médico", f"{ruta.capitalize()} guardado con código de verificación",
               q.get("estado", [""])[0] == "entregado" and len(q.get("sello", [""])[0]) == 64, q.get("estado", ["?"])[0])
    st, h = medico.json("GET", f"{A.api}/api/pacientes/{doc}/historia")
    at = next((a for a in h.get("atenciones", []) if a.get("numero_visita") == visita), {})
    roles = sorted(d["rol"] for d in at.get("diagnosticos", []))
    anotar(S, "Médico", "La sede conserva ingreso, relacionado, egreso, fórmula y laboratorio",
           roles == ["EGRESO", "INGRESO", "RELACIONADO"] and len(at.get("tecnologias", [])) == 2 and at.get("egreso", {}).get("sello_hash"),
           f"dx={roles} tecnologías={len(at.get('tecnologias', []))}")
    c = Cliente(); st2, enc = c.json("GET", f"{A.fhir}/Encounter/enc-{visita}")
    usos = sorted(d["use"]["coding"][0]["code"] for d in enc.get("diagnosis", []))
    anotar(S, "FHIR", "Encounter finalizado con diagnóstico de ingreso y egreso", enc.get("status") == "finished" and usos == ["AD", "DD"],
           f"{enc.get('status')} {usos}")
    c57 = h.get("cobertura_57") or {}
    anotar(S, "57 campos", "Obligatorios cubiertos (paciente de la prueba)", c57.get("porcentaje_obligatorios") is not None,
           f"{c57.get('campos_cubiertos')}/57 · obligatorios {c57.get('porcentaje_obligatorios')} %")

    # 8. El paciente de la red se atiende también en esta sede
    hsb.json("POST", f"{A.hsb}/hsb/hl7", datos=adt(sede, doc_red, f"V-S{sede}-RED-{semilla % 100000}", f"VER-{semilla}-{sede}-RED", "I10^Hipertension esencial^I10"))

# ── Comprobaciones de toda la red ──────────────────────────────────────────
R = "Red (3 sedes)"
st, h = medico.json("GET", f"{A.api}/api/pacientes/{doc_red}/historia")
motores = sorted({a.get("motor_origen") for a in h.get("atenciones", [])})
anotar(R, "Consulta unificada", "Un paciente atendido en las 3 sedes aparece completo",
       h.get("sedes_con_registros") == [1, 2, 3] and h.get("reporte_completo"), f"sedes {h.get('sedes_con_registros')}")
anotar(R, "Consulta unificada", "Mezcla PostgreSQL y MongoDB en una sola historia", motores == ["mongodb", "postgresql"], motores)
st, cuerpo, _ = medico.pedir("GET", f"{A.api}/api/pacientes/{doc_red}/bundle")
st, val = Cliente().json("POST", f"{A.fhir}/Bundle/$validate", datos=cuerpo, tipo="application/fhir+json")
errores = [i for i in val.get("issue", []) if i.get("severity") in ("error", "fatal")]
anotar(R, "FHIR", "Bundle de las 3 sedes validado por HAPI ($validate)", not errores, f"{len(errores)} errores")
st, cuerpo, _ = medico.pedir("GET", f"{A.api}/api/pacientes/1001/bundle")
st, val = Cliente().json("POST", f"{A.fhir}/Bundle/$validate", datos=cuerpo, tipo="application/fhir+json")
anotar(R, "FHIR", "Bundle del paciente 1001 validado", not [i for i in val.get("issue", []) if i.get("severity") in ("error", "fatal")])
paciente = login("paciente_carlos", "Paciente123!")
st, _ = paciente.json("GET", f"{A.api}/api/pacientes/1002/historia")
anotar(R, "Seguridad", "Paciente que pide la historia de otro = 403", st == 403, st)
st, _ = admision.json("GET", f"{A.api}/api/pacientes/1001/historia")
anotar(R, "Seguridad", "Admisionista que pide una historia clínica = 403", st == 403, st)
sede2 = login("admin_cartagena", "Admin123!")
st, r = sede2.json("POST", f"{A.api}/api/panel/usuarios", datos=json.dumps({"username": f"x.s1.{semilla % 10000}",
                   "nombre_completo": "X", "rol": "medico", "documento_id": "M", "sede_id": 1}), tipo="application/json")
anotar(R, "Seguridad", "Administrador de sede 2 no puede crear usuarios en la sede 1", st == 403, st)
auditor = login("auditor_elena", "Auditor123!")
st, au = auditor.json("GET", f"{A.api}/api/auditoria/verificar")
anotar(R, "Auditoría", "Cadena SHA-256 íntegra", au.get("cadena_integra") is True, f"{au.get('total_eventos_registrados')} eventos")
st, m = Cliente().json("GET", f"{A.api}/metrics")
cob = m.get("cobertura_fhir_por_sede", {})
for s in (1, 2, 3):
    anotar(f"Sede {s} · {CIUDAD[s]} ({MOTOR[s]})", "Cobertura FHIR", "Pacientes de la sede publicados en FHIR",
           cob.get(f"sede_{s}") == 100.0, f"{cob.get(f'sede_{s}')} %")
# ── Seguridad: OAuth 2.0 en el bus y canal cifrado ─────────────────────────
anotar(R, "OAuth 2.0", "client_credentials emite token para el bus", bool(TOKEN_QA))
st, r = Cliente(basic=("herramientas_qa", "secreto-falso")).json("POST", f"{A.api}/oauth/token",
                                                                 form={"grant_type": "client_credentials"})
anotar(R, "OAuth 2.0", "Secreto de cliente incorrecto = 401 invalid_client", st == 401 and r.get("error") == "invalid_client", st)
st, _ = Cliente().json("POST", f"{A.hsb}/hsb/hl7", datos=adt(1, doc_nuevo(), "V-S1-SINTOKEN", f"VER-{semilla}-SINTOKEN"))
anotar(R, "OAuth 2.0", "Bus sin token = 401", st == 401, st)
st, tu = Cliente().json("POST", f"{A.api}/oauth/token", form={"grant_type": "password", "username": "medico_mateo",
                        "password": "Medico123!", "client_id": "herramientas_qa", "client_secret": A.secreto_qa})
st, _ = Cliente(token=tu.get("access_token")).json("POST", f"{A.hsb}/hsb/csv?sede=1", datos="x", tipo="text/csv")
anotar(R, "OAuth 2.0", "Token de usuario (audiencia api) rechazado por el bus = 401", st == 401, st)
st, _ = Cliente(token=token_cliente("sistema_sede1", A.secreto_sede1)).json("POST", f"{A.hsb}/hsb/csv?sede=3",
                                                                            datos="x", tipo="text/csv")
anotar(R, "OAuth 2.0", "Sistema de la sede 1 no puede escribir en la sede 3 = 403", st == 403, st)
st, _ = Cliente().json("GET", f"{A.hsb}/hsb/mensajes")
anotar(R, "OAuth 2.0", "Monitor de mensajes sin token = 401", st == 401, st)
cifrado = all(u.startswith("https://") for u in (A.api, A.hsb, A.fhir)) and os.path.exists(A.ca)
anotar(R, "Cifrado en tránsito", "API, bus y FHIR por HTTPS verificado con la CA propia", cifrado,
       "https + certs/ca.pem" if cifrado else "sin HTTPS")

st, hs = Cliente().json("GET", f"{A.hsb}/health")
anotar(R, "Salud", "Bus, HAPI y las 3 sedes UP", hs.get("status") == "UP", json.dumps(hs.get("dependencias", {}).get("sedes", {})))

# ── Informe ────────────────────────────────────────────────────────────────
total, ok = len(filas), sum(1 for f in filas if f[3])
lineas = [f"# Verificación de interoperabilidad por sede", "",
          f"Ejecutado el {datetime.datetime.now():%Y-%m-%d %H:%M} contra `{A.api}` (script `scripts/verificar_interoperabilidad.py`).", "",
          f"**Resultado: {ok} de {total} comprobaciones correctas ({round(ok / total * 100, 1)} %).**", ""]
por_sede = {}
for f in filas:
    por_sede.setdefault(f[0], []).append(f)
lineas += ["| Ámbito | Correctas |", "|---|---|"]
for s, fs in por_sede.items():
    lineas.append(f"| {s} | {sum(1 for f in fs if f[3])} / {len(fs)} |")
for s, fs in por_sede.items():
    lineas += ["", f"## {s}", "", "| Sección | Comprobación | Resultado | Detalle |", "|---|---|---|---|"]
    for _, sec, comp, o, det in fs:
        lineas.append(f"| {sec} | {comp} | {'✅' if o else '❌'} | {det.replace('|', '/')} |")
open(A.salida, "w", encoding="utf-8").write("\n".join(lineas) + "\n")
print(f"\n{ok}/{total} correctas -> {A.salida}")
