#!/bin/bash
# Se ejecuta UNA vez, al crear la base. Un usuario por servicio (minimo privilegio)
# y el usuario de replicacion para los backups (fase 5).
set -euo pipefail

leer() { tr -d '\r\n' < "/run/secrets/$1"; }

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v clave_registro="$(leer pg_registro_password)" \
  -v clave_consulta="$(leer pg_consulta_password)" \
  -v clave_worker="$(leer pg_worker_password)" \
  -v clave_replicador="$(leer pg_replicador_password)" <<'SQL'
CREATE ROLE usr_registro LOGIN PASSWORD :'clave_registro';
CREATE ROLE usr_consulta LOGIN PASSWORD :'clave_consulta';
CREATE ROLE usr_worker   LOGIN PASSWORD :'clave_worker';
CREATE ROLE replicador   LOGIN REPLICATION PASSWORD :'clave_replicador';
SQL

# Permitir conexiones de replicacion (pg_basebackup) desde la red de Docker
echo "host replication replicador all scram-sha-256" >> "$PGDATA/pg_hba.conf"
echo "[init] Usuarios de servicio creados"
