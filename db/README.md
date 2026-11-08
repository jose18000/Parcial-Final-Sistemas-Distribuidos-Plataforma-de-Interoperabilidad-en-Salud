# db/

Scripts SQL de inicialización de los 3 nodos PostgreSQL — Fase 2.

Estructura por carpeta:
- `db/sede1/` — scripts de Sincelejo (pg_sede1 :5433)
- `db/sede2/` — scripts de Cartagena (pg_sede2 :5434)
- `db/sede3/` — scripts de Corozal (pg_sede3 :5435)
- `db/seed/` — datos sintéticos (mínimo 1 paciente con atenciones en las 3 sedes)

Tablas a crear en cada nodo:
usuario, atencion, diagnostico, tecnologia_salud, egreso, profesional_salud, mensaje_bus, evento_auditoria

