"""
hsb/parser_hl7.py
Lectura de mensajes HL7 v2.5 (ADT^A01, ORU^R01, RDE^O11).

La traducción campo a campo la hace el traductor universal (traductor/traductor.py,
función desde_hl7), guiado por traductor/catalogo_57.py. Este módulo mantiene la
interfaz que usa el resto del bus.
"""

from typing import Any, Dict

from traductor.traductor import desde_hl7

SEDE_MAP = {"SEDE1": 1, "SEDE2": 2, "SEDE3": 3, "1": 1, "2": 2, "3": 3}


def parse_hl7_message(raw_text: str) -> Dict[str, Any]:
    """Devuelve metadatos del mensaje + registro canónico en un solo diccionario."""
    meta, reg = desde_hl7(raw_text)
    return {**meta, **reg}
