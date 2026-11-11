# Presentación de sustentación · Diapositivas

**Equipo:** Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)
**Curso:** Sistemas Distribuidos · Parcial final
**Uso:** apoyo de la demostración de 15 min (ver `guion_demostracion.md`). Una diapositiva por bloque.

---

## Diapositiva 1 · El problema

**Plataforma distribuida de interoperabilidad clínica para una red de IPS con tres sedes heterogéneas**

- Sincelejo, Cartagena y Corozal: cada sede con su sistema legado, **su base y su motor**.
- Envían en formatos distintos: HL7 v2 (ADT, ORU) y CSV con `;`.
- La historia de un paciente está partida en tres.
- Meta: unificarla con los **57 campos de la Resolución 866 de 2021**, en FHIR R4, **sin reemplazar
  los legados**.

---

## Diapositiva 2 · Arquitectura

```
 HL7 v2 ─┐                          ┌─> HAPI FHIR R4 :8090 (Bundle transaction, PUT)
 CSV    ─┼─> HSB :8001 ─> traductor ┼─> Sede 1 Sincelejo · PostgreSQL  (pg_sede1)
 JSON   ─┘   valida, idempotencia,  ├─> Sede 2 Cartagena · MongoDB     (mongo_sede2)
             cola y reintentos      └─> Sede 3 Corozal   · PostgreSQL  (pg_sede3)
                                          ▲
 4 vistas por rol ─> API Gateway :8000 ───┘  consulta unificada en paralelo
                         └─> pg_central: auditoría encadenada SHA-256
```

- 7 contenedores, **un comando**: `docker compose down -v && docker compose up -d --build`.
- Regla de oro: ninguna vista habla con las bases. Lecturas por la API; escrituras por el HSB.

---

## Diapositiva 3 · Por qué motores distintos

- El escenario dice que **cada sede conserva su sistema**: en la vida real no todas usan el mismo
  motor. Por indicación del docente, la Sede 2 usa **MongoDB**.
- MongoDB guarda **un documento por paciente** con sus atenciones embebidas, y con otros nombres:
  `identificacion.numero` en vez de `documento_id`, `ingreso.fecha` en vez de `fecha_ingreso`.
- La plataforma no puede suponer un esquema común → **repositorio con una sola interfaz**
  (`RepositorioPostgres` / `RepositorioMongo`) y **traductor**.
- Atomicidad:
  - PostgreSQL: usuario + atención + diagnósticos + tecnologías + egreso en **una transacción**.
  - MongoDB: la atención va dentro del documento → **una escritura de un documento**, atómica.
- CAP: la consulta es **AP**. Si una sede cae, se responde con las otras dos y se marca
  `reporte_completo = false`.

---

## Diapositiva 4 · Traductor de 57 campos

- **Un catálogo** (`traductor/catalogo_57.py`): para cada campo, HL7 → CSV → `tabla.columna` de
  PostgreSQL → ruta en MongoDB → elemento FHIR.
- **Registro canónico** como pivote: 3 entradas + 3 salidas = 6 traducciones, no 9.
- **Segmentos Z** para lo que HL7 v2.5 no trae: `ZPI`, `ZPV`, `ZRX`, `ZEG` (convención del proyecto).
- **Dominios con sinónimos**: `E` → `01` Urgencias, `III` → triage `3`, `PO` → vía `01` Oral.
- Diagnósticos 33–39 como filas con rol (INGRESO, EGRESO, RELACIONADO). Derivados: edad, unidad,
  código del prestador.
- Ejemplo, campo 14: `PID-11.9` → `usuario.municipio_residencia` / `residencia.municipio_dane` →
  `Patient.address.district`.

---

## Diapositiva 5 · El HSB y los estados del mensaje

```
RECIBIDO ─> VALIDADO ─> TRANSFORMADO ─> ENTREGADO
   │             │            │  ▲
   ▼             ▼            ▼  │ reintento OK
RECHAZADO    RECHAZADO    REINTENTANDO ──(7 intentos)──> MUERTO ──(reencolar)──> REINTENTANDO
                              error de datos ─────────────> MUERTO
```

- Traducir → **idempotencia** (`MSH-10` o hash, guardado en `mensaje_bus` de la sede) → validar →
  Bundle → **HAPI primero, sede después**.
- Reintentos en segundo plano: 2, 4, 8, 16, 32, 64 s (`HSB_MAX_RETRIES=7`). Responde `202` sin bloquear.
- **Error de datos** (restricción violada, HAPI 4xx) → MUERTO de una vez: reintentar no lo arregla.
- Al reiniciar el bus, recupera lo que quedó en REINTENTANDO o TRANSFORMADO.

---

## Diapositiva 6 · Seguridad y auditoría

- **JWT** y **4 roles** validados en la API (no en la pantalla): paciente, admisionista, médico,
  auditor. Acción no permitida → **403** y evento `ACCESO_DENEGADO`.
- Admisionista no ve diagnósticos. El médico firma con su identidad del token.
- **Cadena SHA-256** en `pg_central.evento_auditoria`:
  `hash = SHA-256(hash_anterior | índice | timestamp | usuario | rol | tipo | recurso | resultado | detalle)`
- El verificador señala el **primer** evento alterado. Cada escritura del médico devuelve un
  **sello** = hash de su evento.

---

## Diapositiva 7 · Resultados medidos (Kali, VM de 3,8 GB, Docker 28)

| Prueba | Resultado |
|---|---|
| Arranque desde cero | Un comando; HAPI listo en 85–95 s |
| Ejemplos oficiales | 01 entregado · reenvío duplicado (1 Patient 1007) · 02 entregado (718-7 = 13,8 g/dL) · 03 rechazado (3 motivos) · CSV 3 entregados + 2 rechazados |
| Mensaje de 57 campos | 11 recursos FHIR · **56/57** campos · 100 % obligatorios (falta el 42: sale vivo) |
| Cobertura FHIR | 0 % al inicio → sede 1: 50–67 %, sede 2: 33,3 %, sede 3: 75 % |
| Historia de 1001 (3 sedes, 2 motores) | **52/57** campos, 100 % obligatorios · Bundle de 26 recursos, **0 errores** en `$validate` |
| HAPI apagado | `reintentando` → 7 intentos → entregado solo a los **129,5 s**, sin duplicar |
| `mongo_sede2` detenido | Responde con sedes 1 y 3, reporte incompleto, `/health` DEGRADED 2/3 |
| `UPDATE` en la auditoría | Detectado en el **índice 3** |
| Pruebas automatizadas | **36/36** |

No medido de forma sistemática: latencia por mensaje y mensajes por minuto bajo carga.

---

## Diapositiva 8 · Limitaciones y trabajo futuro

- MongoDB sin *replica set* (sin transacciones multi-documento ni conmutación por fallo).
- Una sola instancia de HAPI.
- Segmentos Z y códigos REPS son de este proyecto (sintéticos), no estándar nacional.
- Cobertura FHIR por sede < 100 %: falta migrar por el bus a los pacientes legados.
- El HSB no exige autenticación; JWT con usuarios de prueba.
- **Siguiente:** *replica set*, script de migración, prueba de carga, Keycloak + TLS, anclaje en
  Fabric, CI con las 36 pruebas.

**Conclusión:** un catálogo de 57 campos, un registro canónico y entregas idempotentes bastan para
unificar tres sedes con motores distintos, sin transacción distribuida y sin tocar los legados.
