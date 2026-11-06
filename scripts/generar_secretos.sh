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

# Credenciales para que las APIs hablen con LocalStack (acepta cualquier valor,
# pero se manejan como secreto igual que en produccion)
if [[ ! -f secrets/aws_credentials ]]; then
  printf '[default]\naws_access_key_id = test\naws_secret_access_key = test\n' > secrets/aws_credentials
  echo "Creado:    secrets/aws_credentials"
fi
chmod 644 secrets/aws_credentials

# Material de la clave maestra KMS (32 bytes = AES-256). Permite recrear la MISMA
# clave si el contenedor localstack-kms se reinicia; sin el, los documentos son irrecuperables.
if [[ ! -f secrets/kms_key_material.txt ]]; then
  head -c 32 /dev/urandom | base64 -w0 > secrets/kms_key_material.txt
  echo "Creado:    secrets/kms_key_material.txt"
fi
chmod 644 secrets/kms_key_material.txt

# Token de administrador para eliminar documentos (api-registro)
if [[ ! -f secrets/api_admin_token.txt ]]; then
  head -c 1024 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c 32 > secrets/api_admin_token.txt || true
  echo "Creado:    secrets/api_admin_token.txt"
fi
chmod 644 secrets/api_admin_token.txt

# Credenciales de MinIO (copias A, B y backup). Las aplicaciones usan las mismas
# a traves de secrets/aws_credentials (LocalStack-KMS acepta cualquier credencial).
if [[ ! -f secrets/minio_root_user.txt ]]; then
  printf 'pepicloud' > secrets/minio_root_user.txt
  echo "Creado:    secrets/minio_root_user.txt"
fi
if [[ ! -f secrets/minio_root_password.txt ]]; then
  generar > secrets/minio_root_password.txt
  echo "Creado:    secrets/minio_root_password.txt"
fi
minio_usuario=$(cat secrets/minio_root_user.txt)
minio_clave=$(cat secrets/minio_root_password.txt)
if ! grep -qF "$minio_clave" secrets/aws_credentials 2>/dev/null; then
  printf '[default]\naws_access_key_id = %s\naws_secret_access_key = %s\n' "$minio_usuario" "$minio_clave" > secrets/aws_credentials
  echo "Actualizado: secrets/aws_credentials (credenciales de MinIO)"
fi
chmod 644 secrets/minio_root_user.txt secrets/minio_root_password.txt secrets/aws_credentials
