#!/bin/bash
# Se ejecuta dentro de cada instancia LocalStack de almacenamiento cuando esta lista.
# Crea el bucket BUCKET_NAME con Object Lock y bloquea el acceso publico.
# Si existe BUCKET_EXTRA, tambien lo crea.
set -euo pipefail

crear_bucket() {
  local bucket="$1"
  if awslocal s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
    echo "[init] Bucket $bucket ya existe"
    return
  fi

  # Object Lock solo se activa al crear el bucket; activa el versionado automaticamente
  awslocal s3api create-bucket --bucket "$bucket" --object-lock-enabled-for-bucket

  awslocal s3api put-public-access-block --bucket "$bucket" \
    --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

  echo "[init] Bucket $bucket creado con Object Lock en $(hostname)"
}

crear_bucket "${BUCKET_NAME:?Falta BUCKET_NAME}"

if [[ -n "${BUCKET_EXTRA:-}" ]]; then
  crear_bucket "$BUCKET_EXTRA"
fi
