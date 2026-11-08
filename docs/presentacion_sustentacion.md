# Presentación de Sustentación · Diapositivas
## Plataforma Distribuida de Interoperabilidad Clínica

**Equipo:** Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)  
**Curso:** Sistemas Distribuidos · Parcial Final  
**Duración:** 15 minutos de presentación + demostración en vivo

---

## Diapositiva 1: Portada y Planteamiento del Problema

### Plataforma Distribuida de Interoperabilidad Clínica
*Red de IPS Sincelejo, Cartagena y Corozal*

- **El Problema:**
  - Red hospitalaria con 3 sedes independientes.
  - Cada sede emite información en formatos dispares (HL7 v2.5 y CSV legado).
  - La historia clínica de un paciente está fraccionada entre ciudades.
  - **Desafío:** Unificar el expediente médico en tiempo real **SIN reemplazar los sistemas legados** ni forzar una migración traumática.

---

## Diapositiva 2: Arquitectura de Tres Capas

```
[ SEDES LEGADAS ] ──(HL7 v2 / CSV)──> [ HEALTH SERVICE BUS (HSB) ]
                                              │
                                 ┌────────────┴────────────┐
                                 ▼                         ▼
                         [ HAPI FHIR R4 ]          [ NODOS DE DATOS ]
                           (:8090 REST)          (Sincelejo, Cartagena,
                                 │                      Corozal)
                                 └────────────┬────────────┘
                                              ▼
                                     [ API GATEWAY :8000 ]
                                 (Seguridad RBAC + Auditoría)
                                              │
                    ┌──────────────┬──────────┴───┬──────────────┐
                    ▼              ▼              ▼              ▼
               [ Paciente ]  [ Admisión ]    [ Médico ]    [ Reporte ]
```

- **Principios Rectores:**
  - Cero microservicios por moda: cada componente responde a un RF o RNF.
  - Regla de oro: Ninguna vista habla directo con las bases de datos de las sedes; todo pasa por la API y el HSB.

---

## Diapositiva 3: Capa de Datos Distribuidos y Teorema CAP

- **Decisión de Fragmentación:**
  - Fragmentación horizontal por sede (`sede_id`).
  - Coincide en un 95 % con la localidad de consulta y escritura inmediata.
- **Justificación según Teorema CAP:**
  - **Modelo AP (Disponibilidad y Tolerancia a Partición):** Si una sede cae (ej. Cartagena), la plataforma **sigue disponible**, responde con Sincelejo y Corozal, y etiqueta el reporte con aviso explícito de incompletitud.
  - Renunciamos al bloqueo global inmediato de 2PC para no paralizar la atención médica ante caídas de enlace WAN.
- **ACID Intra-Nodo:**
  - Transacciones atómicas locales en PostgreSQL: si falla la inserción de una atención, se ejecuta un rollback total y no queda ningún registro huérfano.

---

## Diapositiva 4: Health Service Bus (HSB) e Interoperabilidad Semántica

- **Capacidades del HSB:**
  - Ingesta multiformato: `POST /hsb/hl7` (ADT^A01, ORU^R01) y `POST /hsb/csv?sede=N`.
  - Mapeo semántico dinámico: diagnósticos locales de CSV mapeados a CIE-10 (`05_ref_terminologia.csv`) y laboratorios a LOINC.
  - Rechazo estricto con motivo antes de transformar: ningún mensaje inválido se pierde en silencio.
- **Idempotencia Criptográfica Persistente:**
  - Hash SHA-256 de la carga útil almacenado en la tabla `mensaje_bus`.
  - Reenviar el mismo mensaje responde `duplicado` y no crea pacientes repetidos.
- **Resiliencia y Reintentos con Backoff Exponencial:**
  - Si HAPI FHIR no responde: reintentos en $1\text{ s}, 2\text{ s}, 4\text{ s}, 8\text{ s}$.
  - Tras 4 fallos $\to$ Estado `MUERTO` (Dead Letter Queue) con posibilidad de reencolar.

---

## Diapositiva 5: Seguridad RBAC y Auditoría Inmutable

- **Autenticación JWT:**
  - 4 roles con permisos diferenciados evaluados en la API Gateway:
    - *Paciente:* Solo su propia historia (si cambia el doc en URL $\to$ 403 Forbidden).
    - *Admisionista:* Registro y triage; sin acceso a diagnósticos clínicos.
    - *Médico:* Consulta integral de 3 sedes, diagnóstico CIE-10 y egreso con sello hash.
    - *Auditor:* Reporte completo, estado de nodos y verificación criptográfica.
- **Cadena de Auditoría Encadenada por Hash SHA-256:**
  $$\text{hash\_propio} = \text{SHA-256}(\text{hash\_anterior} + \text{timestamp} + \text{usuario} + \text{tipo\_evento} + \text{resultado} + \text{detalle})$$
- **Verificador Matemático en Tiempo Real:**
  - Recorre la cadena y señala inmediatamente el primer bloque adulterado.
- **Cumplimiento Ley 1581 de 2012:**
  - El paciente audita en su portal quién ha consultado su información.

---

## Diapositiva 6: Resultados Medidos y Telemetría

| Indicador Evaluado | Objetivo Inicial | Medición Obtenida | Estado |
|--------------------|:----------------:|:-----------------:|:------:|
| **Comando de Despliegue** | 1 solo comando | `docker compose up -d` | ✅ 6/6 servicios activos |
| **Latencia Consulta Unificada** | <500 ms | **18,4 ms** (3 sedes) | ✅ Óptimo |
| **Cobertura FHIR Inicial** | 0 % | **0,0 %** (`fhir_patient_id = NULL`) | ✅ Verificado |
| **Cobertura FHIR Post-Ingesta** | 100 % | **100,0 %** | ✅ Verificado |
| **Detección de Duplicados** | 100 % | **100,0 %** reconocidos | ✅ Verificado |
| **Detección de Alteraciones** | Detección exacta | **100,0 %** (índice e ID identificados) | ✅ Verificado |

---

## Diapositiva 7: Demostración en Vivo y Conclusiones

### Demostración en Vivo (Paso a Paso):
1. `docker compose down -v && docker compose up -d` limpio.
2. Tablero de observabilidad con cobertura inicial al 0 %.
3. Ingesta de mensajes HL7 y CSV $\to$ la cobertura sube y se genera el Bundle FHIR R4.
4. Reenvío del mensaje $\to$ respuesta "duplicado" sin recrear filas.
5. Caída intencional de una sede (`docker stop pg_sede2`) $\to$ la vista responde con 2 sedes y avisa.
6. Demostración de alteración en auditoría $\to$ alerta roja en el tablero.
7. Consulta federada del paciente 1001 (Carlos Pérez) con registros en las 3 sedes.

### Conclusión Principal:
Es factible lograr interoperabilidad semántica clínica bajo estándares FHIR R4 y principios de alta disponibilidad respetando la soberanía de los legados hospitalarios.
