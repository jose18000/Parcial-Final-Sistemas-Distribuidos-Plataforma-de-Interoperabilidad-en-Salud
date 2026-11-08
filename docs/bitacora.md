# Bitácora del proyecto — Plataforma de Interoperabilidad Clínica

> Se registra aquí cada sesión de trabajo, uso de IA, código abierto reutilizado y correcciones entre fases.
> Formato: `AAAA-MM-DD | Integrante | Actividad | Herramientas/IA usadas`

---

## Fase 1 · Análisis, UML y diseño

| Fecha | Integrante | Actividad | IA / Código abierto |
|-------|-----------|-----------|---------------------|
| 2026-11-08 | A — Jose Canchila | Configuración del repositorio: `.gitignore`, `.env.example`, `README.md`, `docker-compose.yml` esqueleto, estructura de carpetas | Antigravity (Google DeepMind) — generación de estructura base y plantillas |
| 2026-11-08 | A — Jose Canchila | Diagramas UML: casos de uso, secuencia, clases y estados del mensaje (Mermaid) | Antigravity — generación de código Mermaid; revisión manual de coherencia entre diagramas |
| 2026-11-08 | B — Sharit Manjarrez | Marco teórico, tabla de mapeo de campos (≥15 filas), tabla de justificación de componentes | Antigravity — asistencia en redacción; conceptos verificados contra fuentes indicadas en la guía |
| 2026-11-08 | A + B | Revisión cruzada de diagramas e informe Fase 1; respuesta a pregunta de autoevaluación | — |

### Uso declarado de IA en Fase 1
- **Herramienta:** Antigravity (Google DeepMind) vía IDE integrado.
- **Uso:** Generación de código Mermaid para los 4 diagramas UML, estructura de archivos, plantillas markdown y borrador del informe.
- **Revisión humana:** Todos los diagramas fueron revisados manualmente para garantizar coherencia entre actores, clases y estados. Los conceptos del marco teórico fueron verificados por los integrantes.
- **Código abierto:** No se reutilizó código de terceros en Fase 1 (solo documentación).

---

## Fase 2 · Datos distribuidos y FHIR

| Fecha | Integrante | Actividad | IA / Código abierto |
|-------|-----------|-----------|---------------------|
| 2026-11-08 | A — Jose Canchila | Infraestructura docker-compose con 3 nodos PostgreSQL y HAPI FHIR R4; esquema relacional unificado `db/schema.sql` y scripts de inicialización `db/sede1..3/init.sql` | Antigravity — generación y validación de scripts SQL y docker-compose |
| 2026-11-08 | A — Jose Canchila | Demostración de atomicidad ACID (`db/demo_acid.sql`) y script de consulta unificada distribuida (`db/consulta_unificada.py`) | Antigravity — soporte en diseño del patrón scatter-gather |
| 2026-11-08 | B — Sharit Manjarrez | Normalizador determinista a FHIR R4 (`fhir/normalizer.py`), suite de pruebas unitarias (`tests/fase2/test_normalizer.py`) y generación de `bundle_valido.json` | Antigravity — revisión de especificación FHIR R4 y mapeos de terminología |
| 2026-11-08 | B — Sharit Manjarrez | Estado del arte con 8 fuentes (global/LatAm/Colombia), justificación CAP y redacción del informe de Fase 2 | Antigravity — asistencia en investigación y redacción técnica |
| 2026-11-08 | A + B | Revisión cruzada de esquemas, validación de datos sintéticos del paciente 1001 en las 3 sedes y respuesta a pregunta de autoevaluación | — |

### Uso declarado de IA en Fase 2
- **Herramienta:** Antigravity (Google DeepMind) vía IDE integrado.
- **Uso:** Asistencia en la generación de esquemas DDL relacionales, estructuración del módulo normalizador FHIR R4 según estándar oficial HL7, redacción de casos de prueba unitaria y síntesis comparativa del estado del arte.
- **Revisión humana:** Se validó manualmente que el paciente 1001 existiera de forma consistente en las 3 sedes con fhir_patient_id nulo, que los identificadores de recursos sean deterministas, y que la consulta unificada tolere fallos de nodo degradando a reporte incompleto.
- **Código abierto:** PostgreSQL 16 Alpine, HAPI FHIR v7.2.0 (Apache 2.0).*

---

## Fase 3 · HSB / Middleware

*(pendiente)*

---

## Fase 4 · Seguridad, resiliencia y despliegue

*(pendiente)*

---

## Fase 5 · Prototipo final y sustentación

*(pendiente)*

---

## Correcciones entre fases

| Fase corregida | Fecha | Motivo | Corrección aplicada |
|---------------|-------|--------|---------------------|
| — | — | — | — |

