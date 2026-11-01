#!/usr/bin/env bash
# Verifica trigger de inmutabilidad y permisos por servicio. No deja datos.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T postgres psql -q -U pepicloud_admin -d pepicloud -f - < pruebas/sql/prueba_bd.sql 2>&1 \
  | sed -E 's/^psql:[^ ]+ NOTICE:  //'
