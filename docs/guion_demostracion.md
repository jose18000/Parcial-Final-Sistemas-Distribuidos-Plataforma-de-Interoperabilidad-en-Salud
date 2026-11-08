# Guion de Sustentación en Vivo (15 Minutos)
## Plataforma Distribuida de Interoperabilidad Clínica

**Equipo:** Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)  
**Modalidad:** Demostración práctica en vivo sin pasos manuales fuera del README.

---

## Estructura del Tiempo (15 min Demo + 10 min Preguntas)

| Minuto | Paso de la Demostración | Responsable Principal | Qué se Muestra en Pantalla |
|--------|--------------------------|-----------------------|----------------------------|
| **00:00 - 02:00** | Paso 1: Arranque limpio desde cero | **A (Jose Canchila)** | Terminal: `docker compose down -v && docker compose up -d` y `docker compose ps` (6 servicios saludables). |
| **02:00 - 04:00** | Paso 2: Cobertura FHIR inicial al 0 % | **B (Sharit Manjarrez)**| Navegador: Login como `auditor_elena` $\to$ `/reporte`. Tablero muestra Cobertura FHIR: **0 %** en las 3 sedes. |
| **04:00 - 07:00** | Paso 3: Ingesta de HL7 y CSV (Cobertura sube) | **A (Jose Canchila)** | Terminal: Enviar `01_adt_a01_valido_sede2.hl7` y `04_sede3_legado.csv` con cURL. Refrescar tablero: cobertura sube y aparece Bundle. |
| **07:00 - 09:00** | Paso 4: Idempotencia persistente comprobada | **B (Sharit Manjarrez)**| Terminal: Reenviar `01_adt_a01_valido_sede2.hl7`. El bus responde `{"estado": "duplicado"}`. La BD sólo tiene un paciente 1007. |
| **09:00 - 11:30** | Paso 5: Caída de Sede en Vivo (Resiliencia CAP) | **A (Jose Canchila)** | Terminal: `docker stop pg_sede2`. Refrescar `/reporte`: el sistema responde con sedes 1 y 3, avisa la caída y marca reporte parcial. `docker start pg_sede2` $\to$ se recupera. |
| **11:30 - 13:30** | Paso 6: Detección de Auditoría Adulterada | **B (Sharit Manjarrez)**| Navegador / cURL: Clic en *"Demostrar Alteración en Vivo"*. El verificador SHA-256 cambia a rojo y señala el bloque adulterado. |
| **13:30 - 15:00** | Paso 7: Consulta Unificada en 3 Sedes (Carlos Pérez) | **A + B (Ambos)** | Navegador: Login como `medico_mateo` $\to$ Consulta doc `1001`. Aparecen atenciones de Sincelejo, Cartagena y Corozal con sello médico. |

---

## Comandos y Salidas Esperadas Paso a Paso

### Paso 1: Arranque limpio desde cero (2 min)
```bash
# Limpiar volúmenes y reiniciar
docker compose down -v
docker compose up -d

# Verificar estado de los 6 contenedores
docker compose ps
```
*Salida esperada:*
- `pg_sede1` (Sincelejo :5433) $\to$ `healthy`
- `pg_sede2` (Cartagena :5434) $\to$ `healthy`
- `pg_sede3` (Corozal :5435) $\to$ `healthy`
- `hapi_fhir` (HAPI FHIR R4 :8090) $\to$ `healthy`
- `hsb_bus` (HSB :8001) $\to$ `running`
- `api_gateway` (API Gateway :8000) $\to$ `running`

---

### Paso 2: Cobertura FHIR en 0 % (2 min)
1. Abrir navegador en: `http://localhost:8000/login`
2. Hacer clic en el pill rápido: **Auditor (Central)** (`auditor_elena` / `Auditor123!`).
3. Observar el Tablero de Observabilidad:
   - Cobertura FHIR Sincelejo: **0.0%** (0 de 2 pacientes con `fhir_patient_id`).
   - Cobertura FHIR Cartagena: **0.0%** (0 de 2 pacientes con `fhir_patient_id`).
   - Cobertura FHIR Corozal: **0.0%** (0 de 4 pacientes con `fhir_patient_id`).
   - *Explicación al docente:* Los datos legados inician sin mapeo FHIR para demostrar la migración gradual.

---

### Paso 3: Envío de HL7 y CSV (La cobertura sube) (3 min)
Ejecutar en la terminal:
```bash
# 1. Enviar HL7 ADT^A01 válido (Andrea Rojas - Doc 1007, Sede 2 Cartagena)
curl -X POST http://localhost:8001/hsb/hl7 \
  -H "Content-Type: text/plain" \
  --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7

# 2. Enviar CSV legado Sede 3 (3 entregados: 1008, 1009, 1010; 2 rechazados)
curl -X POST "http://localhost:8001/hsb/csv?sede=3" \
  -H "Content-Type: text/csv" \
  --data-binary @ejemplos/04_sede3_legado.csv
```
*Resultado en pantalla:*
- El HSB responde `200 OK` con `estado: entregado` y `bundle_id: bundle-pac-1007`.
- El CSV responde `total_entregados: 3, total_rechazados: 2`.
- Al refrescar el Tablero web en `/reporte`, la cobertura FHIR de Sede 2 y Sede 3 sube visiblemente.

---

### Paso 4: Reenvío del mensaje (Idempotencia demostrada) (2 min)
Reenviar el archivo 01 inmediatamente:
```bash
curl -X POST http://localhost:8001/hsb/hl7 \
  -H "Content-Type: text/plain" \
  --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7
```
*Salida esperada:*
```json
{
  "estado": "duplicado",
  "mensaje_id": "MSG-0001",
  "bundle_id": "bundle-pac-1007",
  "motivo": "Mensaje procesado previamente. Idempotencia garantizada, no se duplicó el paciente ni la atención."
}
```
*Comprobación en base de datos:*
```bash
docker exec -i pg_sede2 psql -U clinica_user -d clinica_cartagena -c "SELECT COUNT(*) FROM usuario WHERE documento_id='1007';"
```
*(Devuelve exactamente `1`, demostrando que no se crean duplicados).*

---

### Paso 5: Caída en vivo de una sede (Resiliencia CAP) (2.5 min)
```bash
# Simular caída imprevista de la sede Cartagena
docker stop pg_sede2

# Consultar la historia del paciente 1001 (que tiene atenciones en las 3 sedes)
curl -s http://localhost:8000/api/pacientes/1001/historia | jq '{reporte_completo, sedes_disponibles, sedes_no_disponibles}'
```
*Salida esperada:*
```json
{
  "reporte_completo": false,
  "sedes_disponibles": [1, 3],
  "sedes_no_disponibles": [
    {
      "sede_id": 2,
      "nombre": "Sede 2 - Cartagena",
      "motivo": "conexión rechazada o tiempo agotado"
    }
  ]
}
```
- En el navegador `/reporte`, aparece la alerta amarilla: *"⚠️ REPORTE CLÍNICO INCOMPLETO: Sede 2 no disponible"*.
- Reactivar Cartagena:
  ```bash
  docker start pg_sede2
  ```
- Al refrescar el navegador, la Sede 2 vuelve a aparecer en verde y el reporte se marca nuevamente como completo.

---

### Paso 6: Alteración manual de auditoría y detección (2 min)
1. En el Tablero de `/reporte`, la caja de auditoría dice en verde: **`INTEGRA (Sin alteraciones)`**.
2. Hacer clic en el botón rojo: **`⚠️ Demostrar Alteración en Vivo`** (o ejecutar por terminal `curl -X POST http://localhost:8000/api/auditoria/alterar-prueba`).
3. La página recarga y la caja cambia inmediatamente a **ROJO**:
   - **`¡ALERTA! ALTERACIÓN DETECTADA`**
   - Muestra el ID del bloque adulterado (`c71a39...`), índice `0`, y motivo: *"Alteración de contenido: el hash_propio no corresponde con los datos del bloque"*.
4. *Explicación al docente:* El verificador recalculó matemáticamente la cadena y descubrió que el contenido del evento fue modificado en base de datos sin autorización.

---

### Paso 7: Consulta Unificada del Paciente 1001 y las 4 Vistas (2 min)
1. Iniciar sesión como `medico_mateo` (`Medico123!`).
2. Consultar paciente `1001` (Carlos Pérez).
3. Mostrar en pantalla cómo una sola vista reúne:
   - Atención de Urgencia en **Sincelejo** (`V-S1-0150`, Hemoglobina 13.8 g/dL).
   - Control de Asma en **Cartagena** (`V-S2-0080`, PCR 2.1 mg/L).
   - Consulta por Gastroenteritis en **Corozal** (`V-S3-0045`, Sodio y Potasio).
4. Hacer clic en *"Firmar Registro y Obtener Sello Criptográfico"* y mostrar el hash SHA-256 generado en verde.
5. Iniciar sesión como `paciente_carlos` (`Paciente123!`) y mostrar el botón *"Descargar mi Bundle FHIR R4"* y la trazabilidad de accesos.
