"""
traductor/catalogo_57.py
Catálogo único de los 57 campos de la historia clínica interoperable (Resolución 866 de 2021).

Es la FUENTE DE VERDAD del traductor universal. Para cada campo dice:
  - num / nombre / grupo / obligatorio (según 57_CAMPOS_HC.md)
  - clave:       nombre canónico interno (el mismo en todo el sistema)
  - contenedor:  dónde vive dentro del registro canónico
                 usuario | atencion | tecnologia | diagnostico | egreso
  - dominio:     tabla de valores permitidos (traductor/dominios.py)
  - hl7:         de qué segmento/campo/componente de HL7 v2.5 sale
                 (los campos que HL7 v2 no trae van en segmentos Z: ZPI, ZPV, ZRX, ZEG)
  - csv:         columna del CSV legado (separador ';')
  - pg:          tabla.columna en los nodos PostgreSQL (sedes 1 y 3)
  - mongo:       ruta dentro del documento `pacientes` del nodo MongoDB (sede 2)
  - fhir:        elemento FHIR R4 donde termina

Los campos 33 a 39 (diagnósticos) son "virtuales": en las bases se guardan como filas de
`diagnostico` con un rol (INGRESO, EGRESO, RELACIONADO) y el traductor los reconstruye.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict

# ── Sedes de la red (código de habilitación REPS sintético) ────────────────
SEDES: Dict[int, Dict[str, str]] = {
    1: {"nombre": "IPS Sincelejo Central", "ciudad": "Sincelejo", "municipio_dane": "70001",
        "codigo_prestador": "700010000101", "motor": "postgresql"},
    2: {"nombre": "IPS Cartagena Bocagrande", "ciudad": "Cartagena", "municipio_dane": "13001",
        "codigo_prestador": "130010000202", "motor": "mongodb"},
    3: {"nombre": "IPS Corozal La Perla", "ciudad": "Corozal", "municipio_dane": "70215",
        "codigo_prestador": "702150000303", "motor": "postgresql"},
}


@dataclass(frozen=True)
class Campo:
    num: Optional[int]          # None = campo técnico (no es de los 57, pero el sistema lo necesita)
    clave: str
    nombre: str
    grupo: str
    contenedor: str
    obligatorio: bool
    tipo: str                   # texto | fecha | fechahora | entero | booleano | codigo | decimal
    dominio: Optional[str]
    hl7: Optional[str]
    csv: Optional[str]
    pg: Optional[str]
    mongo: Optional[str]
    fhir: str
    # Para los diagnósticos virtuales (33-39): rol y posición dentro de las filas
    rol_dx: Optional[str] = None
    atributo_dx: Optional[str] = None
    orden_dx: int = 1
    derivado: bool = False      # se calcula si la sede no lo envía (edad, unidad, prestador)


ID, AT, TS, DX, EG = ("Identificación del usuario", "Datos de la atención",
                      "Tecnologías en salud", "Diagnósticos", "Datos de egreso")

C = Campo  # alias corto para la tabla
CAMPOS_57: List[Campo] = [
    # ── 1. Identificación del usuario (1-15) ───────────────────────────────
    C(1, "tipo_documento", "Tipo de documento de identidad", ID, "usuario", True, "codigo", "tipo_documento",
      "PID-3.5", "tipo_documento", "usuario.tipo_documento", "identificacion.tipo", "Patient.identifier.type"),
    C(2, "documento_id", "Número de documento de identidad", ID, "usuario", True, "texto", None,
      "PID-3.1", "documento", "usuario.documento_id", "identificacion.numero", "Patient.identifier.value"),
    C(3, "pais_nacionalidad", "País de nacionalidad", ID, "usuario", True, "texto", None,
      "PID-28.1", "pais_nacionalidad", "usuario.pais_nacionalidad", "nacionalidad",
      "Patient.extension(nacionalidad)"),
    C(4, "nombre_completo", "Nombre completo", ID, "usuario", True, "texto", None,
      "PID-5", "nombre", "usuario.nombre_completo", "nombre.completo", "Patient.name"),
    C(5, "fecha_nacimiento", "Fecha de nacimiento", ID, "usuario", True, "fecha", None,
      "PID-7", "nacimiento", "usuario.fecha_nacimiento", "nacimiento.fecha", "Patient.birthDate"),
    C(6, "edad", "Edad", ID, "usuario", True, "entero", None,
      None, "edad", "usuario.edad", "nacimiento.edad", "Patient.extension(edad)", derivado=True),
    C(7, "unidad_edad", "Unidad de medida de la edad", ID, "usuario", True, "codigo", "unidad_edad",
      None, "unidad_edad", "usuario.unidad_edad", "nacimiento.unidad_edad", "Patient.extension(edad).unit",
      derivado=True),
    C(8, "sexo", "Sexo", ID, "usuario", True, "codigo", "sexo",
      "PID-8", "sexo", "usuario.sexo", "sexo_biologico", "Patient.gender"),
    C(9, "genero", "Género", ID, "usuario", False, "codigo", "genero",
      "ZPI-1", "genero", "usuario.genero", "identidad_genero", "Patient.extension(genero)"),
    C(10, "ocupacion", "Ocupación", ID, "usuario", False, "texto", None,
      "ZPI-2", "ocupacion", "usuario.ocupacion", "ocupacion", "Patient.extension(ocupacion)"),
    C(11, "voluntad_anticipada", "Voluntad anticipada", ID, "usuario", False, "booleano", None,
      "ZPI-3", "voluntad_anticipada", "usuario.voluntad_anticipada", "voluntad_anticipada",
      "Patient.extension(voluntad-anticipada)"),
    C(12, "categoria_discapacidad", "Categoría de discapacidad", ID, "usuario", False, "codigo",
      "categoria_discapacidad", "ZPI-4", "categoria_discapacidad", "usuario.categoria_discapacidad",
      "discapacidad", "Patient.extension(discapacidad)"),
    C(13, "pais_residencia", "País de residencia", ID, "usuario", True, "texto", None,
      "PID-11.6", "pais_residencia", "usuario.pais_residencia", "residencia.pais", "Patient.address.country"),
    C(14, "municipio_residencia", "Municipio de residencia (DANE)", ID, "usuario", True, "texto", None,
      "PID-11.9", "municipio_residencia", "usuario.municipio_residencia", "residencia.municipio_dane",
      "Patient.address.district"),
    C(15, "etnia", "Etnia", ID, "usuario", False, "codigo", "etnia",
      "PID-22.1", "etnia", "usuario.etnia", "pertenencia_etnica", "Patient.extension(etnia)"),

    # ── 2. Datos de la atención (16-24) ────────────────────────────────────
    C(16, "entidad_salud", "Entidad de salud (EPS)", AT, "atencion", True, "texto", None,
      "IN1-4.1", "entidad_salud", "atencion.entidad_salud", "aseguradora", "Encounter.extension(entidad-salud)"),
    C(17, "fecha_ingreso", "Fecha y hora de ingreso", AT, "atencion", True, "fechahora", None,
      "PV1-44", "fecha", "atencion.fecha_ingreso", "ingreso.fecha", "Encounter.period.start"),
    C(18, "modalidad_entrega", "Modalidad de entrega del servicio", AT, "atencion", True, "codigo",
      "modalidad_entrega", "ZPV-1", "modalidad_entrega", "atencion.modalidad_entrega", "ingreso.modalidad",
      "Encounter.extension(modalidad)"),
    C(19, "entorno_atencion", "Entorno de atención", AT, "atencion", True, "codigo", "entorno_atencion",
      "PV1-2", "entorno_atencion", "atencion.entorno_atencion", "ingreso.entorno", "Encounter.class"),
    C(20, "via_ingreso", "Vía de ingreso", AT, "atencion", True, "codigo", "via_ingreso",
      "PV1-14", "via_ingreso", "atencion.via_ingreso", "ingreso.via", "Encounter.hospitalization.admitSource"),
    C(21, "causa_atencion", "Causa de la atención", AT, "atencion", True, "texto", None,
      "PV2-3.2", "causa_atencion", "atencion.causa_atencion", "ingreso.causa", "Encounter.reasonCode.text"),
    C(22, "fecha_triage", "Fecha y hora del triage", AT, "atencion", False, "fechahora", None,
      "ZPV-2", "fecha_triage", "atencion.fecha_triage", "triage.fecha", "Encounter.extension(fecha-triage)"),
    C(23, "clasificacion_triage", "Clasificación del triage", AT, "atencion", False, "codigo",
      "clasificacion_triage", "ZPV-3", "triage", "atencion.clasificacion_triage", "triage.clasificacion",
      "Encounter.priority"),
    C(24, "comunidad_etnica", "Comunidad étnica", AT, "atencion", False, "texto", None,
      "ZPI-6", "comunidad_etnica", "atencion.comunidad_etnica", "comunidad_etnica",
      "Encounter.extension(comunidad-etnica)"),

    # ── 3. Tecnologías en salud (25-32): medicamento formulado ─────────────
    C(25, "descripcion_medicamento", "Descripción del medicamento", TS, "tecnologia", False, "texto", None,
      "RXE-2.2", "medicamento", "tecnologia_salud.descripcion_medicamento", "medicamento",
      "MedicationRequest.medicationCodeableConcept.text"),
    C(26, "dosis", "Dosis", TS, "tecnologia", False, "texto", None,
      "RXE-3 + RXE-5", "dosis", "tecnologia_salud.dosis", "dosis", "MedicationRequest.dosageInstruction.text"),
    C(27, "via_administracion", "Vía de administración", TS, "tecnologia", False, "codigo", "via_administracion",
      "RXR-1.1", "via_administracion", "tecnologia_salud.via_administracion", "via",
      "MedicationRequest.dosageInstruction.route"),
    C(28, "frecuencia", "Frecuencia", TS, "tecnologia", False, "texto", None,
      "RXE-1.2", "frecuencia", "tecnologia_salud.frecuencia", "frecuencia",
      "MedicationRequest.dosageInstruction.timing.code.text"),
    C(29, "dias_tratamiento", "Días de tratamiento", TS, "tecnologia", False, "entero", None,
      "RXE-1.3", "dias_tratamiento", "tecnologia_salud.dias_tratamiento", "dias_tratamiento",
      "MedicationRequest.dispenseRequest.expectedSupplyDuration"),
    C(30, "unidades_aplicadas", "Unidades aplicadas", TS, "tecnologia", False, "entero", None,
      "RXE-10", "unidades_aplicadas", "tecnologia_salud.unidades_aplicadas", "unidades",
      "MedicationRequest.dispenseRequest.quantity"),
    C(31, "id_personal_salud", "Identificación del personal de salud", TS, "tecnologia", False, "texto", None,
      "ORC-12.1", "id_personal_salud", "tecnologia_salud.id_personal_salud", "prescriptor",
      "MedicationRequest.requester"),
    C(32, "finalidad_tecnologia", "Finalidad de la tecnología", TS, "tecnologia", False, "codigo",
      "finalidad_tecnologia", "ZRX-1", "finalidad_tecnologia", "tecnologia_salud.finalidad_tecnologia",
      "finalidad", "MedicationRequest.extension(finalidad)"),

    # ── 3b/4. Diagnósticos (33-39): filas de `diagnostico` con rol ─────────
    C(33, "tipo_diagnostico_ingreso", "Tipo de diagnóstico de ingreso", TS, "diagnostico", False, "codigo",
      "tipo_diagnostico", "DG1-15 (DG1-6=A)", "tipo_dx", "diagnostico.tipo_diagnostico [rol=INGRESO]",
      "diagnosticos[rol=INGRESO].tipo", "Encounter.diagnosis(AD).rank",
      rol_dx="INGRESO", atributo_dx="tipo_diagnostico"),
    C(34, "diagnostico_ingreso", "Diagnóstico de ingreso (CIE-10)", TS, "diagnostico", False, "codigo", None,
      "DG1-3.1 (DG1-6=A)", "dx_local → CIE-10", "diagnostico.cie10_codigo [rol=INGRESO]",
      "diagnosticos[rol=INGRESO].cie10", "Condition.code + Encounter.diagnosis(AD)",
      rol_dx="INGRESO", atributo_dx="cie10_codigo"),
    C(35, "tipo_diagnostico_egreso", "Tipo de diagnóstico de egreso", TS, "diagnostico", False, "codigo",
      "tipo_diagnostico", "DG1-15 (DG1-6=F)", None, "diagnostico.tipo_diagnostico [rol=EGRESO]",
      "diagnosticos[rol=EGRESO].tipo", "Encounter.diagnosis(DD).rank",
      rol_dx="EGRESO", atributo_dx="tipo_diagnostico"),
    C(36, "diagnostico_egreso", "Diagnóstico de egreso (CIE-10)", DX, "diagnostico", True, "codigo", None,
      "DG1-3.1 (DG1-6=F)", None, "diagnostico.cie10_codigo [rol=EGRESO]",
      "diagnosticos[rol=EGRESO].cie10", "Condition.code + Encounter.diagnosis(DD)",
      rol_dx="EGRESO", atributo_dx="cie10_codigo"),
    C(37, "diagnostico_rel1", "Diagnóstico relacionado 1", DX, "diagnostico", False, "codigo", None,
      "DG1-3.1 (DG1-15=2)", None, "diagnostico.cie10_codigo [rol=RELACIONADO, orden=1]",
      "diagnosticos[rol=RELACIONADO][0].cie10", "Condition.code",
      rol_dx="RELACIONADO", atributo_dx="cie10_codigo", orden_dx=1),
    C(38, "diagnostico_rel2", "Diagnóstico relacionado 2", DX, "diagnostico", False, "codigo", None,
      "DG1-3.1 (DG1-15=3)", None, "diagnostico.cie10_codigo [rol=RELACIONADO, orden=2]",
      "diagnosticos[rol=RELACIONADO][1].cie10", "Condition.code",
      rol_dx="RELACIONADO", atributo_dx="cie10_codigo", orden_dx=2),
    C(39, "diagnostico_rel3", "Diagnóstico relacionado 3", DX, "diagnostico", False, "codigo", None,
      "DG1-3.1 (DG1-15=4)", None, "diagnostico.cie10_codigo [rol=RELACIONADO, orden=3]",
      "diagnosticos[rol=RELACIONADO][2].cie10", "Condition.code",
      rol_dx="RELACIONADO", atributo_dx="cie10_codigo", orden_dx=3),

    # ── 5. Datos de egreso (40-50) ─────────────────────────────────────────
    C(40, "fecha_salida", "Fecha y hora de salida", EG, "egreso", True, "fechahora", None,
      "PV1-45", "fecha_salida", "egreso.fecha_salida", "egreso.fecha", "Encounter.period.end"),
    C(41, "condicion_salida", "Condición de salida", EG, "egreso", True, "codigo", "condicion_salida",
      "PV1-36", "condicion_salida", "egreso.condicion_salida", "egreso.condicion",
      "Encounter.hospitalization.dischargeDisposition"),
    C(42, "diagnostico_muerte", "Diagnóstico de muerte (CIE-10)", EG, "egreso", False, "codigo", None,
      "ZEG-1", "diagnostico_muerte", "egreso.diagnostico_muerte", "egreso.diagnostico_muerte",
      "Encounter.extension(diagnostico-muerte)"),
    C(43, "codigo_prestador", "Código del prestador", EG, "egreso", True, "texto", None,
      "MSH-4 → REPS", "codigo_prestador", "egreso.codigo_prestador", "egreso.codigo_prestador",
      "Organization.identifier", derivado=True),
    C(44, "tipo_incapacidad", "Tipo de incapacidad", EG, "egreso", False, "codigo", "tipo_incapacidad",
      "ZEG-2", "tipo_incapacidad", "egreso.tipo_incapacidad", "egreso.incapacidad.tipo",
      "Encounter.extension(incapacidad)"),
    C(45, "dias_incapacidad", "Días de incapacidad", EG, "egreso", False, "entero", None,
      "ZEG-3", "dias_incapacidad", "egreso.dias_incapacidad", "egreso.incapacidad.dias",
      "Encounter.extension(incapacidad)"),
    C(46, "dias_lic_maternidad", "Días de licencia de maternidad", EG, "egreso", False, "entero", None,
      "ZEG-4", "dias_lic_maternidad", "egreso.dias_lic_maternidad", "egreso.licencia_maternidad_dias",
      "Encounter.extension(licencia-maternidad)"),
    C(47, "alergias", "Alergias", EG, "egreso", False, "texto", None,
      "AL1-3.2", "alergias", "egreso.alergias", "egreso.alergias", "AllergyIntolerance.code.text"),
    C(48, "antecedentes_familiares", "Antecedentes familiares", EG, "egreso", False, "texto", None,
      "ZEG-5", "antecedentes_familiares", "egreso.antecedentes_familiares", "egreso.antecedentes_familiares",
      "Encounter.extension(antecedentes-familiares)"),
    C(49, "riesgos_ocupacionales", "Riesgos ocupacionales", EG, "egreso", False, "texto", None,
      "ZEG-6", "riesgos_ocupacionales", "egreso.riesgos_ocupacionales", "egreso.riesgos_ocupacionales",
      "Encounter.extension(riesgos-ocupacionales)"),
    C(50, "responsable_egreso", "Responsable del egreso", EG, "egreso", True, "texto", None,
      "ZEG-7", "responsable_egreso", "egreso.responsable_egreso", "egreso.responsable",
      "Encounter.participant(DIS)"),

    # ── 5b. Residencia y contacto (51-57): se guardan con el usuario ───────
    C(51, "zona_residencia", "Zona de residencia", EG, "usuario", True, "codigo", "zona_residencia",
      "ZPI-7", "zona_residencia", "usuario.zona_residencia", "residencia.zona",
      "Patient.address.extension(zona)"),
    C(52, "direccion_residencia", "Dirección de residencia", EG, "usuario", True, "texto", None,
      "PID-11.1", "direccion", "usuario.direccion_residencia", "residencia.direccion", "Patient.address.line"),
    C(53, "telefono", "Teléfono", EG, "usuario", False, "texto", None,
      "PID-13.1", "telefono", "usuario.telefono", "contacto.telefono", "Patient.telecom(phone)"),
    C(54, "correo_electronico", "Correo electrónico", EG, "usuario", False, "texto", None,
      "PID-13.4", "correo", "usuario.correo_electronico", "contacto.correo", "Patient.telecom(email)"),
    C(55, "nombre_responsable", "Nombre del responsable", EG, "usuario", False, "texto", None,
      "NK1-2", "nombre_responsable", "usuario.nombre_responsable", "responsable.nombre", "Patient.contact.name"),
    C(56, "parentesco_responsable", "Parentesco del responsable", EG, "usuario", False, "codigo", "parentesco",
      "NK1-3.1", "parentesco_responsable", "usuario.parentesco_responsable", "responsable.parentesco",
      "Patient.contact.relationship"),
    C(57, "telefono_responsable", "Teléfono del responsable", EG, "usuario", False, "texto", None,
      "NK1-5.1", "telefono_responsable", "usuario.telefono_responsable", "responsable.telefono",
      "Patient.contact.telecom"),
]

# ── Campos técnicos: no son de los 57 pero el sistema los necesita ─────────
T = "Técnico"
CAMPOS_TECNICOS: List[Campo] = [
    C(None, "apellidos", "Apellidos", T, "usuario", False, "texto", None,
      "PID-5.1", "apellidos", "usuario.apellidos", "nombre.apellidos", "Patient.name.family"),
    C(None, "nombres", "Nombres", T, "usuario", False, "texto", None,
      "PID-5.2", "nombres", "usuario.nombres", "nombre.nombres", "Patient.name.given"),
    C(None, "fhir_patient_id", "Id FHIR del paciente", T, "usuario", False, "texto", None,
      None, None, "usuario.fhir_patient_id", "fhir_patient_id", "Patient.id"),
    C(None, "sede_origen_id", "Sede donde se registró", T, "usuario", False, "entero", None,
      "MSH-4", None, "usuario.sede_origen_id", "sede_origen", "Patient.managingOrganization"),
    C(None, "numero_visita", "Número de visita", T, "atencion", False, "texto", None,
      "PV1-19.1", None, "atencion.numero_visita", "numero_visita", "Encounter.identifier"),
    C(None, "clase_atencion", "Clase de paciente HL7 (E/O/I)", T, "atencion", False, "texto", None,
      "PV1-2", None, "atencion.clase_atencion", "clase_hl7", "Encounter.class"),
    C(None, "codigo_profesional", "Profesional que atiende", T, "atencion", False, "texto", None,
      "PV1-7.1", "profesional", "atencion.codigo_profesional", "profesional.codigo", "Encounter.participant"),
    C(None, "sede_id", "Sede de la atención", T, "atencion", False, "entero", None,
      "MSH-4", None, "atencion.sede_id", "sede", "Encounter.serviceProvider"),
    C(None, "estado", "Estado de la atención", T, "atencion", False, "texto", None,
      None, None, "atencion.estado", "estado", "Encounter.status"),
    C(None, "fhir_encounter_id", "Id FHIR de la atención", T, "atencion", False, "texto", None,
      None, None, "atencion.fhir_encounter_id", "fhir_encounter_id", "Encounter.id"),
    C(None, "tecnologia_id", "Id de la tecnología", T, "tecnologia", False, "texto", None,
      None, None, "tecnologia_salud.tecnologia_id", "id", "MedicationRequest.id / Observation.id"),
    C(None, "tipo", "MEDICAMENTO o LABORATORIO", T, "tecnologia", False, "texto", None,
      None, None, "tecnologia_salud.tipo", "tipo", "resourceType"),
    C(None, "loinc_codigo", "Prueba de laboratorio (LOINC)", T, "tecnologia", False, "texto", None,
      "OBX-3.1", None, "tecnologia_salud.loinc_codigo", "loinc", "Observation.code"),
    C(None, "descripcion_loinc", "Nombre de la prueba", T, "tecnologia", False, "texto", None,
      "OBX-3.2", None, "tecnologia_salud.descripcion_loinc", "prueba", "Observation.code.text"),
    C(None, "valor", "Resultado", T, "tecnologia", False, "decimal", None,
      "OBX-5", None, "tecnologia_salud.valor", "resultado.valor", "Observation.valueQuantity.value"),
    C(None, "unidad", "Unidad del resultado", T, "tecnologia", False, "texto", None,
      "OBX-6.1", None, "tecnologia_salud.unidad", "resultado.unidad", "Observation.valueQuantity.unit"),
    C(None, "fecha_toma", "Fecha de toma", T, "tecnologia", False, "fechahora", None,
      "OBX-14", None, "tecnologia_salud.fecha_toma", "fecha", "Observation.effectiveDateTime"),
    C(None, "fhir_resource_id", "Id FHIR de la tecnología", T, "tecnologia", False, "texto", None,
      None, None, "tecnologia_salud.fhir_resource_id", "fhir_id", "Observation.id / MedicationRequest.id"),
    C(None, "diagnostico_id", "Id del diagnóstico", T, "diagnostico", False, "texto", None,
      None, None, "diagnostico.diagnostico_id", "id", "Condition.id"),
    C(None, "cie10_codigo", "Código CIE-10", T, "diagnostico", False, "texto", None,
      "DG1-3.1", "dx_local", "diagnostico.cie10_codigo", "cie10", "Condition.code"),
    C(None, "descripcion_cie10", "Descripción CIE-10", T, "diagnostico", False, "texto", None,
      "DG1-3.2", None, "diagnostico.descripcion_cie10", "descripcion", "Condition.code.text"),
    C(None, "rol", "INGRESO / EGRESO / RELACIONADO", T, "diagnostico", False, "texto", None,
      "DG1-6", None, "diagnostico.rol", "rol", "Encounter.diagnosis.use"),
    C(None, "tipo_diagnostico", "Principal / relacionado / complicación", T, "diagnostico", False, "codigo",
      "tipo_diagnostico", "DG1-15", None, "diagnostico.tipo_diagnostico", "tipo", "Encounter.diagnosis.rank"),
    C(None, "orden", "Posición entre los relacionados", T, "diagnostico", False, "entero", None,
      "DG1-15", None, "diagnostico.orden", "orden", "Encounter.diagnosis.rank"),
    C(None, "fecha_diagnostico", "Fecha del diagnóstico", T, "diagnostico", False, "fecha", None,
      "DG1-5", None, "diagnostico.fecha_diagnostico", "fecha", "Condition.recordedDate"),
    C(None, "fhir_condition_id", "Id FHIR del diagnóstico", T, "diagnostico", False, "texto", None,
      None, None, "diagnostico.fhir_condition_id", "fhir_id", "Condition.id"),
    C(None, "sello_hash", "Sello SHA-256 del egreso", T, "egreso", False, "texto", None,
      None, None, "egreso.sello_hash", "egreso.sello", "Encounter.meta.tag(sello)"),
]

TODOS: List[Campo] = CAMPOS_57 + CAMPOS_TECNICOS

assert len(CAMPOS_57) == 57, "El catálogo debe tener exactamente 57 campos"
assert [c.num for c in CAMPOS_57] == list(range(1, 58)), "Los campos deben ir numerados del 1 al 57"

POR_NUM: Dict[int, Campo] = {c.num: c for c in CAMPOS_57}
OBLIGATORIOS: List[Campo] = [c for c in CAMPOS_57 if c.obligatorio]


def campos_de(contenedor: str, incluir_tecnicos: bool = True, solo_reales: bool = True) -> List[Campo]:
    """
    Campos que viven físicamente en un contenedor.
    solo_reales=True excluye los diagnósticos virtuales 33-39 (no son columnas propias).
    """
    lista = TODOS if incluir_tecnicos else CAMPOS_57
    return [c for c in lista if c.contenedor == contenedor and not (solo_reales and c.rol_dx)]
