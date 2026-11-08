# Plataforma Distribuida de Interoperabilidad Clínica
## Red de IPS Sincelejo · Cartagena · Corozal

> **Equipo:** Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)  
> **Curso:** Sistemas Distribuidos · Parcial Final  
> **Versión:** `v1.0` (Entrega Final y Sustentación)  
> **Estado:** 🟢 100 % Completado (Fases 1 a 5)

---

## 1. Descripción del Sistema

Plataforma distribuida orientada a servicios de salud que unifica la historia clínica fragmentada de una red de IPS con sedes en **Sincelejo (1)**, **Cartagena (2)** y **Corozal (3)**. Cada sede conserva su base de datos relacional independiente y emite registros en formatos heterogéneos (**HL7 v2.5** y **CSV** legado). La plataforma integra, normaliza a **FHIR R4**, enruta y consulta los expedientes clínicos **sin reemplazar los sistemas legados**.

---

## 2. Estructura del Repositorio

```
parcial_2/
├── app/                  # API Gateway FastAPI, RBAC, vistas HTML (Jinja2) y dashboard
├── hsb/                  # Health Service Bus (HSB), parsers HL7/CSV, reintentos y métricas
├── fhir/                 # Normalizador determinista a FHIR R4 (Patient, Encounter, Condition, Observation)
├── db/                   # DDL relacional unificado y scripts SQL de inicialización por sede
├── docs/                 # Informes v7, guion de sustentación, diapositivas y bitácora
│   ├── informe_final_v7.md           # Informe final completo en plantilla v7
│   ├── guion_demostracion.md         # Guion paso a paso de 15 minutos de la demo
│   ├── preguntas_sustentacion.md     # Respuestas a las 5 preguntas típicas de examen
│   └── presentacion_sustentacion.md  # Diapositivas de apoyo para la sustentación
├── infra/                # Manifiestos de Kubernetes para Minikube
├── tests/                # Suites de pruebas unitarias e integración (Fases 2, 3 y 4)
├── ejemplos/             # Mensajes de prueba oficiales contractuales (NO MODIFICADOS)
├── docker-compose.yml    # Orquestación de los 6 servicios de la plataforma
├── .env.example          # Plantilla de variables de entorno
└── README.md
```

---

## 3. Requisitos Previos

- Docker Desktop ≥ 24.x con Compose v2
- Git ≥ 2.40
- Navegador web moderno (Chrome, Firefox o Edge)
- (Opcional) cURL o Postman para pruebas de endpoints

---

## 4. Ejecución Rápida (Un Solo Comando)

```bash
# 1. Copiar archivo de entorno
cp .env.example .env

# 2. Levantar los 6 servicios desde cero
docker compose down -v && docker compose up -d --build

# 3. Comprobar que los contenedores están saludables
docker compose ps
```

### Puertos y Servicios Expuestos:
- **API Gateway & Vistas Web:** [`http://localhost:8000`](http://localhost:8000) (Login en `/login`)
- **Health Service Bus (HSB):** [`http://localhost:8001`](http://localhost:8001) (`/health`, `/metrics`)
- **HAPI FHIR R4:** [`http://localhost:8090/fhir`](http://localhost:8090/fhir) (`/fhir/metadata`)
- **pg_sede1 (Sincelejo):** Puerto `5433`
- **pg_sede2 (Cartagena):** Puerto `5434`
- **pg_sede3 (Corozal):** Puerto `5435`

---

## 5. Usuarios de Prueba Preconfigurados

| Usuario | Contraseña | Rol | Acceso y Funcionalidades |
|---------|-----------|-----|--------------------------|
| `paciente_carlos` | `Paciente123!` | `paciente` | Consulta su historia personal (doc: 1001), descarga su Bundle FHIR R4 y revisa el log de accesos (Ley 1581). |
| `admision_laura` | `Admision123!` | `admisionista` | Búsqueda de pacientes en las 3 sedes, apertura de atenciones con triage (1-5) y monitor del bus. **No ve diagnósticos**. |
| `medico_mateo` | `Medico123!` | `medico` | Consulta historias unificadas de cualquier paciente, registra diagnósticos CIE-10 y emite egreso con sello hash SHA-256. |
| `auditor_elena` | `Auditor123!` | `auditor` | Reporte integral, tablero de observabilidad en vivo, estado de sedes y verificador criptográfico de auditoría. |

---

## 6. Procesamiento de Mensajes de Ejemplo (Contrato del HSB)

```bash
# 1. HL7 ADT^A01 válido Sede 2 (Andrea Rojas - Doc 1007) -> ENTREGADO
curl -X POST http://localhost:8001/hsb/hl7 \
  -H "Content-Type: text/plain" \
  --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7

# 2. Reenvío del Archivo 01 -> DUPLICADO DETECTADO (Idempotencia)
curl -X POST http://localhost:8001/hsb/hl7 \
  -H "Content-Type: text/plain" \
  --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7

# 3. HL7 ORU^R01 Laboratorio Sede 1 (Carlos Pérez - Doc 1001) -> ENTREGADO
curl -X POST http://localhost:8001/hsb/hl7 \
  -H "Content-Type: text/plain" \
  --data-binary @ejemplos/02_oru_r01_laboratorio_sede1.hl7

# 4. HL7 ADT^A01 Inválido -> RECHAZADO con 3 motivos (Doc no numérico, sexo inválido, dx sin mapeo)
curl -X POST http://localhost:8001/hsb/hl7 \
  -H "Content-Type: text/plain" \
  --data-binary @ejemplos/03_adt_a01_invalido.hl7

# 5. CSV Legado Sede 3 -> 3 ENTREGADOS (1008, 1009, 1010) y 2 RECHAZADOS (1011 y 12)
curl -X POST "http://localhost:8001/hsb/csv?sede=3" \
  -H "Content-Type: text/csv" \
  --data-binary @ejemplos/04_sede3_legado.csv
```

---

## 7. Pruebas de Resiliencia (Caída de Sede en Vivo)

```bash
# 1. Apagar la base de datos de Cartagena
docker stop pg_sede2

# 2. Consultar la historia del paciente 1001 (responde con Sincelejo y Corozal)
curl -s http://localhost:8000/api/pacientes/1001/historia | jq '{reporte_completo, sedes_disponibles, sedes_no_disponibles}'

# 3. Reactivar la sede Cartagena
docker start pg_sede2
```

---

## 8. Verificador de Auditoría y Detección de Alteración

```bash
# 1. Verificar estado de la auditoría (cadena íntegra)
curl -s http://localhost:8000/api/auditoria/verificar | jq .

# 2. Simular alteración deliberada de un evento
curl -X POST http://localhost:8000/api/auditoria/alterar-prueba

# 3. Comprobar que el verificador detecta la alteración y señala el bloque
curl -s http://localhost:8000/api/auditoria/verificar | jq .
```

---

## 9. Ejecución de Pruebas Automatizadas

```bash
# Pruebas de Normalización FHIR (Fase 2)
python -m unittest tests/fase2/test_normalizer.py

# Pruebas de Integración del HSB con los 4 ejemplos (Fase 3)
python -m unittest tests/fase3/test_hsb_integration.py

# Pruebas de Seguridad RBAC, Auditoría y Resiliencia (Fase 4)
python -m unittest tests/fase4/test_security_resilience.py
```

---

## 10. Etiqueta de Versión

```bash
git tag v1.0
git push origin v1.0
```
