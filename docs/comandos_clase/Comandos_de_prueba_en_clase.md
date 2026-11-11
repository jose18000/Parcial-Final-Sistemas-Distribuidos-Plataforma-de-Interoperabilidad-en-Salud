# Comandos de prueba en clase · Plataforma de Interoperabilidad Clínica

Todos los comandos se ejecutan en una terminal de la VM Kali, dentro de la carpeta del proyecto. Todo va por **HTTPS** con la CA propia de la plataforma (`certs/ca.pem`) y el bus exige un **token OAuth 2.0**.

> **Red.** La VM está en NAT con reenvío de puertos (8000, 8001 y SSH 2222). En el PC se abre `https://localhost:8000`; otro equipo de la misma red usa la IP del PC (hoy `https://10.10.10.45:8000`). Así no importa qué IP le dé el Wi-Fi a la VM.

> **Aviso del navegador.** Para que el navegador del PC confíe en el certificado, importe la CA una vez en PowerShell, desde la carpeta del proyecto en el PC: `certutil -user -addstore Root certs\ca.pem`. Sin eso, el navegador muestra "no es privado" y hay que aceptar el aviso.

## Antes de clase

Encienda la VM en VirtualBox y abra una terminal en Kali (o entre por SSH desde Windows, por el puerto reenviado).

```bash
ssh -p 2222 -i ~/.ssh/atlas_kali kali@127.0.0.1
```

```bash
cd ~/Documents/Parcial-Final-Sistemas-Distribuidos-Plataforma-de-Interoperabilidad-en-Salud
```

Deje la plataforma levantada y comprobada una vez antes de entrar (tarda 5 a 8 minutos). Debe terminar en **70/70 correctas**.

```bash
bash desplegar.sh --desde-cero --con-datos --verificar
```

Para la demo frente al profe se arranca otra vez desde cero (paso 1), porque la guía pide mostrar la cobertura FHIR en 0 %.

| Usuario | Contraseña | Rol |
| --- | --- | --- |
| auditor_elena | Auditor123! | Auditor (panel y estado) |
| medico_mateo | Medico123! | Médico |
| admision_laura | Admision123! | Admisionista |
| paciente_carlos | Paciente123! | Paciente (documento 1001) |
| admin_plataforma | Admin123! | Administrador general |

| Cliente OAuth 2.0 | Secreto (prueba) | Para qué |
| --- | --- | --- |
| herramientas_qa | qa_secreto_2026 | Scripts, Postman y esta demo (bus completo) |
| sistema_sede1 / 2 / 3 | sede1_secreto_2026 … | Sistema legado de cada sede: solo envía mensajes de su sede |
| portal_web | portal_web_secreto_2026 | Las vistas web (login) |

## Preparar la terminal (una vez por sesión)

```bash
source scripts/sesion_demo.sh
```

Deja definidas `$CURL` (curl que verifica HTTPS con la CA) y `$TOKEN` (token OAuth 2.0 pedido con client_credentials) y muestra qué contiene el token: algoritmo RS256, audiencia `hsb`, scopes y hora de vencimiento. El token dura 15 minutos; si el bus responde `401 ... expired`, se repite este comando.

## Paso 1 · Arranque limpio (A, minuto 0)

Todo sube con un solo comando desde bases vacías: genera certificados, crea las bases con sus roles y levanta los servicios. El servidor FHIR tarda 1 a 2 minutos.

```bash
bash desplegar.sh --desde-cero
```

```bash
docker compose ps
```

Esperado: `pg_sede1`, `mongo_sede2`, `pg_sede3` y `pg_central` en *healthy* y **sin puertos publicados**; `hapi_fhir_r4` solo en `127.0.0.1:8090`; `hsb_bus` y `api_gateway` en *Up*.

```bash
source scripts/sesion_demo.sh
```

```bash
$CURL https://localhost:8001/health | python3 -m json.tool
```

Esperado: `"status": "UP"` y las tres sedes con su motor (postgresql, mongodb, postgresql) en UP.

## Paso 2 · Cobertura FHIR en 0 % (B, minuto 2)

Recién arrancado, ningún paciente de las sedes está publicado en FHIR.

```bash
$CURL https://localhost:8000/metrics | python3 -m json.tool
```

Esperado: `cobertura_fhir_por_sede` en 0.0 para `sede_1`, `sede_2` y `sede_3`, y `auditoria_cadena_integra: true`.

En el navegador del PC: entrar como **auditor_elena** en `https://localhost:8000` y abrir la sección **FHIR** del panel para mostrar el 0 %.

## Paso 3 · Mensajes HL7 y CSV del docente (A, minuto 3)

Los cuatro archivos de `ejemplos/` dan exactamente el resultado del `LEEME.md`. Cada envío lleva el token: `-H "Authorization: Bearer $TOKEN"`.

```bash
$CURL -H "Authorization: Bearer $TOKEN" -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 https://localhost:8001/hsb/hl7 | python3 -m json.tool
```

```bash
$CURL -H "Authorization: Bearer $TOKEN" -X POST --data-binary @ejemplos/02_oru_r01_laboratorio_sede1.hl7 https://localhost:8001/hsb/hl7 | python3 -m json.tool
```

```bash
$CURL -H "Authorization: Bearer $TOKEN" -X POST --data-binary @ejemplos/03_adt_a01_invalido.hl7 https://localhost:8001/hsb/hl7 | python3 -m json.tool
```

```bash
$CURL -H "Authorization: Bearer $TOKEN" -X POST --data-binary @ejemplos/04_sede3_legado.csv "https://localhost:8001/hsb/csv?sede=3" | python3 -m json.tool
```

| Archivo | Resultado esperado |
| --- | --- |
| 01 admisión, sede 2 (MongoDB) | `entregado`: Patient 1007 y Condition J45.9 |
| 02 laboratorio, sede 1 (PostgreSQL) | `entregado`: Observation LOINC 718-7 = 13,8 g/dL |
| 03 admisión inválida | `rechazado` con 3 motivos: documento no numérico, sexo no válido, diagnóstico sin mapeo a CIE-10 |
| 04 CSV legado, sede 3 | 3 entregados (1008, 1009, 1010) y 2 rechazados |

La cobertura sube; vuelva a mirarla:

```bash
$CURL https://localhost:8000/metrics | python3 -m json.tool | grep -A4 cobertura_fhir_por_sede
```

## Paso 4 · Reenvío sin duplicados (B, minuto 5)

Reenviar el mismo mensaje no crea otro paciente: el bus responde `duplicado`.

```bash
$CURL -H "Authorization: Bearer $TOKEN" -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 https://localhost:8001/hsb/hl7 | python3 -m json.tool
```

Comprobar que hay un solo paciente 1007 en el servidor FHIR (esperado: `"total": 1`). HAPI solo responde dentro de la VM:

```bash
$CURL "https://localhost:8090/fhir/Patient?identifier=1007&_summary=count" | python3 -m json.tool | grep total
```

Y uno solo en la base de Cartagena, MongoDB (esperado: `1`). La conexión a MongoDB también exige TLS:

```bash
docker exec mongo_sede2 mongosh --quiet --tls --tlsCAFile /etc/mongo-tls/ca.pem --host localhost -u clinica_user -p clinica_pass_2026 --authenticationDatabase admin --eval 'db.getSiblingDB("clinica_cartagena").pacientes.countDocuments({_id:"1007"})'
```

## Paso 5 · Servidor FHIR caído: reintentos y mensaje muerto (A, intercalado)

Con el servidor FHIR apagado, el bus guarda el mensaje como `reintentando` y lo entrega solo cuando vuelve (esperas de 2, 4, 8, 16, 32 y 64 s; 7 intentos).

```bash
docker compose stop hapi-fhir
```

```bash
$CURL -H "Authorization: Bearer $TOKEN" -X POST --data-binary @tests/datos/06_adt_a03_57_campos_sede1.hl7 https://localhost:8001/hsb/hl7 | python3 -m json.tool | head -8
```

Esperado: `"estado": "reintentando"`. Encender el servidor y mirar el registro del bus (salir con Ctrl+C):

```bash
docker compose start hapi-fhir
```

```bash
docker compose logs -f hsb | grep MSG-0057
```

Esperado: líneas `HSB reintento n/7` y al final `Mensaje MSG-0057 ENTREGADO`. Si el servidor tardó más de unos 2 minutos, el mensaje queda `MUERTO`; con el servidor ya arriba se reencola y se entrega en segundos (reencolar exige el scope `hsb.admin`):

```bash
$CURL -H "Authorization: Bearer $TOKEN" -X POST https://localhost:8001/hsb/reencolar/MSG-0057 | python3 -m json.tool
```

Ver los mensajes por estado:

```bash
$CURL -H "Authorization: Bearer $TOKEN" "https://localhost:8001/hsb/mensajes?limite=10" | python3 -m json.tool | grep -E '"mensaje_id"|"estado"'
```

## Paso 6 · Caída de la sede de Cartagena (B, minuto 7)

Con la base MongoDB apagada, la consulta responde con las otras dos sedes y marca el reporte como incompleto.

Primero se inicia sesión como médico y se guarda la cookie (sirve para los pasos 6, 7 y 8):

```bash
$CURL -c /tmp/medico -o /dev/null -d "username=medico_mateo&password=Medico123!" https://localhost:8000/auth/login
```

```bash
docker stop mongo_sede2
```

```bash
$CURL -b /tmp/medico https://localhost:8000/api/pacientes/1001/historia | python3 -c "import sys,json; d=json.load(sys.stdin); print('completo:', d['reporte_completo'], '| sedes que respondieron:', d['sedes_disponibles']); print(d['aviso_incompletitud'])"
```

Esperado: `completo: False`, sedes `[1, 3]` y el aviso de que la sede de Cartagena no respondió.

```bash
$CURL https://localhost:8000/health | python3 -m json.tool | head -4
```

Esperado: `"status": "DEGRADED"` y `"nodos_activos": "2/3"`. En el navegador, el panel muestra la sede 2 en rojo. Volver a encenderla:

```bash
docker start mongo_sede2
```

Repetir la consulta de la historia: vuelve a `completo: True` con las sedes `[1, 2, 3]`.

## Paso 7 · Permisos por rol y auditoría alterada (A, minuto 9)

Los permisos se aplican en la API, no solo en la pantalla. Se inicia sesión con el paciente y con la admisionista:

```bash
$CURL -c /tmp/paciente -o /dev/null -d "username=paciente_carlos&password=Paciente123!" https://localhost:8000/auth/login
$CURL -c /tmp/admision -o /dev/null -d "username=admision_laura&password=Admision123!" https://localhost:8000/auth/login
```

El paciente Carlos (documento 1001) pide la historia de otra persona (1002):

```bash
$CURL -o /dev/null -w "%{http_code}\n" -b /tmp/paciente https://localhost:8000/api/pacientes/1002/historia
```

Esperado: `403`. Su propia historia (`/api/pacientes/1001/historia`) sí devuelve `200`.

La admisionista pide una historia clínica:

```bash
$CURL -o /dev/null -w "%{http_code}\n" -b /tmp/admision https://localhost:8000/api/pacientes/1001/historia
```

Esperado: `403`. Admisión solo ve datos de identificación, no diagnósticos.

### Alterar la auditoría a mano

La aplicación no puede cambiar la auditoría (su rol `api_central` solo tiene INSERT y SELECT; ver el paso 9). Por eso la alteración la hace el DBA, entrando directamente al contenedor de la base central:

```bash
docker exec -it pg_central psql -U clinica_user -d clinica_central -c "UPDATE evento_auditoria SET usuario_sistema='intruso' WHERE indice = 3;"
```

La auditora verifica la cadena:

```bash
$CURL -c /tmp/auditor -o /dev/null -d "username=auditor_elena&password=Auditor123!" https://localhost:8000/auth/login
$CURL -b /tmp/auditor https://localhost:8000/api/auditoria/verificar | python3 -m json.tool
```

Esperado: `"cadena_integra": false`, `detalle_alteracion` con `"indice": 3` y el motivo "Alteración de contenido". En el navegador se ve igual en el panel, sección Auditoría, en rojo.

> Esta prueba deja la cadena marcada como alterada. Para dejarla limpia, ver "Cómo dejar todo como estaba" al final.

## Paso 8 · Historia de las tres sedes, FHIR, ACID y los 57 campos (A+B, minuto 11)

### Una historia armada desde tres sedes y dos motores

```bash
$CURL -b /tmp/medico https://localhost:8000/api/pacientes/1001/historia | python3 -c "import sys,json; d=json.load(sys.stdin); print('sedes:', d['sedes_con_registros'], '| completo:', d['reporte_completo']); [print(a['numero_visita'], a['sede_origen'], a['motor_origen']) for a in d['atenciones']]"
```

Esperado: atenciones de Sincelejo (PostgreSQL), Cartagena (MongoDB) y Corozal (PostgreSQL) en una sola respuesta.

### Validar el paquete FHIR en HAPI

```bash
$CURL -b /tmp/medico https://localhost:8000/api/pacientes/1001/bundle -o /tmp/bundle.json
$CURL -X POST -H "Content-Type: application/fhir+json" --data @/tmp/bundle.json "https://localhost:8090/fhir/Bundle/\$validate" | grep -c '"severity": "error"'
```

Esperado: `0` errores. Desde fuera de la VM, FHIR se consulta por la pasarela autenticada de la API: `https://localhost:8000/fhir/...` con la sesión de médico, auditor o administrador.

### Atomicidad (la A de ACID)

```bash
docker exec -i pg_sede1 psql -U clinica_user -d clinica_sincelejo < db/demo_acid.sql
```

Esperado: el segundo INSERT falla por el triage `9`, la transacción hace ROLLBACK y el paciente 9999 no queda guardado.

### Migración a FHIR al 100 %

```bash
$CURL -H "Authorization: Bearer $TOKEN" -X POST https://localhost:8001/hsb/migrar | python3 -m json.tool
```

Esperado: cobertura de 100 % en cada sede. Se puede repetir sin crear duplicados.

### Dónde se ven los 57 campos

1. **En pantalla (lo más claro para el profe).** Con la sesión del médico o del auditor, abrir `https://localhost:8000/reporte?buscar_doc=1020`. Tiene dos secciones: "Completitud del registro (Resolución 866 de 2021)", con el porcentaje de campos llenos, y "Datos del registro clínico", con los 57 campos numerados, su valor y la sede de donde salió cada uno.
2. **El catálogo del traductor**, con número, nombre, tipo y dónde se guarda cada campo en cada motor:

```bash
$CURL https://localhost:8001/hsb/catalogo | python3 -m json.tool | less
```

3. **En el código:** `traductor/catalogo_57.py` (la definición) y `docs/mapeo_57_campos.md` (la tabla campo por campo: HL7, columna en PostgreSQL, ruta en MongoDB y recurso FHIR).

## Paso 9 · Seguridad: OAuth 2.0, bases de datos y cifrado entre servidores (A+B, minuto 13)

### OAuth 2.0: el servidor de autorización

Metadatos del servidor (RFC 8414) y la clave pública con la que se verifican los tokens (RFC 7517):

```bash
$CURL https://localhost:8000/.well-known/oauth-authorization-server | python3 -m json.tool
$CURL https://localhost:8000/oauth/jwks | python3 -m json.tool
```

Token de un usuario con el flujo `password` (el médico) y lo que lleva dentro: emisor, audiencia `api`, rol y scopes del rol.

```bash
$CURL -u herramientas_qa:qa_secreto_2026 -d "grant_type=password&username=medico_mateo&password=Medico123!" https://localhost:8000/oauth/token | tee /tmp/tok.json | python3 -m json.tool
python3 -c "import json,base64; t=json.load(open('/tmp/tok.json'))['access_token'].split('.')[1]; print(json.dumps(json.loads(base64.urlsafe_b64decode(t+'='*(-len(t)%4))), indent=2, ensure_ascii=False))"
```

Renovar con el `refresh_token` (rotación: el viejo deja de servir) y revocarlo:

```bash
R=$(python3 -c "import json; print(json.load(open('/tmp/tok.json'))['refresh_token'])")
$CURL -u herramientas_qa:qa_secreto_2026 -d "grant_type=refresh_token&refresh_token=$R" https://localhost:8000/oauth/token | python3 -m json.tool | head -4
$CURL -u herramientas_qa:qa_secreto_2026 -d "grant_type=refresh_token&refresh_token=$R" https://localhost:8000/oauth/token
```

Esperado: el primero entrega tokens nuevos; el segundo, `{"error":"invalid_grant",...}`.

### OAuth 2.0: el bus solo acepta tokens válidos

```bash
$CURL -o /dev/null -w "sin token: %{http_code}\n" -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 https://localhost:8001/hsb/hl7
U=$(python3 -c "import json; print(json.load(open('/tmp/tok.json'))['access_token'])")
$CURL -o /dev/null -w "token de usuario: %{http_code}\n" -H "Authorization: Bearer $U" -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 https://localhost:8001/hsb/hl7
S1=$($CURL -u sistema_sede1:sede1_secreto_2026 -d grant_type=client_credentials https://localhost:8000/oauth/token | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
$CURL -H "Authorization: Bearer $S1" -X POST --data-binary @ejemplos/04_sede3_legado.csv "https://localhost:8001/hsb/csv?sede=3"; echo
$CURL -o /dev/null -w "secreto falso: %{http_code}\n" -u herramientas_qa:falso -d grant_type=client_credentials https://localhost:8000/oauth/token
```

Esperado: `sin token: 401`; `token de usuario: 401` (su audiencia es `api`, no `hsb`); el sistema de la sede 1 enviando un CSV de la sede 3 recibe `403 insufficient_scope`; `secreto falso: 401`.

### Bases de datos: mínimo privilegio, auditoría de solo agregar y TLS obligatorio

```bash
bash scripts/demo_seguridad_bd.sh
```

Esperado, en orden:

1. Las bases no publican puertos.
2. El bus (`hsb_escritor`) no puede borrar: `permission denied`.
3. La API (`api_lector`) no puede modificar las sedes, solo leer.
4. La API (`api_central`) no puede alterar ni borrar la auditoría.
5. MongoDB rechaza el insert de `api_lector` y el borrado de `hsb_escritor`.
6. Sin TLS no se entra a PostgreSQL ni a MongoDB.
7. El registro de PostgreSQL muestra cada servicio con su rol y `SSL enabled (protocol=TLSv1.3)`.

### Cifrado entre servidores: certificados de la CA propia

```bash
openssl s_client -connect localhost:8001 -servername hsb -CAfile certs/ca.pem </dev/null 2>/dev/null | grep -E "subject=|issuer=|Verify return code|Protocol"
$CURL -o /dev/null -w "HAPI por HTTPS: %{http_code}\n" https://localhost:8090/fhir/metadata
curl -s -o /dev/null -w "HAPI por HTTP plano: %{http_code}\n" http://localhost:8090/fhir/metadata
```

Esperado: certificado del bus emitido por "CA Plataforma Interoperabilidad", `Verify return code: 0 (ok)` y TLS 1.3; HAPI responde `200` por HTTPS y `400` por HTTP plano.

## Verificación completa y pruebas automáticas

Si el profe pide "pruébenlo todo", estos comandos lo cubren en pocos minutos.

Verificación de interoperabilidad y seguridad por sede (en la VM):

```bash
python3 scripts/verificar_interoperabilidad.py --api https://localhost:8000 --hsb https://localhost:8001 --fhir https://localhost:8090/fhir --ca certs/ca.pem
```

Esperado: `70/70` comprobaciones superadas (63 de interoperabilidad y 7 de OAuth 2.0 y HTTPS). El detalle queda en `docs/evidencias/07_verificacion_por_sede.md`.

Colección de Postman con Newman, desde el PC (58 peticiones, 82 aserciones; la carpeta 0 pide los tokens OAuth):

```bash
npx newman run docs/coleccion/Plataforma_Interoperabilidad.postman_collection.json -e docs/coleccion/entorno_local.postman_environment.json --ssl-extra-ca-certs certs/ca.pem
```

Pruebas unitarias (en el PC, dentro de la carpeta del proyecto):

```bash
python -m pytest tests -q
```

Esperado: `60 passed` (44 anteriores y 16 de OAuth 2.0 y autorización del bus).

## Cómo dejar todo como estaba

Después del paso 7 la auditoría queda marcada como alterada. Para volver a una plataforma limpia con datos de prueba y cobertura al 100 %:

```bash
bash desplegar.sh --desde-cero --con-datos
```

Si la sede de Cartagena sigue apagada por el paso 6:

```bash
docker start mongo_sede2
```

Apagar la plataforma al terminar la clase (los datos se conservan):

```bash
bash desplegar.sh --detener
```
