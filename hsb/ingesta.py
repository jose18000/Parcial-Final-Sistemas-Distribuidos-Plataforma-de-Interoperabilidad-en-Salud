"""
hsb/ingesta.py
Flujo común de ingesta del HSB para cualquier formato de entrada.

    contenido ──traductor──> registro canónico ──> idempotencia ──> validación
              ──> Bundle FHIR ──> entrega (HAPI y sede) con reintentos

HL7 v2, CSV legado y JSON pasan por exactamente los mismos pasos; lo único que cambia
es la función del traductor universal que convierte la entrada.
"""

import json
from typing import Any, Dict, Optional, Tuple

from traductor.traductor import desde_hl7, desde_fila_csv, desde_json, leer_csv
from hsb.parser_csv import TABLA_TERMINOLOGIA
from hsb.validator import validar_mensaje_pre_transformacion, advertencias
from hsb.queue_manager import verificar_idempotencia, registrar_estado_mensaje, procesar_entrega_con_reintentos
from hsb.metrics import metrics
from fhir.normalizer import bundle_desde_registro

import hashlib


def contenido_csv(encabezado: str, linea: str) -> str:
    return json.dumps({"encabezado": encabezado, "linea": linea}, ensure_ascii=False)


def traducir_contenido(formato: str, contenido: str, sede: Optional[int]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Reconstruye (meta, registro) a partir del contenido original guardado en mensaje_bus."""
    if formato == "HL7_V2":
        return desde_hl7(contenido)
    if formato == "CSV":
        d = json.loads(contenido)
        fila, linea = leer_csv(d["encabezado"] + "\n" + d["linea"])[0]
        return desde_fila_csv(fila, int(sede), TABLA_TERMINOLOGIA, linea)
    if formato == "JSON":
        d = json.loads(contenido)
        return meta_json(d, int(sede) if sede else None), desde_json(d.get("registro", d), sede)
    raise ValueError(f"Formato desconocido: {formato}")


def meta_json(obj: Dict[str, Any], sede: Optional[int]) -> Dict[str, Any]:
    canonico = json.dumps(obj.get("registro", obj), sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256(f"S{sede}|{canonico}".encode("utf-8")).hexdigest()
    return {"formato": "JSON", "mensaje_id": obj.get("mensaje_id") or f"JSON-S{sede}-{h[:12]}",
            "tipo_mensaje": obj.get("tipo_mensaje") or "JSON_REGISTRO", "sede_origen": sede,
            "sede_raw": str(sede), "hash_contenido": h}


def enriquecer_con_existente(reg: Dict[str, Any], sede: int) -> Dict[str, Any]:
    """
    Un mensaje parcial (p. ej. un ORU con solo un laboratorio) no debe borrar en HAPI lo que la
    atención ya tenía: FHIR PUT reemplaza el recurso completo. Antes de armar el Bundle se completa
    el registro con lo que la sede ya guarda de ese paciente y esa visita (lo nuevo siempre gana).
    Si la sede no responde, se sigue con el mensaje tal cual (la entrega reintentará igual).
    """
    from db.repositorio import obtener_repositorio
    try:
        hist = obtener_repositorio(sede).historia(reg["usuario"]["documento_id"])
    except Exception:
        return reg
    if not hist:
        return reg
    for k, v in (hist.get("usuario") or {}).items():
        if v not in (None, "") and reg["usuario"].get(k) in (None, "") and k != "fhir_patient_id":
            reg["usuario"][k] = v
    visita = reg["atencion"].get("numero_visita")
    previa = next((a for a in hist.get("atenciones", []) if a.get("numero_visita") == visita), None)
    if not previa:
        return reg
    for k, v in previa.items():
        if k not in ("diagnosticos", "tecnologias", "egreso", "fhir_encounter_id") and v not in (None, "") \
                and reg["atencion"].get(k) in (None, ""):
            reg["atencion"][k] = v
    ids_dx = {d.get("diagnostico_id") for d in reg["diagnosticos"]}
    reg["diagnosticos"] += [dict(d, numero_visita=visita) for d in previa.get("diagnosticos", [])
                            if d.get("diagnostico_id") not in ids_dx]
    ids_t = {t.get("tecnologia_id") for t in reg["tecnologias"]}
    reg["tecnologias"] += [dict(t, numero_visita=visita) for t in previa.get("tecnologias", [])
                           if t.get("tecnologia_id") not in ids_t]
    if previa.get("egreso"):
        reg["egreso"] = {**previa["egreso"], **{k: v for k, v in reg["egreso"].items() if v not in (None, "")}}
    return reg


def procesar(meta: Dict[str, Any], reg: Dict[str, Any], contenido: str) -> Dict[str, Any]:
    """Idempotencia -> validación -> transformación -> entrega. Devuelve el resultado del mensaje."""
    metrics.registrar_recibido()
    mid, sede = meta["mensaje_id"], meta["sede_origen"]

    existente = verificar_idempotencia(mid, meta["hash_contenido"], sede)
    if existente and existente.get("estado") in ("ENTREGADO", "REINTENTANDO", "TRANSFORMADO"):
        metrics.registrar_duplicado()
        return {"estado": "duplicado", "mensaje_id": mid, "estado_original": existente.get("estado"),
                "bundle_id": existente.get("bundle_id"),
                "motivo": "Mensaje recibido previamente: no se vuelve a crear el paciente ni la atención."}

    registrar_estado_mensaje(mid, meta["formato"], sede, meta["tipo_mensaje"], "RECIBIDO",
                             meta["hash_contenido"], 0, None, None, contenido)
    parsed = {**meta, **reg}
    valido, motivos = validar_mensaje_pre_transformacion(parsed)
    if not valido:
        metrics.registrar_rechazado()
        registrar_estado_mensaje(mid, meta["formato"], sede, meta["tipo_mensaje"], "RECHAZADO",
                                 meta["hash_contenido"], 0, "; ".join(motivos), None, contenido)
        return {"estado": "rechazado", "mensaje_id": mid, "total_motivos": len(motivos), "motivos": motivos}
    registrar_estado_mensaje(mid, meta["formato"], sede, meta["tipo_mensaje"], "VALIDADO",
                             meta["hash_contenido"], 0, None, None, contenido)

    try:
        reg = enriquecer_con_existente(reg, sede)
        bundle = bundle_desde_registro(reg)
    except Exception as e:
        metrics.registrar_rechazado()
        motivo = f"Fallo al normalizar a FHIR R4: {e}"
        registrar_estado_mensaje(mid, meta["formato"], sede, meta["tipo_mensaje"], "RECHAZADO",
                                 meta["hash_contenido"], 0, motivo, None, contenido)
        return {"estado": "rechazado", "mensaje_id": mid, "motivos": [motivo]}

    resultado = procesar_entrega_con_reintentos(meta, reg, bundle, contenido)
    avisos = advertencias(parsed)
    if avisos:
        resultado["advertencias"] = avisos
    resultado["documento"] = reg["usuario"].get("documento_id")
    resultado["numero_visita"] = reg["atencion"].get("numero_visita")
    resultado["recursos_fhir"] = [f"{e['resource']['resourceType']}/{e['resource']['id']}" for e in bundle["entry"]]
    return resultado
