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

| Fecha | Integrante | Actividad | IA / Código abierto |
|-------|-----------|-----------|---------------------|
| 2026-11-08 | A — Jose Canchila | Diseño del HSB con FastAPI (`hsb/main.py`), endpoints `/hsb/hl7`, `/hsb/csv`, `/health`, `/metrics`, gestor de cola con reintentos (`hsb/queue_manager.py`) y Dockerfile | Antigravity — estructuración de endpoints y lógica de reintentos |
| 2026-11-08 | A — Jose Canchila | Integración de HSB en `docker-compose.yml`, recolector de métricas operacionales (`hsb/metrics.py`) y verificación de idempotencia | Antigravity — cálculo de latencias y soporte en deduplicación |
| 2026-11-08 | B — Sharit Manjarrez | Parsers de HL7 v2 (`hsb/parser_hl7.py`) y CSV legado (`hsb/parser_csv.py`), validador pre-transformación (`hsb/validator.py`) y tabla de terminologías | Antigravity — análisis de segmentos HL7 y expresiones regulares CIE-10/LOINC |
| 2026-11-08 | B — Sharit Manjarrez | Suite de pruebas de integración (`tests/fase3/test_hsb_integration.py`) con los 4 ejemplos contractuales e informe técnico de Fase 3 | Antigravity — asistencia en casos de prueba con unittest y redacción técnica |
| 2026-11-08 | A + B | Verificación de reintentos con backoff exponencial, simulación de cola de mensajes muertos y respuesta de autoevaluación | — |

### Uso declarado de IA en Fase 3
- **Herramienta:** Antigravity (Google DeepMind) vía IDE integrado.
- **Uso:** Asistencia en la construcción del parser de segmentos HL7 v2 con delimitadores `\r`, mapeador terminológico para CSV, validador de contratos clínicos con reporte de motivos exactos de rechazo y pruebas de integración.
- **Revisión humana:** Se verificó experimentalmente que los 4 archivos de prueba arrojaran exactamente los resultados previstos por la guía docente sin alterar los ejemplos originales, y que el reenvío respondiera 'duplicado' sin crear registros espurios.
- **Código abierto:** FastAPI (MIT), Uvicorn (BSD), HTTPX (BSD), HAPI FHIR (Apache 2.0).*

---

## Fase 4 · Seguridad, resiliencia y despliegue

| Fecha | Integrante | Actividad | IA / Código abierto |
|-------|-----------|-----------|---------------------|
| 2026-11-08 | A — Jose Canchila | Motor de auditoría encadenada por hash SHA-256 (`app/audit.py`), algoritmo verificador de integridad y soporte de simulación de alteración maliciosa | Antigravity — implementación matemática de la cadena inmutable |
| 2026-11-08 | A — Jose Canchila | Orquestación completa de 6 servicios en `docker-compose.yml`, Dockerfile de la API Gateway (`app/Dockerfile`) y manifiestos de Kubernetes para Minikube (`infra/k8s/`) | Antigravity — configuración de probes y servicios k8s |
| 2026-11-08 | B — Sharit Manjarrez | Autenticación JWT y matriz RBAC con 4 roles (`app/auth.py`, `app/rbac.py`) y plantillas HTML accesibles (`app/templates/`) | Antigravity — diseño de vistas accesibles y middleware de seguridad |
| 2026-11-08 | B — Sharit Manjarrez | Suite de pruebas de seguridad y resiliencia (`tests/fase4/test_security_resilience.py`) e informe de Fase 4 (Viabilidad técnica y Ley 1581) | Antigravity — redacción técnica y diseño de casos de prueba |
| 2026-11-08 | A + B | Demostración de caída de sede (degradación a reporte parcial), prueba de detección de auditoría alterada y respuesta a pregunta de autoevaluación | — |

### Uso declarado de IA en Fase 4
- **Herramienta:** Antigravity (Google DeepMind) vía IDE integrado.
- **Uso:** Asistencia en la formulación criptográfica de la cadena de hash SHA-256, diseño de la matriz RBAC en FastAPI con excepciones HTTP 403, maquetación de plantillas HTML accesibles para las 4 vistas y manifiestos declarativos de Kubernetes.
- **Revisión humana:** Se probó que un usuario paciente recibiera error 403 al solicitar historias ajenas, que la adulteración de un registro en memoria activara la alerta del verificador señalando el bloque exacto, y que la caída de un nodo no interrumpiera el servicio de consulta.
- **Código abierto:** Python-Jose (MIT), Passlib (BSD), Jinja2 (BSD), Kubernetes Client / Manifests.*

---

## Fase 5 · Prototipo final y sustentación

*(pendiente)*

---

## Correcciones entre fases

| Fase corregida | Fecha | Motivo | Corrección aplicada |
|---------------|-------|--------|---------------------|
| — | — | — | — |

