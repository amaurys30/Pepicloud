# Imagen comun para api-registro, api-consulta y worker-backup.
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

# Boveda del backup (volumen): el usuario app debe poder escribir en ella
RUN mkdir -p /boveda && chown app:app /boveda

USER app
CMD ["python", "-m", "comun.diagnostico"]
