# Guía de Ejecución en Kali Linux
## Plataforma Distribuida de Interoperabilidad Clínica

---

### 1. Preparar el Entorno en Kali Linux

Abre una terminal (`qterminal` o `bash`) en Kali Linux y verifica las herramientas necesarias:

```bash
# 1. Actualizar repositorios e instalar paquetes base
sudo apt update
sudo apt install -y git curl jq docker.io docker-compose-plugin

# 2. Iniciar y habilitar el servicio de Docker
sudo systemctl start docker
sudo systemctl enable docker

# 3. Permitir ejecutar Docker sin 'sudo'
sudo usermod -aG docker $USER
newgrp docker

# 4. Comprobar que Docker responde sin sudo
docker ps
```

---

### 2. Clonar el Repositorio

```bash
cd ~
git clone https://github.com/jose18000/parcial_2.git
cd parcial_2

# Comprobar estado y etiqueta v1.0
git log -n 3 --oneline
git tag -l
```

---

### 3. Configurar Variables de Entorno y Desplegar

```bash
# Copiar plantilla .env
cp .env.example .env

# Levantar los 6 servicios en un solo comando
docker compose down -v && docker compose up -d --build

# Verificar que los 6 contenedores estén saludables
docker compose ps
```

---

### 4. Ejecutar el Guion de Demostración (15 Minutos)

Abre **Firefox** en Kali Linux e interactúa en paralelo con la terminal:

1. **Apertura y Cobertura 0 %:**
   - Entra a `http://localhost:8000/login`
   - Ingresa como `auditor_elena` / `Auditor123!`
   - Muestra en el Tablero que la Cobertura FHIR arranca en **0.0%**.

2. **Ingesta de HL7 y CSV (Subida de Cobertura):**
   ```bash
   # HL7 ADT^A01 válido Sede 2
   curl -X POST http://localhost:8001/hsb/hl7 \
     -H "Content-Type: text/plain" \
     --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7

   # CSV legado Sede 3 (3 entregados, 2 rechazados)
   curl -X POST "http://localhost:8001/hsb/csv?sede=3" \
     -H "Content-Type: text/csv" \
     --data-binary @ejemplos/04_sede3_legado.csv
   ```
   Refresca `/reporte` en Firefox y muestra cómo sube la cobertura FHIR.

3. **Demostración de Idempotencia:**
   ```bash
   curl -X POST http://localhost:8001/hsb/hl7 \
     -H "Content-Type: text/plain" \
     --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7
   ```
   Responde `{"estado": "duplicado"}` sin duplicar filas en PostgreSQL.

4. **Demostración de Caída de Sede en Vivo (CAP - AP):**
   ```bash
   docker stop pg_sede2
   ```
   En Firefox `/reporte`, el sistema no falla: responde con sedes 1 y 3 y avisa la incompletitud.
   ```bash
   docker start pg_sede2
   ```
   Se recupera inmediatamente al siguiente refresco.

5. **Detección de Auditoría Adulterada:**
   - En `/reporte`, haz clic en `⚠️ Demostrar Alteración en Vivo`.
   - La caja de auditoría cambia a **ROJO** (`¡ALERTA! ALTERACIÓN DETECTADA`), indicando el índice y bloque exacto adulterado.

6. **Las 4 Vistas por Rol:**
   - **Médico (`medico_mateo` / `Medico123!`):** Consulta paciente `1001` (3 sedes reunidas) y emite egreso con sello hash.
   - **Admisionista (`admision_laura` / `Admision123!`):** Admite con triage y sin acceso a diagnósticos (mínimo privilegio).
   - **Paciente (`paciente_carlos` / `Paciente123!`):** Descarga su Bundle FHIR R4 y revisa el log de accesos (Ley 1581).

---

### 5. Pruebas Automatizadas

```bash
python3 -m unittest tests/fase2/test_normalizer.py
python3 -m unittest tests/fase3/test_hsb_integration.py
python3 -m unittest tests/fase4/test_security_resilience.py
```
*(Todas pasan con 100 % de éxito).*

