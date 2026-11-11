"""
fhir/normalizer.py
Normalizador del registro canónico (57 campos, traductor universal) a un Bundle FHIR R4.

Reglas clave (guía Fase 2):
1. Ids deterministas: pac-<documento>, enc-<visita>, cond-<visita>-<rol>-<cie10>,
   obs-<visita>-<loinc>, med-<visita>-<hash>, prac-<código>, org-sede-<n>, alg-<documento>.
2. Bundle de tipo `transaction` con PUT: reenviar el mismo mensaje no duplica nada.
3. Toda referencia apunta a un recurso que viaja dentro del mismo Bundle.
4. Terminologías: CIE-10 en Condition, LOINC en Observation.

Recursos que produce:
    Organization (sede)   Practitioner (profesional)   Patient (campos 1-15, 51-57)
    Encounter (16-24, 40-50)   Condition (33-39)   MedicationRequest (25-32)
    Observation (laboratorio LOINC)   AllergyIntolerance (47)
"""

import os
import re
import datetime
from typing import Any, Dict, List, Optional

from traductor.catalogo_57 import SEDES
from traductor.dominios import etiqueta

CIE10_REGEX = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$")
LOINC_REGEX = re.compile(r"^[0-9]+-[0-9]+$")

FHIR_BASE = os.getenv("FHIR_FULLURL_BASE", "http://localhost:8090/fhir")
EXT = "https://minsalud.gov.co/fhir/StructureDefinition/"
CS = "https://minsalud.gov.co/fhir/CodeSystem/"

MAPA_SEXO = {"M": "male", "F": "female", "O": "other"}
MAPA_CLASE_ATENCION = {
    "E": {"code": "EMER", "display": "emergency"},
    "O": {"code": "AMB", "display": "ambulatory"},
    "I": {"code": "IMP", "display": "inpatient encounter"},
}
CLASE_POR_ENTORNO = {"01": "E", "02": "O", "03": "I", "04": "I", "05": "O", "06": "O"}


def formatear_fecha_iso(fecha_val: Any) -> Optional[str]:
    """YYYYMMDD[HHMM[SS]], YYYY-MM-DD[THH:MM[:SS]] o date/datetime -> ISO 8601."""
    if not fecha_val:
        return None
    if isinstance(fecha_val, (datetime.date, datetime.datetime)):
        return fecha_val.isoformat()
    s = str(fecha_val).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) >= 12 and s[:12].isdigit():
        seg = s[12:14] if len(s) >= 14 else "00"
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{seg}"
    return s


def _fecha_hora_fhir(valor: Any) -> Optional[str]:
    """dateTime FHIR: si trae hora debe llevar zona horaria (Colombia = -05:00)."""
    iso = formatear_fecha_iso(valor)
    if not iso:
        return None
    if "T" in iso and not re.search(r"(Z|[+-]\d{2}:\d{2})$", iso):
        if len(iso) == 16:
            iso += ":00"
        iso += "-05:00"
    return iso


def _ext(nombre: str, **valor) -> Dict[str, Any]:
    return {"url": EXT + nombre, **valor}


def _codigo(dominio: str, codigo: Any) -> Dict[str, Any]:
    return {"coding": [{"system": CS + dominio, "code": str(codigo),
                        "display": etiqueta(dominio, codigo) or str(codigo)}]}


def _ref(tipo: str, rid: str) -> Dict[str, str]:
    return {"reference": f"{tipo}/{rid}"}


def _id_seguro(texto: Any) -> str:
    return re.sub(r"[^A-Za-z0-9\-.]", "", str(texto))[:64]


# ── Patient ────────────────────────────────────────────────────────────────

def normalizar_paciente(usuario: Dict[str, Any]) -> Dict[str, Any]:
    doc = str(usuario.get("documento_id", "")).strip()
    if not doc:
        raise ValueError("El documento_id es obligatorio para construir Patient")
    if not doc.isdigit() or len(doc) < 4 or len(doc) > 15:
        raise ValueError(f"documento_id inválido ({doc}): debe ser numérico entre 4 y 15 dígitos")
    nombre = str(usuario.get("nombre_completo", "")).strip()
    if not nombre:
        raise ValueError("nombre_completo no puede ser vacío")

    family, given = usuario.get("apellidos"), usuario.get("nombres")
    if not family:
        partes = nombre.split("^") if "^" in nombre else nombre.split(" ")
        family, given = (partes[0], " ".join(partes[1:])) if "^" in nombre else (
            (" ".join(partes[1:]) or partes[0]), partes[0] if len(partes) > 1 else "")
    sexo = str(usuario.get("sexo", "")).upper()
    gender = MAPA_SEXO.get(sexo)
    if not gender:
        raise ValueError(f"Sexo no válido: '{sexo}'. Debe ser M, F u O")

    tipo_doc = usuario.get("tipo_documento") or "CC"
    res: Dict[str, Any] = {
        "resourceType": "Patient",
        "id": f"pac-{doc}",
        "identifier": [{
            "use": "official",
            "type": _codigo("tipo_documento", tipo_doc),
            "system": f"https://minsalud.gov.co/identificacion/{tipo_doc}",
            "value": doc,
        }],
        "active": True,
        "name": [{"use": "official", "text": " ".join(x for x in (given, family) if x) if family else nombre,
                  "family": family, **({"given": str(given).split(" ")} if given else {})}],
        "gender": gender,
    }
    if usuario.get("fecha_nacimiento"):
        res["birthDate"] = formatear_fecha_iso(usuario["fecha_nacimiento"])[:10]

    exts = []
    if usuario.get("pais_nacionalidad"):
        exts.append(_ext("nacionalidad", valueCode=usuario["pais_nacionalidad"]))
    if usuario.get("edad") is not None:
        unidad = {"1": ("a", "años"), "2": ("mo", "meses"), "3": ("d", "días")}.get(str(usuario.get("unidad_edad") or "1"))
        exts.append(_ext("edad", valueQuantity={"value": int(usuario["edad"]), "unit": unidad[1],
                                               "system": "http://unitsofmeasure.org", "code": unidad[0]}))
    for clave, dominio in (("genero", "genero"), ("categoria_discapacidad", "categoria_discapacidad"),
                           ("etnia", "etnia")):
        if usuario.get(clave):
            exts.append(_ext(clave.replace("_", "-"), valueCodeableConcept=_codigo(dominio, usuario[clave])))
    if usuario.get("ocupacion"):
        exts.append(_ext("ocupacion", valueString=usuario["ocupacion"]))
    if usuario.get("voluntad_anticipada") is not None:
        exts.append(_ext("voluntad-anticipada", valueBoolean=bool(usuario["voluntad_anticipada"])))
    if exts:
        res["extension"] = exts

    telecom = []
    if usuario.get("telefono"):
        telecom.append({"system": "phone", "value": str(usuario["telefono"]), "use": "mobile"})
    if usuario.get("correo_electronico"):
        telecom.append({"system": "email", "value": usuario["correo_electronico"], "use": "home"})
    if telecom:
        res["telecom"] = telecom

    direccion = usuario.get("direccion_residencia") or usuario.get("direccion")
    if any(usuario.get(k) for k in ("pais_residencia", "municipio_residencia", "zona_residencia")) or direccion:
        addr: Dict[str, Any] = {"use": "home"}
        if direccion:
            addr["line"] = [direccion]
            addr["text"] = direccion
        if usuario.get("municipio_residencia"):
            addr["district"] = usuario["municipio_residencia"]
        if usuario.get("pais_residencia"):
            addr["country"] = usuario["pais_residencia"]
        if usuario.get("zona_residencia"):
            addr["extension"] = [_ext("zona-residencia", valueCodeableConcept=_codigo(
                "zona_residencia", usuario["zona_residencia"]))]
        res["address"] = [addr]

    if usuario.get("nombre_responsable"):
        contacto: Dict[str, Any] = {"name": {"text": usuario["nombre_responsable"]}}
        if usuario.get("parentesco_responsable"):
            contacto["relationship"] = [_codigo("parentesco", usuario["parentesco_responsable"])]
        if usuario.get("telefono_responsable"):
            contacto["telecom"] = [{"system": "phone", "value": str(usuario["telefono_responsable"])}]
        res["contact"] = [contacto]

    sede = usuario.get("sede_origen_id")
    if sede and int(sede) in SEDES:
        res["managingOrganization"] = _ref("Organization", f"org-sede-{int(sede)}")
    return res


# ── Encounter ──────────────────────────────────────────────────────────────

def normalizar_atencion(atencion: Dict[str, Any], patient_id: str,
                        diagnosticos: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    visita = str(atencion.get("numero_visita", "")).strip()
    if not visita:
        raise ValueError("numero_visita es obligatorio para Encounter")
    egreso = atencion.get("egreso") or {}

    clase = str(atencion.get("clase_atencion") or CLASE_POR_ENTORNO.get(str(atencion.get("entorno_atencion")), "O")).upper()
    act = MAPA_CLASE_ATENCION.get(clase, MAPA_CLASE_ATENCION["O"])
    salida = egreso.get("fecha_salida") or atencion.get("fecha_egreso")
    terminada = bool(salida) or atencion.get("estado") == "FINALIZADA"

    res: Dict[str, Any] = {
        "resourceType": "Encounter",
        "id": f"enc-{_id_seguro(visita)}",
        "identifier": [{"system": "https://clinica.local/visitas", "value": visita}],
        "status": "finished" if terminada else "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", **act},
        "subject": _ref("Patient", patient_id),
    }
    if atencion.get("entorno_atencion"):
        res["serviceType"] = _codigo("entorno_atencion", atencion["entorno_atencion"])

    periodo = {}
    if atencion.get("fecha_ingreso"):
        periodo["start"] = _fecha_hora_fhir(atencion["fecha_ingreso"])
    if salida:
        periodo["end"] = _fecha_hora_fhir(salida)
    if periodo:
        res["period"] = periodo

    triage = atencion.get("clasificacion_triage") or atencion.get("triage")
    if triage:
        t = int(triage)
        res["priority"] = {"coding": [{"system": CS + "triage", "code": f"T{t}",
                                       "display": etiqueta("clasificacion_triage", str(t)) or f"Triage {t}"}]}
    if atencion.get("causa_atencion"):
        res["reasonCode"] = [{"text": atencion["causa_atencion"]}]

    sede = atencion.get("sede_id")
    if sede and int(sede) in SEDES:
        res["serviceProvider"] = {**_ref("Organization", f"org-sede-{int(sede)}"),
                                  "display": SEDES[int(sede)]["nombre"]}
    if atencion.get("codigo_profesional"):
        res["participant"] = [{"individual": _ref("Practitioner", f"prac-{_id_seguro(atencion['codigo_profesional'])}")}]

    hosp: Dict[str, Any] = {}
    if atencion.get("via_ingreso"):
        hosp["admitSource"] = _codigo("via_ingreso", atencion["via_ingreso"])
    if egreso.get("condicion_salida"):
        hosp["dischargeDisposition"] = _codigo("condicion_salida", egreso["condicion_salida"])
    if hosp:
        res["hospitalization"] = hosp

    exts = []
    if atencion.get("entidad_salud"):
        exts.append(_ext("entidad-salud", valueString=atencion["entidad_salud"]))
    if atencion.get("modalidad_entrega"):
        exts.append(_ext("modalidad-entrega", valueCodeableConcept=_codigo("modalidad_entrega", atencion["modalidad_entrega"])))
    if atencion.get("fecha_triage"):
        exts.append(_ext("fecha-triage", valueDateTime=_fecha_hora_fhir(atencion["fecha_triage"])))
    if atencion.get("comunidad_etnica"):
        exts.append(_ext("comunidad-etnica", valueString=atencion["comunidad_etnica"]))
    if egreso.get("diagnostico_muerte"):
        exts.append(_ext("diagnostico-muerte", valueCodeableConcept={"coding": [
            {"system": "http://hl7.org/fhir/sid/icd-10", "code": egreso["diagnostico_muerte"]}]}))
    if egreso.get("tipo_incapacidad") or egreso.get("dias_incapacidad"):
        sub = []
        if egreso.get("tipo_incapacidad"):
            sub.append({"url": "tipo", "valueCodeableConcept": _codigo("tipo_incapacidad", egreso["tipo_incapacidad"])})
        if egreso.get("dias_incapacidad") is not None:
            sub.append({"url": "dias", "valueInteger": int(egreso["dias_incapacidad"])})
        exts.append(_ext("incapacidad", extension=sub))
    if egreso.get("dias_lic_maternidad") is not None:
        exts.append(_ext("licencia-maternidad", valueInteger=int(egreso["dias_lic_maternidad"])))
    for clave in ("antecedentes_familiares", "riesgos_ocupacionales", "responsable_egreso"):
        if egreso.get(clave):
            exts.append(_ext(clave.replace("_", "-"), valueString=egreso[clave]))
    if egreso.get("codigo_prestador"):
        exts.append(_ext("codigo-prestador", valueString=egreso["codigo_prestador"]))
    if egreso.get("sello_hash"):
        exts.append(_ext("sello-egreso", valueString=egreso["sello_hash"]))
    if exts:
        res["extension"] = exts

    # Diagnósticos de ingreso (AD) y egreso (DD) enlazados a sus Condition
    diag = []
    for dx in diagnosticos or []:
        if dx.get("rol") in ("INGRESO", "EGRESO") and CIE10_REGEX.match(str(dx.get("cie10_codigo", ""))):
            uso = "AD" if dx["rol"] == "INGRESO" else "DD"
            diag.append({
                "condition": _ref("Condition", id_condition(dx, visita)),
                "use": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/diagnosis-role", "code": uso,
                                    "display": "Admission diagnosis" if uso == "AD" else "Discharge diagnosis"}]},
                "rank": 1 if str(dx.get("tipo_diagnostico", "01")) == "01" else 2,
            })
    if diag:
        res["diagnosis"] = diag
    return res


# ── Condition ──────────────────────────────────────────────────────────────

def id_condition(dx: Dict[str, Any], visita: str) -> str:
    if dx.get("diagnostico_id"):
        return _id_seguro(dx["diagnostico_id"])
    rol = str(dx.get("rol") or "INGRESO")[:3].lower()
    return f"cond-{_id_seguro(visita)}-{rol}-{_id_seguro(str(dx.get('cie10_codigo', '')).upper())}"


def normalizar_diagnostico(diagnostico: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    cie10 = str(diagnostico.get("cie10_codigo", "")).strip().upper()
    if not cie10 or not CIE10_REGEX.match(cie10):
        raise ValueError(f"Código CIE-10 inválido o ausente: '{cie10}'")
    visita = str(diagnostico.get("numero_visita") or encounter_id.replace("enc-", "", 1))
    desc = str(diagnostico.get("descripcion_cie10") or f"Diagnóstico CIE-10 {cie10}")
    rol = diagnostico.get("rol") or "INGRESO"
    res = {
        "resourceType": "Condition",
        "id": id_condition({**diagnostico, "cie10_codigo": cie10}, visita),
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                       "code": "active", "display": "Active"}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                           "code": "confirmed", "display": "Confirmed"}]},
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category",
                                  "code": "encounter-diagnosis", "display": "Encounter Diagnosis"}]}],
        "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": cie10, "display": desc}],
                 "text": desc},
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "extension": [_ext("rol-diagnostico", valueCode=rol),
                      _ext("tipo-diagnostico", valueCodeableConcept=_codigo(
                          "tipo_diagnostico", diagnostico.get("tipo_diagnostico") or "01"))],
    }
    if diagnostico.get("fecha_diagnostico"):
        res["recordedDate"] = formatear_fecha_iso(diagnostico["fecha_diagnostico"])[:10]
    return res


# ── Observation (laboratorio) y MedicationRequest (medicamento) ───────────

def normalizar_tecnologia(tecnologia: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    if (tecnologia.get("tipo") == "MEDICAMENTO") or (tecnologia.get("descripcion_medicamento") and not tecnologia.get("loinc_codigo")):
        return normalizar_medicamento(tecnologia, patient_id, encounter_id)
    loinc = str(tecnologia.get("loinc_codigo", "")).strip()
    if not loinc or not LOINC_REGEX.match(loinc):
        raise ValueError(f"Código LOINC inválido o ausente: '{loinc}'")
    visita = str(tecnologia.get("numero_visita") or encounter_id.replace("enc-", "", 1))
    desc = str(tecnologia.get("descripcion_loinc") or f"Observación {loinc}")
    unidad = str(tecnologia.get("unidad") or "1")
    fecha = _fecha_hora_fhir(tecnologia.get("fecha_toma")) or \
        datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    res = {
        "resourceType": "Observation",
        "id": _id_seguro(tecnologia.get("tecnologia_id") or f"obs-{visita}-{loinc}"),
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                  "code": "laboratory", "display": "Laboratory"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": desc}], "text": desc},
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "effectiveDateTime": fecha,
    }
    if tecnologia.get("valor") is not None:
        res["valueQuantity"] = {"value": float(tecnologia["valor"]), "unit": unidad,
                                "system": "http://unitsofmeasure.org", "code": unidad}
    return res


def normalizar_medicamento(tec: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    desc = tec.get("descripcion_medicamento")
    if not desc:
        raise ValueError("El medicamento necesita descripción (campo 25)")
    visita = str(tec.get("numero_visita") or encounter_id.replace("enc-", "", 1))
    dosis: Dict[str, Any] = {"text": " · ".join(str(x) for x in (desc, tec.get("dosis"), tec.get("frecuencia")) if x)}
    if tec.get("via_administracion"):
        dosis["route"] = _codigo("via_administracion", tec["via_administracion"])
    if tec.get("frecuencia"):
        dosis["timing"] = {"code": {"text": tec["frecuencia"]}}
    res: Dict[str, Any] = {
        "resourceType": "MedicationRequest",
        "id": _id_seguro(tec.get("tecnologia_id") or f"med-{visita}"),
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {"text": desc},
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "dosageInstruction": [dosis],
    }
    disp: Dict[str, Any] = {}
    if tec.get("unidades_aplicadas") is not None:
        disp["quantity"] = {"value": int(tec["unidades_aplicadas"]), "unit": "unidades"}
    if tec.get("dias_tratamiento") is not None:
        disp["expectedSupplyDuration"] = {"value": int(tec["dias_tratamiento"]), "unit": "días",
                                          "system": "http://unitsofmeasure.org", "code": "d"}
    if disp:
        res["dispenseRequest"] = disp
    if tec.get("id_personal_salud"):
        res["requester"] = _ref("Practitioner", f"prac-{_id_seguro(tec['id_personal_salud'])}")
    if tec.get("finalidad_tecnologia"):
        res["extension"] = [_ext("finalidad-tecnologia", valueCodeableConcept=_codigo(
            "finalidad_tecnologia", tec["finalidad_tecnologia"]))]
    return res


# ── Bundle ─────────────────────────────────────────────────────────────────

def _entrada(recurso: Dict[str, Any]) -> Dict[str, Any]:
    tipo, rid = recurso["resourceType"], recurso["id"]
    return {"fullUrl": f"{FHIR_BASE}/{tipo}/{rid}", "resource": recurso,
            "request": {"method": "PUT", "url": f"{tipo}/{rid}"}}


def _organizacion(sede: int) -> Dict[str, Any]:
    s = SEDES[sede]
    return {"resourceType": "Organization", "id": f"org-sede-{sede}", "active": True, "name": s["nombre"],
            "identifier": [{"system": "https://prestadores.minsalud.gov.co/reps", "value": s["codigo_prestador"]}],
            "address": [{"city": s["ciudad"], "district": s["municipio_dane"], "country": "CO"}]}


def _profesional(codigo: str) -> Dict[str, Any]:
    return {"resourceType": "Practitioner", "id": f"prac-{_id_seguro(codigo)}", "active": True,
            "identifier": [{"system": "https://clinica.local/profesionales", "value": str(codigo)}],
            "name": [{"text": str(codigo)}]}


def construir_bundle(usuario: Dict[str, Any], atenciones: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bundle transaction de un paciente a partir de la historia canónica:
    cada atención trae dentro sus `diagnosticos`, `tecnologias` y `egreso`.
    """
    paciente = normalizar_paciente(usuario)
    pid = paciente["id"]
    organizaciones, profesionales = set(), set()
    if usuario.get("sede_origen_id") and int(usuario["sede_origen_id"]) in SEDES:
        organizaciones.add(int(usuario["sede_origen_id"]))

    clinicas: List[Dict[str, Any]] = []
    alergias: List[str] = []
    for at in atenciones:
        dxs = [dict(d, numero_visita=d.get("numero_visita") or at.get("numero_visita")) for d in at.get("diagnosticos", [])]
        enc = normalizar_atencion(at, pid, dxs)
        clinicas.append(enc)
        if at.get("sede_id") and int(at["sede_id"]) in SEDES:
            organizaciones.add(int(at["sede_id"]))
        if at.get("codigo_profesional"):
            profesionales.add(str(at["codigo_profesional"]))
        for dx in dxs:
            clinicas.append(normalizar_diagnostico(dx, pid, enc["id"]))
        for t in at.get("tecnologias", []):
            t = dict(t, numero_visita=t.get("numero_visita") or at.get("numero_visita"))
            recurso = normalizar_tecnologia(t, pid, enc["id"])
            if recurso["resourceType"] == "MedicationRequest" and t.get("id_personal_salud"):
                profesionales.add(str(t["id_personal_salud"]))
            clinicas.append(recurso)
        texto_alergia = (at.get("egreso") or {}).get("alergias")
        if texto_alergia and not re.search(r"NINGUN|NO REFIERE|NIEGA", texto_alergia.upper()):
            alergias.append(texto_alergia)

    if alergias:
        clinicas.append({
            "resourceType": "AllergyIntolerance", "id": f"alg-{_id_seguro(usuario['documento_id'])}",
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                                           "code": "active"}]},
            "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                                               "code": "confirmed"}]},
            "code": {"text": "; ".join(sorted(set(alergias)))},
            "patient": _ref("Patient", pid),
        })

    recursos = [_organizacion(s) for s in sorted(organizaciones)] + \
               [_profesional(p) for p in sorted(profesionales)] + [paciente] + clinicas
    vistos, entradas = set(), []
    for r in recursos:
        llave = (r["resourceType"], r["id"])
        if llave not in vistos:
            vistos.add(llave)
            entradas.append(_entrada(r))
    return {"resourceType": "Bundle", "id": f"bundle-pac-{_id_seguro(usuario.get('documento_id'))}",
            "type": "transaction", "entry": entradas}


def construir_bundle_transaccional(
    usuario: Dict[str, Any],
    atenciones: List[Dict[str, Any]],
    diagnosticos: Optional[List[Dict[str, Any]]] = None,
    tecnologias: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Compatibilidad: acepta diagnósticos y tecnologías sueltos (se asignan a su atención por
    numero_visita) o atenciones que ya los traen anidados.
    """
    anidadas = []
    for at in atenciones:
        at = dict(at)
        visita = str(at.get("numero_visita"))
        if diagnosticos is not None and "diagnosticos" not in at:
            at["diagnosticos"] = [d for d in diagnosticos if str(d.get("numero_visita")) == visita]
        if tecnologias is not None and "tecnologias" not in at:
            at["tecnologias"] = [t for t in tecnologias if str(t.get("numero_visita")) == visita]
        at.setdefault("diagnosticos", [])
        at.setdefault("tecnologias", [])
        anidadas.append(at)
    return construir_bundle(usuario, anidadas)


def bundle_desde_registro(reg: Dict[str, Any]) -> Dict[str, Any]:
    """Registro canónico de UNA atención (lo que produce el traductor) -> Bundle."""
    at = dict(reg["atencion"])
    at["diagnosticos"] = reg.get("diagnosticos", [])
    at["tecnologias"] = reg.get("tecnologias", [])
    at["egreso"] = reg.get("egreso", {})
    return construir_bundle(reg["usuario"], [at] if at.get("numero_visita") else [])
