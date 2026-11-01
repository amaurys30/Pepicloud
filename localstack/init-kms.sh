#!/bin/bash
# Se ejecuta dentro de localstack-kms cuando esta listo.
#  1. Crea la clave maestra KMS para el cifrado de sobre de los documentos.
#  2. Carga en Secrets Manager las credenciales de BD de cada servicio.
set -euo pipefail

ALIAS="alias/pepicloud-docs"

if awslocal kms describe-key --key-id "$ALIAS" >/dev/null 2>&1; then
  echo "[init] La clave $ALIAS ya existe"
else
  KEY_ID=$(awslocal kms create-key \
    --description "PepiCloud - clave maestra de documentos" \
    --key-usage ENCRYPT_DECRYPT --key-spec SYMMETRIC_DEFAULT \
    --query KeyMetadata.KeyId --output text)
  awslocal kms create-alias --alias-name "$ALIAS" --target-key-id "$KEY_ID"
  echo "[init] Clave KMS creada: $KEY_ID ($ALIAS)"
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
