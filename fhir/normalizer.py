"""
fhir/normalizer.py
Normalizador de entidades relacionales clínicas a Bundle transaction FHIR R4.

Reglas clave:
1. IDs deterministas (pac-<doc>, enc-<visita>, cond-<visita>-<cie10>, obs-<visita>-<loinc>)
2. Bundle de tipo 'transaction' con método 'PUT': idempotencia matemática
3. Referencias internas consistentes (todas las referencias existen dentro del Bundle)
4. Codificación estándar: CIE-10 en Condition y LOINC en Observation
"""

import re
import datetime
from typing import Dict, Any, List, Optional


CIE10_REGEX = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$")
LOINC_REGEX = re.compile(r"^[0-9]+-[0-9]+$")

MAPA_SEXO = {
    "M": "male",
    "F": "female",
    "O": "other"
}

MAPA_CLASE_ATENCION = {
    "E": {"code": "EMER", "display": "emergency"},
    "O": {"code": "AMB", "display": "ambulatory"},
    "I": {"code": "IMP", "display": "inpatient encounter"}
}


def formatear_fecha_iso(fecha_val: Any) -> Optional[str]:
    """Formatea una fecha o timestamp a formato ISO 8601 (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SSZ)."""
    if not fecha_val:
        return None
    if isinstance(fecha_val, (datetime.date, datetime.datetime)):
        return fecha_val.isoformat()
    fecha_str = str(fecha_val).strip()
    # Si viene formato HL7 compacto (YYYYMMDD o YYYYMMDDHHMMSS)
    if len(fecha_str) == 8 and fecha_str.isdigit():
        return f"{fecha_str[0:4]}-{fecha_str[4:6]}-{fecha_str[6:8]}"
    if len(fecha_str) >= 12 and fecha_str[:12].isdigit():
        return f"{fecha_str[0:4]}-{fecha_str[4:6]}-{fecha_str[6:8]}T{fecha_str[8:10]}:{fecha_str[10:12]}:00Z"
    return fecha_str


def normalizar_paciente(usuario: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convierte registro de usuario en un recurso Patient de FHIR R4.
    ID determinista: pac-{documento_id}
    """
    doc = str(usuario.get("documento_id", "")).strip()
    if not doc:
        raise ValueError("El documento_id es obligatorio para construir Patient")
    if not doc.isdigit() or len(doc) < 4 or len(doc) > 15:
        raise ValueError(f"documento_id inválido ({doc}): debe ser numérico entre 4 y 15 dígitos")

    nombre_completo = str(usuario.get("nombre_completo", "")).strip()
    if not nombre_completo:
        raise ValueError("nombre_completo no puede ser vacío")

    # Separación de apellido y nombre
    partes = nombre_completo.split("^") if "^" in nombre_completo else nombre_completo.split(" ")
    if len(partes) >= 2:
        family = partes[0]
        given = partes[1:]
    else:
        family = partes[0]
        given = [partes[0]]

    sexo_raw = str(usuario.get("sexo", "")).upper()
    gender = MAPA_SEXO.get(sexo_raw)
    if not gender:
        raise ValueError(f"Sexo no válido: '{sexo_raw}'. Debe ser M, F u O")

    patient_id = f"pac-{doc}"
    birth_date = formatear_fecha_iso(usuario.get("fecha_nacimiento"))

    resource = {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [
            {
                "use": "official",
                "system": "https://minsalud.gov.co/identificacion-pacientes",
                "value": doc
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "family": family,
                "given": given
            }
        ],
        "gender": gender
    }

    if birth_date:
        # Asegurar sólo fecha en YYYY-MM-DD
        resource["birthDate"] = birth_date[:10]

    if usuario.get("telefono"):
        resource["telecom"] = [
            {
                "system": "phone",
                "value": str(usuario["telefono"]),
                "use": "mobile"
            }
        ]

    if usuario.get("direccion"):
        resource["address"] = [
            {
                "use": "home",
                "text": str(usuario["direccion"])
            }
        ]

    return resource


def normalizar_atencion(atencion: Dict[str, Any], patient_id: str) -> Dict[str, Any]:
    """
    Convierte registro de atencion en Encounter de FHIR R4.
    ID determinista: enc-{numero_visita}
    """
    visita = str(atencion.get("numero_visita", "")).strip()
    if not visita:
        raise ValueError("numero_visita es obligatorio para Encounter")

    encounter_id = f"enc-{visita}"
    clase_raw = str(atencion.get("clase_atencion", "O")).upper()
    act_code = MAPA_CLASE_ATENCION.get(clase_raw, {"code": "AMB", "display": "ambulatory"})

    fecha_ingreso = formatear_fecha_iso(atencion.get("fecha_ingreso"))
    fecha_egreso = formatear_fecha_iso(atencion.get("fecha_egreso"))

    status = "finished" if atencion.get("fecha_egreso") or atencion.get("estado") == "FINALIZADA" else "in-progress"

    resource = {
        "resourceType": "Encounter",
        "id": encounter_id,
        "identifier": [
            {
                "system": "https://clinica.local/visitas",
                "value": visita
            }
        ],
        "status": status,
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": act_code["code"],
            "display": act_code["display"]
        },
        "subject": {
            "reference": f"Patient/{patient_id}"
        }
    }

    period = {}
    if fecha_ingreso:
        period["start"] = fecha_ingreso
    if fecha_egreso:
        period["end"] = fecha_egreso
    if period:
        resource["period"] = period

    if atencion.get("sede_id"):
        resource["serviceProvider"] = {
            "reference": f"Organization/org-sede-{atencion['sede_id']}",
            "display": f"Sede {atencion['sede_id']}"
        }

    if atencion.get("triage"):
        triage_val = int(atencion["triage"])
        resource["priority"] = {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActPriority",
                    "code": f"T{triage_val}",
                    "display": f"Triage {triage_val}"
                }
            ]
        }

    return resource


def normalizar_diagnostico(diagnostico: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    """
    Convierte registro de diagnostico a Condition de FHIR R4 con CIE-10.
    ID determinista: cond-{numero_visita}-{clean_cie10}
    """
    cie10 = str(diagnostico.get("cie10_codigo", "")).strip().upper()
    if not cie10 or not CIE10_REGEX.match(cie10):
        raise ValueError(f"Código CIE-10 inválido o ausente: '{cie10}'")

    visita = str(diagnostico.get("numero_visita", "")).strip()
    clean_code = re.sub(r"[^A-Za-z0-9]", "", cie10)
    cond_id = f"cond-{visita}-{clean_code}"

    desc = str(diagnostico.get("descripcion_cie10", f"Diagnóstico CIE-10 {cie10}"))

    resource = {
        "resourceType": "Condition",
        "id": cond_id,
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                    "display": "Active"
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": "confirmed",
                    "display": "Confirmed"
                }
            ]
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "encounter-diagnosis",
                        "display": "Encounter Diagnosis"
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/icd-10",
                    "code": cie10,
                    "display": desc
                }
            ],
            "text": desc
        },
        "subject": {
            "reference": f"Patient/{patient_id}"
        },
        "encounter": {
            "reference": f"Encounter/{encounter_id}"
        }
    }

    if diagnostico.get("fecha_diagnostico"):
        resource["recordedDate"] = formatear_fecha_iso(diagnostico["fecha_diagnostico"])[:10]

    return resource


def normalizar_tecnologia(tecnologia: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    """
    Convierte tecnología en salud / laboratorio en Observation de FHIR R4 con LOINC.
    ID determinista: obs-{numero_visita}-{clean_loinc}
    """
    loinc = str(tecnologia.get("loinc_codigo", "")).strip()
    if not loinc or not LOINC_REGEX.match(loinc):
        raise ValueError(f"Código LOINC inválido o ausente: '{loinc}'")

    visita = str(tecnologia.get("numero_visita", "")).strip()
    clean_loinc = re.sub(r"[^A-Za-z0-9]", "", loinc)
    obs_id = f"obs-{visita}-{clean_loinc}"

    desc = str(tecnologia.get("descripcion_loinc", f"Observación {loinc}"))
    valor = float(tecnologia.get("valor", 0.0))
    unidad = str(tecnologia.get("unidad", "1"))

    fecha_toma = formatear_fecha_iso(tecnologia.get("fecha_toma")) or datetime.datetime.utcnow().isoformat() + "Z"

    resource = {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                        "display": "Laboratory"
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": loinc,
                    "display": desc
                }
            ],
            "text": desc
        },
        "subject": {
            "reference": f"Patient/{patient_id}"
        },
        "encounter": {
            "reference": f"Encounter/{encounter_id}"
        },
        "effectiveDateTime": fecha_toma,
        "valueQuantity": {
            "value": valor,
            "unit": unidad,
            "system": "http://unitsofmeasure.org",
            "code": unidad
        }
    }

    return resource


def construir_bundle_transaccional(
    usuario: Dict[str, Any],
    atenciones: List[Dict[str, Any]],
    diagnosticos: Optional[List[Dict[str, Any]]] = None,
    tecnologias: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Construye un Bundle transaction FHIR R4 completo con métodos PUT y referencias deterministas.
    """
    patient_res = normalizar_paciente(usuario)
    patient_id = patient_res["id"]

    entries = [
        {
            "fullUrl": f"urn:uuid:{patient_id}",
            "resource": patient_res,
            "request": {
                "method": "PUT",
                "url": f"Patient/{patient_id}"
            }
        }
    ]

    diagnosticos = diagnosticos or []
    tecnologias = tecnologias or []

    for atencion in atenciones:
        enc_res = normalizar_atencion(atencion, patient_id)
        enc_id = enc_res["id"]
        visita = atencion.get("numero_visita")

        entries.append({
            "fullUrl": f"urn:uuid:{enc_id}",
            "resource": enc_res,
            "request": {
                "method": "PUT",
                "url": f"Encounter/{enc_id}"
            }
        })

        # Diagnósticos de esta atención
        dxs_visita = [d for d in diagnosticos if str(d.get("numero_visita")) == str(visita)]
        for dx in dxs_visita:
            cond_res = normalizar_diagnostico(dx, patient_id, enc_id)
            cond_id = cond_res["id"]
            entries.append({
                "fullUrl": f"urn:uuid:{cond_id}",
                "resource": cond_res,
                "request": {
                    "method": "PUT",
                    "url": f"Condition/{cond_id}"
                }
            })

        # Tecnologías / Labs de esta atención
        techs_visita = [t for t in tecnologias if str(t.get("numero_visita")) == str(visita)]
        for tech in techs_visita:
            obs_res = normalizar_tecnologia(tech, patient_id, enc_id)
            obs_id = obs_res["id"]
            entries.append({
                "fullUrl": f"urn:uuid:{obs_id}",
                "resource": obs_res,
                "request": {
                    "method": "PUT",
                    "url": f"Observation/{obs_id}"
                }
            })

    bundle_id = f"bundle-pac-{usuario.get('documento_id')}"
    return {
        "resourceType": "Bundle",
        "id": bundle_id,
        "type": "transaction",
        "entry": entries
    }
