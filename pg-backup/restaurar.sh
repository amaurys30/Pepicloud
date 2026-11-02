#!/bin/bash
# Reconstruye en /restore/data la base a partir de la cadena full + incrementales.
# Uso: restaurar.sh [nombre_del_ultimo_backup_a_incluir]   (por defecto, el mas reciente)
set -euo pipefail

DIR=/backups
HASTA="${1:-}"
mapfile -t todos < <(ls -1d "$DIR"/*_full "$DIR"/*_incremental 2>/dev/null | sort)
[[ ${#todos[@]} -gt 0 ]] || { echo "No hay backups"; exit 1; }

cadena=()
for d in "${todos[@]}"; do
  [[ "$d" == *_full ]] && cadena=()          # cada full inicia una cadena nueva
  cadena+=("$d")
  [[ -n "$HASTA" && "$(basename "$d")" == "$HASTA" ]] && break
done

echo "[restaurar] Cadena a combinar:"
printf '   %s\n' "${cadena[@]##*/}"

rm -rf /restore/data
pg_combinebackup "${cadena[@]}" -o /restore/data
chmod 700 /restore/data
echo "[restaurar] Base reconstruida en /restore/data ($(du -sh /restore/data | cut -f1))"
