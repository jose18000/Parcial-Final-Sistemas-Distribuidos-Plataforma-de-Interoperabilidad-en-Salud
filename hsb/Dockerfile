FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar
COPY hsb/requirements.txt /app/hsb/requirements.txt
RUN pip install --no-cache-dir -r /app/hsb/requirements.txt

# Copiar módulos del proyecto necesarios para el HSB
COPY hsb /app/hsb
COPY fhir /app/fhir
COPY ejemplos /app/ejemplos

ENV PYTHONPATH=/app
EXPOSE 8001

CMD ["uvicorn", "hsb.main:app", "--host", "0.0.0.0", "--port", "8001"]

