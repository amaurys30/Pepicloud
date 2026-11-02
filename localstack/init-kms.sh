#!/bin/bash
# Se ejecuta dentro de localstack-kms cuando esta listo.
#  1. Crea la clave maestra KMS para el cifrado de sobre de los documentos.
#  2. Carga en Secrets Manager las credenciales de BD de cada servicio.
set -euo pipefail

ALIAS="alias/pepicloud-docs"
KEY_ID="9e5c2b1a-7d3f-4c8e-a1b2-5e91c10d0001"   # ID fijo: siempre la misma clave

if awslocal kms describe-key --key-id "$KEY_ID" >/dev/null 2>&1; then
  echo "[init] La clave $KEY_ID ya existe"
else
  MATERIAL=$(tr -d '
' < /run/secrets/kms_key_material)
  awslocal kms create-key \
    --description "PepiCloud - clave maestra de documentos" \
    --key-usage ENCRYPT_DECRYPT --key-spec SYMMETRIC_DEFAULT \
    --tags "[{\"TagKey\":\"_custom_id_\",\"TagValue\":\"$KEY_ID\"},{\"TagKey\":\"_custom_key_material_\",\"TagValue\":\"$MATERIAL\"}]" \
    >/dev/null
  awslocal kms create-alias --alias-name "$ALIAS" --target-key-id "$KEY_ID"
  echo "[init] Clave KMS creada con ID y material fijos: $KEY_ID ($ALIAS)"
fi

cargar_secreto() {
  local nombre="$1" usuario="$2" archivo="/run/secrets/$3"
  local clave valor
  clave=$(tr -d '\r\n' < "$archivo")
  valor=$(printf '{"usuario":"%s","clave":"%s","host":"postgres","puerto":5432,"bd":"pepicloud"}' \
          "$usuario" "$clave")
  if awslocal secretsmanager describe-secret --secret-id "$nombre" >/dev/null 2>&1; then
    awslocal secretsmanager put-secret-value --secret-id "$nombre" --secret-string "$valor" >/dev/null
    echo "[init] Secreto $nombre actualizado"
  else
    awslocal secretsmanager create-secret --name "$nombre" \
      --description "Credenciales PostgreSQL de $usuario" --secret-string "$valor" >/dev/null
    echo "[init] Secreto $nombre creado"
  fi
}

cargar_secreto "pepicloud/db/registro" "usr_registro" "pg_registro_password"
cargar_secreto "pepicloud/db/consulta" "usr_consulta" "pg_consulta_password"
cargar_secreto "pepicloud/db/worker"   "usr_worker"   "pg_worker_password"
