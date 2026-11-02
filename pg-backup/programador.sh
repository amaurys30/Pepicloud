#!/bin/bash
# Full inicial (si no existe) e incrementales periodicos cada BACKUP_INTERVALO_MIN minutos.
set -uo pipefail
INTERVALO=$(( ${BACKUP_INTERVALO_MIN:-10} * 60 ))

until pg_isready -h postgres -q; do sleep 2; done
if ! ls -d /backups/*_full >/dev/null 2>&1; then
  respaldo.sh full
fi
echo "[programador] Incrementales cada ${BACKUP_INTERVALO_MIN:-10} minutos"
while true; do
  sleep "$INTERVALO"
  respaldo.sh incremental || echo "[programador] ERROR en el incremental"
done
