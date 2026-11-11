"""
docs/coleccion/generar_coleccion.py
Genera la colección de pruebas de Postman (formato v2.1) de la plataforma y sus entornos.

    python docs/coleccion/generar_coleccion.py

Salida (misma carpeta):
    Plataforma_Interoperabilidad.postman_collection.json
    entorno_kali.postman_environment.json      (VM Kali 192.168.1.94)
    entorno_local.postman_environment.json     (localhost)

Los mensajes HL7/CSV se toman de ejemplos/ (los del docente, sin modificar) y de tests/datos/.
Cada petición trae pruebas (pm.test) con el resultado esperado del LEEME.md del docente.
Se ejecuta en Postman ("Run collection") o con Newman:
    npx newman run Plataforma_Interoperabilidad.postman_collection.json -e entorno_kali.postman_environment.json
"""

import json
import os
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8", newline="") as f:
        return f.read()


def pruebas(*lineas):
    return [{"listen": "test", "script": {"type": "text/javascript", "exec": list(lineas)}}]


def pre(*lineas):
    return [{"listen": "prerequest", "script": {"type": "text/javascript", "exec": list(lineas)}}]


def peticion(nombre, metodo, url, cuerpo=None, tipo="text/plain", eventos=None, auth=None, descripcion="",
             form=None, seguir_redirecciones=True):
    req = {"method": metodo, "header": [], "url": url, "description": descripcion}
    if cuerpo is not None:
        req["header"].append({"key": "Content-Type", "value": tipo})
        req["body"] = {"mode": "raw", "raw": cuerpo}
    if form is not None:
        req["body"] = {"mode": "urlencoded", "urlencoded": [{"key": k, "value": v} for k, v in form.items()]}
    if auth:
        req["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": "{{" + auth + "}}", "type": "string"}]}
    else:
        req["auth"] = {"type": "noauth"}
    # Sin cookies: cada petición se autentica solo con el token de su rol (si no, la cookie del último
    # inicio de sesión se colaría en todas las peticiones y las pruebas de 401/403 no serían reales).
    item = {"name": nombre, "request": req, "event": eventos or [],
            "protocolProfileBehavior": {"disableCookies": True}}
    if not seguir_redirecciones:
        item["protocolProfileBehavior"]["followRedirects"] = False
    return item


def carpeta(nombre, descripcion, items):
    return {"name": nombre, "description": descripcion, "item": items}


def login(rol, usuario, clave, variable):
    return peticion(
        f"Iniciar sesión · {rol} ({usuario})", "POST", "{{api}}/auth/login",
        form={"username": usuario, "password": clave}, seguir_redirecciones=False,
        descripcion=f"Obtiene el JWT del rol {rol} (cookie access_token) y lo guarda en la variable {variable}.",
        eventos=pruebas(
            "pm.test('Credenciales aceptadas (303)', () => pm.response.to.have.status(303));",
            "const c = pm.response.headers.all().filter(h => h.key.toLowerCase() === 'set-cookie').map(h => h.value).join(';');",
            "const m = c.match(/access_token=([^;]+)/);",
            "pm.test('Entrega el token JWT', () => pm.expect(m, 'cookie access_token').to.not.be.null);",
            f"if (m) pm.collectionVariables.set('{variable}', m[1].replace(/^\"|\"$/g, ''));",
        ))


ESTADO_OK = "pm.expect(['entregado','duplicado','reintentando']).to.include(r.estado);"

coleccion = {
    "info": {
        "_postman_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "parcial-sd-interop/coleccion")),
        "name": "Plataforma de Interoperabilidad Clínica · Red de IPS",
        "description": (
            "Colección de pruebas del parcial final de Sistemas Distribuidos.\n\n"
            "Sedes: 1 Sincelejo (PostgreSQL), 2 Cartagena (MongoDB), 3 Corozal (PostgreSQL). "
            "HSB en {{hsb}}, API y vistas en {{api}}, HAPI FHIR R4 en {{fhir}}.\n\n"
            "Ejecute las carpetas en orden (Run collection). Los mensajes oficiales del docente vienen de ejemplos/ "
            "sin modificar. Si el sistema ya tenía los ejemplos cargados, el bus responde 'duplicado': las pruebas "
            "lo aceptan porque eso demuestra la idempotencia.\n\n"
            "Pruebas que necesitan apagar contenedores (reintento con HAPI caído, mensaje muerto, caída de una "
            "sede, alteración de la auditoría) están en el README y en docs/guion_demostracion.md."),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [{"key": k, "value": ""} for k in ("token_medico", "token_paciente", "token_admision",
                                                   "token_auditor", "token_admin", "token_admin_sede2",
                                                   "usuario_nuevo")],
    "item": [
        carpeta("0. Salud y métricas", "GET /health y /metrics de cada servicio (requisito no funcional).", [
            peticion("HSB /health", "GET", "{{hsb}}/health", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('Reporta las 3 sedes con su motor', () => { pm.expect(Object.keys(r.dependencias.sedes)).to.have.length(3);"
                " pm.expect(r.dependencias.sedes.sede_2.motor).to.eql('mongodb'); });",
                "pm.test('Reporta HAPI FHIR', () => pm.expect(r.dependencias).to.have.property('hapi_fhir_r4'));")),
            peticion("HSB /metrics", "GET", "{{hsb}}/metrics", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Expone latencia, % fallidos, duplicados y mensajes por estado', () => {",
                "  ['latencia_media_ms','porcentaje_fallidos','total_duplicados_detectados','mensajes_ultimo_minuto','mensajes_por_estado_persistidos']",
                "    .forEach(k => pm.expect(r).to.have.property(k)); });")),
            peticion("API /health", "GET", "{{api}}/health", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('200 y 3 sedes', () => { pm.response.to.have.status(200); pm.expect(r.nodos_activos).to.match(/\\/3$/); });")),
            peticion("API /metrics (cobertura FHIR y auditoría)", "GET", "{{api}}/metrics", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Cobertura FHIR por sede', () => pm.expect(Object.keys(r.cobertura_fhir_por_sede)).to.have.length(3));",
                "pm.test('Cadena de auditoría íntegra', () => pm.expect(r.auditoria_cadena_integra).to.eql(true));")),
            peticion("HAPI FHIR CapabilityStatement", "GET", "{{fhir}}/metadata", eventos=pruebas(
                "pm.test('FHIR 4.0.1', () => pm.expect(pm.response.json().fhirVersion).to.eql('4.0.1'));")),
        ]),
        carpeta("1. HSB · mensajes oficiales del docente", "Resultados esperados de ejemplos/LEEME.md.", [
            peticion("01 ADT^A01 válido · sede 2 (MongoDB)", "POST", "{{hsb}}/hsb/hl7",
                     leer("ejemplos/01_adt_a01_valido_sede2.hl7"), eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Entregado (o duplicado si ya existía)', () => { " + ESTADO_OK + " });",
                "pm.test('Mensaje MSG-0001', () => pm.expect(r.mensaje_id).to.eql('MSG-0001'));")),
            peticion("01 reenviado · idempotencia", "POST", "{{hsb}}/hsb/hl7",
                     leer("ejemplos/01_adt_a01_valido_sede2.hl7"), eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('El bus responde duplicado', () => pm.expect(r.estado).to.eql('duplicado'));")),
            peticion("02 ORU^R01 laboratorio · sede 1 (PostgreSQL)", "POST", "{{hsb}}/hsb/hl7",
                     leer("ejemplos/02_oru_r01_laboratorio_sede1.hl7"), eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Entregado (o duplicado)', () => { " + ESTADO_OK + " });")),
            peticion("03 ADT^A01 inválido · 3 motivos", "POST", "{{hsb}}/hsb/hl7",
                     leer("ejemplos/03_adt_a01_invalido.hl7"), eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('422 rechazado', () => { pm.response.to.have.status(422); pm.expect(r.estado).to.eql('rechazado'); });",
                "pm.test('Exactamente 3 motivos', () => pm.expect(r.motivos).to.have.length(3));",
                "pm.test('Documento, sexo y diagnóstico', () => { const t = r.motivos.join(' | ');",
                "  ['documento no numérico','sexo no válido','sin mapeo a CIE-10'].forEach(x => pm.expect(t).to.include(x)); });")),
            peticion("04 CSV legado · sede 3", "POST", "{{hsb}}/hsb/csv?sede=3",
                     leer("ejemplos/04_sede3_legado.csv"), tipo="text/csv", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('5 filas', () => pm.expect(r.total_filas).to.eql(5));",
                "pm.test('3 válidas (entregadas o duplicadas): 1008, 1009, 1010', () =>",
                "  pm.expect(r.total_entregados + r.total_duplicados).to.eql(3));",
                "pm.test('2 rechazadas: dx sin mapeo y documento de 2 dígitos', () => {",
                "  pm.expect(r.total_rechazados).to.eql(2);",
                "  const t = JSON.stringify(r.rechazados); pm.expect(t).to.include('sin mapeo'); pm.expect(t).to.include('2 dígitos'); });")),
        ]),
        carpeta("2. Traductor universal de 57 campos", "Mensaje HL7 con todos los campos de la Res. 866 (segmentos Z) y registro JSON.", [
            peticion("ADT^A03 con los 57 campos · sede 1", "POST", "{{hsb}}/hsb/hl7",
                     leer("tests/datos/06_adt_a03_57_campos_sede1.hl7"), eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Entregado (o duplicado)', () => { " + ESTADO_OK + " });",
                "if (r.recursos_fhir) pm.test('Genera MedicationRequest y AllergyIntolerance', () => {",
                "  const t = r.recursos_fhir.join(' '); pm.expect(t).to.include('MedicationRequest'); pm.expect(t).to.include('AllergyIntolerance'); });")),
            peticion("Registro JSON por número de campo · sede 2", "POST", "{{hsb}}/hsb/json?sede=2",
                     json.dumps({"tipo_mensaje": "PRUEBA_POSTMAN", "registro": {
                         "1": "CC", "2": "{{doc_json}}", "3": "CO", "4": "Lucía Pérez Gómez", "5": "1990-05-17",
                         "8": "F", "13": "CO", "14": "13001", "16": "Coosalud EPS", "17": "2026-11-11T09:30",
                         "18": "01", "19": "01", "20": "01", "21": "Dolor abdominal", "23": "3", "34": "K29.7",
                         "51": "01", "52": "Calle 30 # 10-20, Cartagena", "53": "3001234567"}}, ensure_ascii=False, indent=2),
                     tipo="application/json",
                     eventos=pre("pm.collectionVariables.set('doc_json', String(Math.floor(70000000 + Math.random()*9999999)));") +
                     pruebas("const r = pm.response.json();",
                             "pm.test('Entregado en la sede 2', () => pm.expect(r.estado).to.eql('entregado'));",
                             "pm.test('Paciente y atención publicados en FHIR', () => {",
                             "  pm.expect(r.recursos_fhir.join(' ')).to.include('Patient/pac-'); pm.expect(r.recursos_fhir.join(' ')).to.include('Condition/'); });")),
            peticion("Catálogo de los 57 campos", "GET", "{{hsb}}/hsb/catalogo", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('57 campos con destino HL7/CSV/PostgreSQL/MongoDB/FHIR', () => {",
                "  pm.expect(r.total).to.eql(57); ['hl7','pg','mongo','fhir'].forEach(k => pm.expect(r.campos[13]).to.have.property(k)); });")),
        ]),
        carpeta("3. Cola del bus", "Estados persistidos en la base de cada sede.", [
            peticion("Mensajes recientes de las 3 sedes", "GET", "{{hsb}}/hsb/mensajes?limite=20", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Lista mensajes con estado y motor', () => { pm.expect(r.mensajes.length).to.be.above(0);",
                "  pm.expect(r.mensajes[0]).to.have.property('estado'); pm.expect(r.mensajes[0]).to.have.property('motor'); });")),
            peticion("Mensajes rechazados (con motivo)", "GET", "{{hsb}}/hsb/mensajes?estado=RECHAZADO", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Ninguno se pierde: todos guardan motivo', () => r.mensajes.forEach(m => pm.expect(m.motivo_rechazo).to.be.a('string')));")),
            peticion("Reencolar un mensaje que no está muerto", "POST", "{{hsb}}/hsb/reencolar/MSG-0001", eventos=pruebas(
                "pm.test('Informa que no está MUERTO', () => pm.expect(pm.response.text()).to.include('no está MUERTO'));")),
        ]),
        carpeta("4. Autenticación", "Un token JWT por rol (se guardan como variables de la colección).", [
            login("médico", "medico_mateo", "Medico123!", "token_medico"),
            login("paciente", "paciente_carlos", "Paciente123!", "token_paciente"),
            login("admisionista", "admision_laura", "Admision123!", "token_admision"),
            login("auditor", "auditor_elena", "Auditor123!", "token_auditor"),
            login("administrador general", "admin_plataforma", "Admin123!", "token_admin"),
            login("administrador sede 2", "admin_cartagena", "Admin123!", "token_admin_sede2"),
            peticion("Credenciales inválidas", "POST", "{{api}}/auth/login", form={"username": "medico_mateo", "password": "mala"},
                     seguir_redirecciones=False, eventos=pruebas("pm.test('401', () => pm.response.to.have.status(401));")),
        ]),
        carpeta("5. Consulta unificada y FHIR", "Historia del paciente 1001 en las 3 sedes y 2 motores; Bundle validado por HAPI.", [
            peticion("Historia unificada de 1001 (médico)", "GET", "{{api}}/api/pacientes/1001/historia", auth="token_medico",
                     eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('Registros en las 3 sedes', () => pm.expect(r.sedes_con_registros).to.have.members([1,2,3]));",
                "pm.test('Atenciones de PostgreSQL y de MongoDB', () => { const m = r.atenciones.map(a => a.motor_origen);",
                "  pm.expect(m).to.include('postgresql'); pm.expect(m).to.include('mongodb'); });",
                "pm.test('100 % de los campos obligatorios', () => pm.expect(r.cobertura_57.porcentaje_obligatorios).to.eql(100));")),
            peticion("Bundle FHIR de 1001", "GET", "{{api}}/api/pacientes/1001/bundle", auth="token_medico", eventos=pruebas(
                "const b = pm.response.json();",
                "pm.test('Bundle transaction con PUT', () => { pm.expect(b.type).to.eql('transaction');",
                "  b.entry.forEach(e => pm.expect(e.request.method).to.eql('PUT')); });",
                "pm.collectionVariables.set('bundle_1001', JSON.stringify(b));")),
            peticion("Validar el Bundle en HAPI ($validate)", "POST", "{{fhir}}/Bundle/$validate", "{{bundle_1001}}",
                     tipo="application/fhir+json", eventos=pruebas(
                "const r = pm.response.json();",
                "const errores = (r.issue || []).filter(i => ['error','fatal'].includes(i.severity));",
                "pm.test('0 errores de validación', () => pm.expect(errores).to.have.length(0));")),
            peticion("Patient 1007 en HAPI: uno solo", "GET", "{{fhir}}/Patient?identifier=1007&_summary=count", eventos=pruebas(
                "pm.test('Sin duplicados', () => pm.expect(pm.response.json().total).to.eql(1));")),
            peticion("Observation LOINC 718-7 = 13,8 g/dL", "GET", "{{fhir}}/Observation/obs-V-S1-0150-718-7", eventos=pruebas(
                "const o = pm.response.json();",
                "pm.test('718-7 en g/dL', () => { pm.expect(o.code.coding[0].code).to.eql('718-7'); pm.expect(o.valueQuantity.unit).to.eql('g/dL'); });")),
        ]),
        carpeta("6. Permisos por rol (permitido y denegado)", "Matriz de la Fase 4: un 403 deja evento en la auditoría.", [
            peticion("Paciente ve su propia historia", "GET", "{{api}}/api/pacientes/1001/historia", auth="token_paciente",
                     eventos=pruebas("pm.test('200', () => pm.response.to.have.status(200));")),
            peticion("Paciente pide la historia de otro (1002)", "GET", "{{api}}/api/pacientes/1002/historia", auth="token_paciente",
                     eventos=pruebas("pm.test('403', () => pm.response.to.have.status(403));")),
            peticion("Admisionista pide una historia clínica", "GET", "{{api}}/api/pacientes/1001/historia", auth="token_admision",
                     eventos=pruebas("pm.test('403', () => pm.response.to.have.status(403));")),
            peticion("Auditor consulta la historia (reporte)", "GET", "{{api}}/api/pacientes/1001/historia", auth="token_auditor",
                     eventos=pruebas("pm.test('200', () => pm.response.to.have.status(200));")),
            peticion("Médico intenta ver eventos de auditoría", "GET", "{{api}}/api/auditoria/eventos", auth="token_medico",
                     eventos=pruebas("pm.test('403', () => pm.response.to.have.status(403));")),
            peticion("Sin token", "GET", "{{api}}/api/pacientes/1001/historia",
                     eventos=pruebas("pm.test('401', () => pm.response.to.have.status(401));")),
        ]),
        carpeta("7. Auditoría encadenada", "Verificador de la cadena SHA-256 y últimos eventos (incluye los 403 de la carpeta anterior).", [
            peticion("Verificar la cadena", "GET", "{{api}}/api/auditoria/verificar", auth="token_auditor", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Cadena íntegra', () => pm.expect(r.cadena_integra).to.eql(true));")),
            peticion("Últimos eventos", "GET", "{{api}}/api/auditoria/eventos?limite=20", auth="token_auditor", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Los accesos denegados quedaron registrados', () =>",
                "  pm.expect(r.map(e => e.tipo_evento)).to.include('ACCESO_DENEGADO'));",
                "pm.test('Cada evento tiene su hash', () => r.forEach(e => pm.expect(e.hash_propio).to.have.length(64)));")),
        ]),
        carpeta("8. Panel de administración y usuarios", "Alcance: el administrador de una sede solo gestiona su sede; el auditor solo consulta.", [
            peticion("Resumen del panel", "GET", "{{api}}/api/panel/resumen", auth="token_admin", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('Indicadores, sedes, bus, FHIR y auditoría', () => ['kpis','sedes','bus','fhir','auditoria'].forEach(k => pm.expect(r).to.have.property(k)));")),
            peticion("Buscar paciente en las 3 sedes", "GET", "{{api}}/api/panel/pacientes?q=1001", auth="token_admin", eventos=pruebas(
                "const r = pm.response.json();",
                "pm.test('1001 aparece en 3 sedes', () => pm.expect(r.pacientes[0].sedes).to.have.length(3));")),
            peticion("Admin sede 2 crea un médico en su sede", "POST", "{{api}}/api/panel/usuarios",
                     json.dumps({"username": "{{usuario_nuevo}}", "nombre_completo": "Dra. Postman Prueba",
                                 "rol": "medico", "documento_id": "MED-PM", "sede_id": 2}, indent=2),
                     tipo="application/json", auth="token_admin_sede2",
                     eventos=pre("pm.collectionVariables.set('usuario_nuevo', 'med.pm' + Date.now().toString().slice(-6));") +
                     pruebas("const r = pm.response.json();",
                             "pm.test('Creado con contraseña temporal', () => { pm.expect(r.ok).to.eql(true); pm.expect(r.clave_temporal).to.have.length(12); });",
                             "pm.test('Origen PANEL, creado por admin_cartagena', () => { pm.expect(r.usuario.origen).to.eql('PANEL');"
                             " pm.expect(r.usuario.creado_por).to.eql('admin_cartagena'); pm.expect(r.usuario.debe_cambiar_clave).to.eql(true); });")),
            peticion("Admin sede 2 intenta crear en la sede 1", "POST", "{{api}}/api/panel/usuarios",
                     json.dumps({"username": "intruso.sede1", "nombre_completo": "X", "rol": "medico",
                                 "documento_id": "M", "sede_id": 1}, indent=2),
                     tipo="application/json", auth="token_admin_sede2",
                     eventos=pruebas("pm.test('403', () => pm.response.to.have.status(403));")),
            peticion("Auditor intenta crear un usuario", "POST", "{{api}}/api/panel/usuarios",
                     json.dumps({"username": "intento.auditor", "nombre_completo": "X", "rol": "medico",
                                 "documento_id": "M", "sede_id": 2}, indent=2),
                     tipo="application/json", auth="token_auditor",
                     eventos=pruebas("pm.test('403', () => pm.response.to.have.status(403));")),
            peticion("Desactivar el médico creado", "POST", "{{api}}/api/panel/usuarios/{{usuario_nuevo}}/estado",
                     json.dumps({"activo": False}), tipo="application/json", auth="token_admin_sede2",
                     eventos=pruebas("pm.test('Inactivo', () => pm.expect(pm.response.json().usuario.activo).to.eql(false));")),
            peticion("Listar usuarios (admin sede 2 ve solo su sede)", "GET", "{{api}}/api/panel/usuarios", auth="token_admin_sede2",
                     eventos=pruebas("const r = pm.response.json();",
                                     "pm.test('Todos de la sede 2', () => r.usuarios.forEach(u => pm.expect(u.sede_id).to.eql(2)));")),
        ]),
    ],
}


def entorno(nombre, host):
    return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, nombre)), "name": nombre, "_postman_variable_scope": "environment",
            "values": [{"key": "api", "value": f"http://{host}:8000", "enabled": True},
                       {"key": "hsb", "value": f"http://{host}:8001", "enabled": True},
                       {"key": "fhir", "value": f"http://{host}:8090/fhir", "enabled": True}]}


if __name__ == "__main__":
    salida = {
        "Plataforma_Interoperabilidad.postman_collection.json": coleccion,
        "entorno_kali.postman_environment.json": entorno("Plataforma · VM Kali (192.168.1.94)", "192.168.1.94"),
        "entorno_local.postman_environment.json": entorno("Plataforma · localhost", "localhost"),
    }
    for nombre, datos in salida.items():
        with open(os.path.join(AQUI, nombre), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        print("escrito", nombre)
    total = sum(len(c["item"]) for c in coleccion["item"])
    print(f"{len(coleccion['item'])} carpetas, {total} peticiones")
