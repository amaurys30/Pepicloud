"""Prueba: conexion a PostgreSQL con credenciales de Secrets Manager y minimo privilegio.
Uso: docker compose run --rm app-pruebas python -m pruebas.prueba_bd_conexion
"""
import os
import sys

import psycopg

from comun import bd

fallos = 0


def resultado(condicion, mensaje):
    global fallos
    if condicion:
        print(f"OK     {mensaje}")
    else:
        fallos += 1
        print(f"FALLO  {mensaje}")


# 1-3. Cada servicio se conecta con su propio usuario
for servicio in ("registro", "consulta", "worker"):
    try:
        with bd.conectar(servicio) as con:
            usuario = con.execute("SELECT current_user").fetchone()[0]
            docs = con.execute("SELECT count(*) FROM documentos").fetchone()[0]
        resultado(usuario == f"usr_{servicio}",
                  f"Servicio {servicio:<9} conectado como {usuario} (documentos: {docs})")
    except Exception as e:
        resultado(False, f"Servicio {servicio:<9} {type(e).__name__}: {e}")

# 4. Minimo privilegio: consulta no puede escribir
try:
    with bd.conectar("consulta") as con:
        con.execute("INSERT INTO personas (id_persona, nombres, apellidos) VALUES ('99999','X','Y')")
    resultado(False, "usr_consulta pudo insertar")
except psycopg.errors.InsufficientPrivilege:
    resultado(True, "usr_consulta no puede insertar (InsufficientPrivilege)")

# 5. Minimo privilegio: worker no puede leer personas
try:
    with bd.conectar("worker") as con:
        con.execute("SELECT * FROM personas").fetchall()
    resultado(False, "usr_worker pudo leer datos personales")
except psycopg.errors.InsufficientPrivilege:
    resultado(True, "usr_worker no puede leer datos personales de pacientes")

# 6. PostgreSQL verifica la contrasena de verdad
c = bd.credenciales("consulta")
try:
    psycopg.connect(host=c["host"], dbname=c["bd"], user=c["usuario"],
                    password="clave-incorrecta", connect_timeout=3).close()
    resultado(False, "Se acepto una contrasena incorrecta")
except psycopg.OperationalError:
    resultado(True, "Contrasena incorrecta rechazada por PostgreSQL")

# 7. Ninguna contrasena esta en las variables de entorno del contenedor
claves = {bd.credenciales(s)["clave"] for s in ("registro", "consulta", "worker")}
en_entorno = [k for k, v in os.environ.items() if v in claves]
resultado(not en_entorno, f"Ninguna contrasena de BD en variables de entorno {en_entorno or ''}")

print()
print("RESULTADO: conexion a BD correcta" if fallos == 0 else f"RESULTADO: {fallos} fallo(s)")
sys.exit(fallos)
