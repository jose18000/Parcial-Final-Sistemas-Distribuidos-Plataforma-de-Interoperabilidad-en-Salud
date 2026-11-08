# Plataforma Distribuida de Interoperabilidad Clínica

> **Equipo:** Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)
> **Curso:** Sistemas Distribuidos · Parcial Final
> **Estado:** 🟡 Fase 1 en progreso

---

## Descripción

Red de IPS con sedes en **Sincelejo**, **Cartagena** y **Corozal**. Cada sede conserva su sistema legado con base de datos propia y emite datos en HL7 v2 y CSV. Esta plataforma unifica la historia clínica fraccionada **sin reemplazar los sistemas legados**.

## Estructura del repositorio

```
parcial_2/
├── docs/           # Informe, diagramas UML, arquitectura (por fase)
├── infra/          # docker-compose y configuración de infraestructura
├── hsb/            # Health Service Bus (Fase 3)
├── fhir/           # Normalizador FHIR y scripts de validación (Fase 2-3)
├── db/             # Scripts SQL de inicialización por sede (Fase 2)
├── app/            # API Gateway y vistas por rol (Fase 4-5)
├── tests/          # Pruebas unitarias e integración
├── ejemplos/       # Mensajes de prueba HL7/CSV — NO MODIFICAR
├── guias/          # Guías del docente por fase — solo lectura
├── README.md
├── docker-compose.yml
├── .env.example    # Plantilla de variables de entorno
└── .gitignore
```

## Requisitos previos

- Docker Desktop ≥ 24.x con Compose v2
- Git ≥ 2.40
- (Opcional) Python 3.11+ para ejecutar pruebas locales

## Ejecución rápida

```bash
# 1. Copiar variables de entorno
cp .env.example .env
# editar .env con los valores reales

# 2. Levantar todo
docker compose up -d

# 3. Verificar estado
docker compose ps

# 4. Limpiar y relanzar desde cero
docker compose down -v && docker compose up -d
```

> **Nota de Fase 1:** `docker-compose.yml` es un esqueleto; la implementación completa está en Fase 2.

## Usuarios de prueba (Fase 4)

| Usuario | Contraseña | Rol | Sede |
|---------|-----------|-----|------|
| `paciente01` | `Test1234!` | paciente | — |
| `admision02` | `Test1234!` | admisionista | Cartagena |
| `medico03` | `Test1234!` | medico | Sincelejo |
| `auditor04` | `Test1234!` | auditor | — |

## Enviar mensajes de ejemplo al HSB (Fase 3)

```bash
# HL7 ADT^A01 válido (sede 2)
curl -X POST http://localhost:8001/hsb/hl7 \
  -H "Content-Type: text/plain" \
  --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7

# HL7 ORU^R01 laboratorio (sede 1)
curl -X POST http://localhost:8001/hsb/hl7 \
  -H "Content-Type: text/plain" \
  --data-binary @ejemplos/02_oru_r01_laboratorio_sede1.hl7

# CSV legado (sede 3)
curl -X POST "http://localhost:8001/hsb/csv?sede=3" \
  -H "Content-Type: text/csv" \
  --data-binary @ejemplos/04_sede3_legado.csv
```

## Simular caída de una sede

```bash
docker compose stop pg_sede2    # Cartagena cae
# → la vista unificada responde con sedes 1 y 3, marca sede 2 como no disponible
docker compose start pg_sede2   # Cartagena vuelve
# → el bus entrega mensajes pendientes automáticamente
```

## Fases y estado

| Fase | Descripción | Nota máx. | Estado |
|------|-------------|-----------|--------|
| 1 | Análisis, UML y diseño | 0,75 | 🟡 En curso |
| 2 | Datos distribuidos y FHIR | 1,00 | ⬜ Pendiente |
| 3 | HSB / middleware | 1,25 | ⬜ Pendiente |
| 4 | Seguridad, resiliencia, despliegue | 1,00 | ⬜ Pendiente |
| 5 | Prototipo final y sustentación | 1,00 | ⬜ Pendiente |

## Integrantes y reparto

| Integrante | Responsabilidad principal F1 |
|------------|------------------------------|
| **A — Jose Guillermo Canchila** | Diagramas UML (casos de uso, secuencia, clases, estados) + diagrama de arquitectura |
| **B — Sharit Javier Manjarrez** | Marco teórico + tabla de mapeo de campos + resumen del informe |

Revisión cruzada: cada integrante revisa y puede modificar el trabajo del otro antes del commit final de cada fase.

## Declaración de uso de IA y código abierto

Ver [`docs/bitacora.md`](docs/bitacora.md) para el registro completo.

## Etiqueta de versión

```bash
git tag v1.0 && git push origin v1.0  # Al finalizar Fase 5
```

