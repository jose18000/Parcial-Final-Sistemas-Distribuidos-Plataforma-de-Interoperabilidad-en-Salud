# app/

API Gateway y vistas por rol (contenedor `api_gateway`, puerto 8000).

- `main.py` — rutas de las vistas y de la API
- `auth.py` — JWT HS256 y usuarios de prueba
- `rbac.py` — permisos por rol; un acceso no permitido responde 403 y queda auditado
- `audit.py` — cadena de auditoría SHA-256 en `pg_central.evento_auditoria` y verificador
- `dashboard.py` — tablero: nodos y motor, cobertura FHIR por sede, métricas del bus, auditoría
- `templates/` — plantillas Jinja2 de las 4 vistas

| Vista | Ruta | Rol |
|---|---|---|
| Paciente | `/paciente` | paciente: su historia de las 3 sedes, su Bundle FHIR, quién accedió |
| Admisionista | `/admision` | admisionista: búsqueda por sedes, registro/admisión con triage, monitor del bus; sin diagnósticos |
| Médico | `/medico` | médico: historia unificada; diagnóstico CIE-10, fórmula y egreso, cada uno con sello |
| Reporte de HC | `/reporte` (`?pestana=tablero`) | médico, auditor y paciente (solo el suyo) |

API: `GET /api/pacientes/{doc}/historia`, `GET /api/pacientes/{doc}/bundle`, `GET /api/catalogo-57`,
`GET /api/auditoria/verificar`, `GET /api/auditoria/eventos`, `POST /api/auditoria/alterar-prueba`,
`GET /health`, `GET /metrics`.

**Regla:** ninguna vista habla directamente con las bases de las sedes. Las lecturas usan la consulta
unificada (`db/consulta_unificada.py`); las escrituras se envían al HSB por `/hsb/json`.
