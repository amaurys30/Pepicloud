"""Conexion a PostgreSQL con credenciales obtenidas de Secrets Manager.

Cada servicio usa su propio usuario (registro, consulta, worker) con permisos minimos.
La contrasena nunca esta en el codigo, la imagen ni las variables de entorno.
"""
import json
from functools import lru_cache

import psycopg

from . import aws


@lru_cache
def credenciales(servicio: str) -> dict:
    """servicio: 'registro', 'consulta' o 'worker'."""
    secreto = aws.secretos().get_secret_value(SecretId=f"pepicloud/db/{servicio}")
    return json.loads(secreto["SecretString"])


def conectar(servicio: str) -> psycopg.Connection:
    c = credenciales(servicio)
    return psycopg.connect(
        host=c["host"], port=c["puerto"], dbname=c["bd"],
        user=c["usuario"], password=c["clave"],
        connect_timeout=3,
        application_name=f"pepicloud-{servicio}",
    )
