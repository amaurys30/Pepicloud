#!/usr/bin/env bash
# Genera contrasenas aleatorias en secrets/ (excluida de git).
# No sobrescribe archivos existentes.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p secrets

generar() {
  # 24 caracteres alfanumericos, sin salto de linea
  local s
  s=$(head -c 1024 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9')
  printf '%s' "${s:0:24}"
}

for nombre in pg_admin_password pg_replicador_password pg_registro_password \
              pg_consulta_password pg_worker_password; do
  archivo="secrets/${nombre}.txt"
  if [[ -f "$archivo" ]]; then
    echo "Ya existe: $archivo (se conserva)"
  else
    generar > "$archivo"
    echo "Creado:    $archivo"
  fi
done

chmod 700 secrets
chmod 644 secrets/*.txt
