# db/

Capa de datos distribuida con **motores heterogéneos por sede** (Fase 2).

| Sede | Ciudad | Motor | Contenedor | Inicialización |
|---|---|---|---|---|
| 1 | Sincelejo | PostgreSQL 16 | `pg_sede1` | `schema.sql` + `sede1/init.sql` |
| 2 | Cartagena | MongoDB 7 | `mongo_sede2` | `sede2/init-mongo.js` |
| 3 | Corozal | PostgreSQL 16 | `pg_sede3` | `schema.sql` + `sede3/init.sql` |
| — | Central (auditoría) | PostgreSQL 16 | `pg_central` | `central/init.sql` |

- `schema.sql` — esquema relacional con los 57 campos (Res. 866 de 2021): `usuario`, `atencion`,
  `tecnologia_salud`, `diagnostico`, `egreso`, `profesional_salud`, `sede`, `mensaje_bus`.
- `sede2/init-mongo.js` — modelo documental: un documento por paciente en `pacientes`, con las
  atenciones embebidas; más `mensajes_bus`, `profesionales` y `sedes`.
- `repositorio.py` — misma interfaz para PostgreSQL y MongoDB (`guardar`, `historia`, mensajes del bus,
  cobertura). Todo pasa por el traductor universal (`traductor/`).
- `consulta_unificada.py` — scatter-gather en paralelo sobre las 3 sedes; tolera la caída de una sede.
- `demo_acid.sql` — demostración de atomicidad en PostgreSQL:
  `docker exec -i pg_sede1 psql -U clinica_user -d clinica_sincelejo < db/demo_acid.sql`

Datos 100 % sintéticos. `fhir_patient_id` arranca en NULL (cobertura FHIR 0 %). El paciente 1001
tiene atenciones en las 3 sedes.
