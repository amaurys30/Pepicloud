#!/bin/bash
# Backup fisico de PostgreSQL 17.  Uso: respaldo.sh full | incremental
# Los backups quedan en /backups (volumen separado del de la base de datos).
set -euo pipefail

TIPO="${1:?Uso: respaldo.sh full|incremental}"
DIR=/backups
CATALOGO="$DIR/catalogo.txt"

# Credencial del usuario de replicacion, leida del Docker secret
export PGPASSFILE=/tmp/.pgpass
printf 'postgres:5432:*:replicador:%s\n' "$(tr -d '\r\n' < /run/secrets/pg_replicador_password)" > "$PGPASSFILE"
chmod 600 "$PGPASSFILE"

anterior=$(ls -1d "$DIR"/*_full "$DIR"/*_incremental 2>/dev/null | sort | tail -1 || true)
if [[ "$TIPO" == "incremental" && -z "$anterior" ]]; then
  echo "[respaldo] No existe un backup previo: se hace uno completo"
  TIPO=full
fi

nombre="$(date +%Y%m%d_%H%M%S)_${TIPO}"
destino="$DIR/$nombre"
args=(-h postgres -U replicador -D "$destino" --checkpoint=fast --no-password)
base="-"
if [[ "$TIPO" == "incremental" ]]; then
  args+=(--incremental="$anterior/backup_manifest")
  base=$(basename "$anterior")
fi

inicio=$(date +%s)
pg_basebackup "${args[@]}"
duracion=$(( $(date +%s) - inicio ))

if [[ "$TIPO" == "full" ]]; then
  pg_verifybackup -q "$destino" && echo "[respaldo] Backup completo verificado"
fi

tamano=$(du -sh "$destino" | cut -f1)
printf '%-28s %-12s %-28s %6s %4ss\n' "$nombre" "$TIPO" "$base" "$tamano" "$duracion" >> "$CATALOGO"
echo "[respaldo] $nombre listo ($tamano, ${duracion}s, base: $base)"
