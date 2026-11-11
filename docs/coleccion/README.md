# Colección de pruebas (Postman)

Entregable de la Fase 5: «Datos sintéticos y colección de pruebas».

| Archivo | Qué es |
|---|---|
| `Plataforma_Interoperabilidad.postman_collection.json` | 43 peticiones en 9 carpetas, cada una con sus pruebas automáticas |
| `entorno_kali.postman_environment.json` | Direcciones de la VM Kali (`192.168.1.94`) |
| `entorno_local.postman_environment.json` | Direcciones en `localhost` (si se ejecuta en el mismo equipo que Docker) |
| `generar_coleccion.py` | Regenera la colección (toma los mensajes de `ejemplos/` sin modificarlos) |

## Carpetas

0. **Salud y métricas** — `/health` y `/metrics` del HSB y la API, `metadata` de HAPI.
1. **Mensajes oficiales del docente** — los 4 ejemplos de `ejemplos/` con el resultado del `LEEME.md` (entregado, duplicado al reenviar, rechazado con 3 motivos, CSV 3 + 2).
2. **Traductor de 57 campos** — mensaje HL7 completo, registro JSON por número de campo y catálogo.
3. **Cola del bus** — mensajes por estado, rechazados con motivo, reencolar.
4. **Autenticación** — un token JWT por rol (se guarda solo en variables de la colección).
5. **Consulta unificada y FHIR** — historia del 1001 en 3 sedes y 2 motores, Bundle, `$validate` con 0 errores, un solo Patient 1007, Observation 718-7.
6. **Permisos por rol** — accesos permitidos (200) y denegados (403/401).
7. **Auditoría encadenada** — verificador y eventos (incluye los 403 de la carpeta anterior).
8. **Panel y usuarios** — el administrador de la sede 2 crea un médico en su sede; no puede crear en la sede 1; el auditor no puede crear; desactivar.

## Cómo ejecutarla

**Postman:** *Import* → los tres archivos `.json` → elegir el entorno *Plataforma · VM Kali* → clic derecho en la colección → *Run collection* → *Run*. Ejecutar las carpetas en orden.

**Newman (línea de comandos):**

```bash
npx newman run docs/coleccion/Plataforma_Interoperabilidad.postman_collection.json -e docs/coleccion/entorno_kali.postman_environment.json
```

Notas:
- Las peticiones no envían cookies: cada una se autentica solo con el token de su rol, así las pruebas de 401/403 son reales.
- Si los ejemplos ya se habían enviado, el bus responde «duplicado»; las pruebas lo aceptan porque eso demuestra la idempotencia.
- Las pruebas que necesitan apagar contenedores (HAPI caído y reintentos, mensaje muerto, sede caída, alteración de la auditoría) están en el `README.md` principal y en `docs/guion_demostracion.md`.
