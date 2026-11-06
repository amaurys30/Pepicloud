# Imagen comun para api-registro, api-consulta, worker-backup y s3-init.
# No contiene credenciales: todas llegan en tiempo de ejecucion (Docker secrets / Secrets Manager).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Usuario sin privilegios: el codigo no corre como root
RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY comun/ comun/
COPY api_registro/ api_registro/
COPY api_consulta/ api_consulta/
COPY worker_backup/ worker_backup/

USER app
CMD ["python", "-m", "comun.diagnostico"]
