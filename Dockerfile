# Imagen oficial ligera de Python 3.11 para EcoConecta Backend
FROM python:3.11-slim

# Variables de entorno para optimización y seguridad en contenedores
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Instalación de dependencias del sistema necesarias para compilación y PostgreSQL
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Instalación de paquetes Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Creación de usuario no privilegiado por buenas prácticas de seguridad (Snyk / DevSecOps)
RUN adduser --disabled-password --gecos "" ecouser
COPY . .
RUN chown -R ecouser:ecouser /app
USER ecouser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

