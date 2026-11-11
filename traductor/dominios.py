"""
traductor/dominios.py
Tablas de dominio (valores permitidos) de los 57 campos de la Resolución 866 de 2021.

Cada dominio guarda:
  - codigos:    código canónico -> etiqueta legible
  - sinonimos:  cualquier forma en que una sede puede enviar el valor -> código canónico
                (etiquetas, abreviaturas, códigos HL7 v2, números romanos, etc.)

`normalizar_codigo(dominio, valor)` es la traducción de VALORES del traductor universal:
recibe lo que mandó la sede (HL7, CSV, Mongo, formulario) y devuelve el código canónico.
"""

import unicodedata
from typing import Dict, Optional, Any


def _llave(texto: Any) -> str:
    """Mayúsculas, sin tildes y sin espacios sobrantes: 'Espontánea ' -> 'ESPONTANEA'."""
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.upper().replace("_", " ").split())


DOMINIOS: Dict[str, Dict[str, Dict[str, str]]] = {
    "tipo_documento": {
        "codigos": {
            "CC": "Cédula de ciudadanía", "TI": "Tarjeta de identidad", "CE": "Cédula de extranjería",
            "PA": "Pasaporte", "RC": "Registro civil", "MS": "Menor sin identificación",
            "AS": "Adulto sin identificación",
        },
        # HL7 tabla 0203: NI = national identifier, PPN = pasaporte, MR = historia clínica
        "sinonimos": {"NI": "CC", "PPN": "PA", "CEDULA": "CC", "HIS": "CC", "MR": "CC"},
    },
    # El profe exige M, F u O (guía Fase 3). La Res. 866 usa I (indeterminado): se traduce a O.
    "sexo": {
        "codigos": {"M": "Masculino", "F": "Femenino", "O": "Otro / indeterminado"},
        "sinonimos": {"I": "O", "INDETERMINADO": "O", "OTRO": "O", "MASCULINO": "M", "HOMBRE": "M",
                      "FEMENINO": "F", "MUJER": "F", "MALE": "M", "FEMALE": "F", "OTHER": "O"},
    },
    "genero": {
        "codigos": {"01": "Masculino", "02": "Femenino", "03": "Transgénero", "04": "No binario", "05": "Otro"},
        "sinonimos": {"M": "01", "F": "02", "O": "05", "TRANS": "03"},
    },
    "unidad_edad": {
        "codigos": {"1": "Años", "2": "Meses", "3": "Días"},
        "sinonimos": {"ANOS": "1", "A": "1", "MESES": "2", "DIAS": "3", "D": "3"},
    },
    "categoria_discapacidad": {
        "codigos": {"01": "Física", "02": "Visual", "03": "Auditiva", "04": "Intelectual",
                    "05": "Psicosocial (mental)", "06": "Sordoceguera", "07": "Múltiple", "08": "Sin discapacidad"},
        "sinonimos": {"MENTAL": "05", "SENSORIAL": "02", "NINGUNA": "08", "NO": "08"},
    },
    "etnia": {
        "codigos": {"01": "Indígena", "02": "ROM (gitano)", "03": "Raizal", "04": "Palenquero",
                    "05": "Negro, mulato, afrocolombiano", "06": "Ninguna de las anteriores"},
        "sinonimos": {"INDIGENA": "01", "GITANO": "02", "AFRO": "05", "AFROCOLOMBIANO": "05",
                      "NEGRO": "05", "OTRO": "06", "NINGUNA": "06"},
    },
    "modalidad_entrega": {
        "codigos": {"01": "Intramural", "02": "Extramural", "03": "Telemedicina interactiva",
                    "04": "Telemedicina no interactiva", "05": "Telexperticia", "06": "Telemonitoreo"},
        "sinonimos": {},
    },
    # El entorno se deduce de la clase de paciente HL7 (PV1-2): E, O, I.
    "entorno_atencion": {
        "codigos": {"01": "Urgencias", "02": "Consulta externa", "03": "Hospitalización",
                    "04": "Cirugía", "05": "Apoyo diagnóstico", "06": "Apoyo terapéutico"},
        "sinonimos": {"E": "01", "O": "02", "I": "03", "EMER": "01", "AMB": "02", "IMP": "03"},
    },
    "via_ingreso": {
        "codigos": {"01": "Espontánea", "02": "Remitido", "03": "Contrarremitido"},
        "sinonimos": {"CONTRAREMITIDO": "03"},
    },
    "clasificacion_triage": {
        "codigos": {"1": "I - Resucitación (rojo)", "2": "II - Emergencia (naranja)", "3": "III - Urgente (amarillo)",
                    "4": "IV - Menos urgente (verde)", "5": "V - No urgente (azul)"},
        "sinonimos": {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5"},
    },
    "via_administracion": {
        "codigos": {"01": "Oral", "02": "Intravenosa", "03": "Intramuscular", "04": "Subcutánea", "05": "Tópica",
                    "06": "Inhalatoria", "07": "Rectal", "08": "Oftálmica", "09": "Ótica", "10": "Nasal"},
        # HL7 tabla 0162 (route of administration)
        "sinonimos": {"PO": "01", "IV": "02", "IM": "03", "SC": "04", "TP": "05", "IH": "06", "PR": "07",
                      "OP": "08", "OT": "09", "NS": "10"},
    },
    "finalidad_tecnologia": {
        "codigos": {"01": "Terapéutica", "02": "Diagnóstica", "03": "Paliativa", "04": "Preventiva", "05": "Rehabilitación"},
        "sinonimos": {},
    },
    "tipo_diagnostico": {
        "codigos": {"01": "Principal", "02": "Relacionado", "03": "Complicación"},
        "sinonimos": {"PRINCIPAL": "01", "RELACIONADO": "02", "1": "01", "2": "02", "3": "02"},
    },
    "condicion_salida": {
        "codigos": {"01": "Vivo", "02": "Muerto"},
        # HL7 tabla 0112 (discharge disposition): 20 = expired; el resto sale vivo
        "sinonimos": {"ESTABLE": "01", "MEJORADO": "01", "20": "02", "FALLECIDO": "02",
                      "01": "01", "02": "01", "03": "01", "04": "01", "07": "01"},
    },
    "tipo_incapacidad": {
        "codigos": {"01": "Temporal", "02": "Permanente parcial", "03": "Permanente total"},
        "sinonimos": {"PERMANENTE": "02"},
    },
    "zona_residencia": {
        "codigos": {"01": "Urbana", "02": "Rural"},
        "sinonimos": {"U": "01", "R": "02"},
    },
    "parentesco": {
        "codigos": {"01": "Padre / madre", "02": "Hijo / hija", "03": "Esposo / esposa", "04": "Hermano / hermana",
                    "05": "Abuelo / abuela", "06": "Tío / tía", "07": "Otro"},
        # HL7 tabla 0063 (relationship)
        "sinonimos": {"PAR": "01", "MTH": "01", "FTH": "01", "MADRE": "01", "PADRE": "01", "CHD": "02",
                      "HIJO": "02", "HIJA": "02", "SPO": "03", "ESPOSO": "03", "ESPOSA": "03", "SIB": "04",
                      "GRP": "05", "OTH": "07"},
    },
}

# Construir índice de búsqueda: código, etiqueta y sinónimos -> código canónico
_INDICE: Dict[str, Dict[str, str]] = {}
for _nombre, _dom in DOMINIOS.items():
    idx: Dict[str, str] = {}
    for cod, etiqueta in _dom["codigos"].items():
        idx[_llave(cod)] = cod
        idx[_llave(etiqueta)] = cod
        # La etiqueta sin el prefijo romano del triage ("III - Urgente (amarillo)" -> "URGENTE")
        if " - " in etiqueta:
            idx[_llave(etiqueta.split(" - ", 1)[1].split(" (")[0])] = cod
    for sin, cod in _dom["sinonimos"].items():
        idx[_llave(sin)] = cod
    _INDICE[_nombre] = idx


class ValorFueraDeDominio(ValueError):
    """El valor recibido no corresponde a ningún código del dominio."""


def normalizar_codigo(dominio: str, valor: Any, estricto: bool = False) -> Optional[str]:
    """
    Traduce un valor de cualquier sede al código canónico del dominio.
    - Vacío -> None.
    - Valor desconocido -> ValorFueraDeDominio si estricto, si no None.
    """
    if valor is None or str(valor).strip() == "":
        return None
    if dominio not in _INDICE:
        return str(valor).strip()
    cod = _INDICE[dominio].get(_llave(valor))
    if cod is None and estricto:
        raise ValorFueraDeDominio(f"'{valor}' no es un valor válido para {dominio}")
    return cod


def etiqueta(dominio: str, codigo: Any) -> Optional[str]:
    """Devuelve la etiqueta legible de un código canónico."""
    if codigo is None:
        return None
    return DOMINIOS.get(dominio, {}).get("codigos", {}).get(str(codigo))


def triage_romano(codigo: Any) -> Optional[str]:
    """'3' -> 'III' (forma que usa la Res. 866 para la clasificación del triage)."""
    return {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V"}.get(str(codigo)) if codigo is not None else None
