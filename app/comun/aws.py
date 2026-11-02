"""Clientes boto3 hacia cada instancia LocalStack.

Timeouts cortos y sin reintentos: si una copia no responde, se falla rapido
para pasar a la siguiente (failover) en lugar de esperar decenas de segundos.
"""
from functools import lru_cache

import boto3
from botocore.config import Config

from . import config

_CONFIG = Config(
    region_name=config.REGION,
    connect_timeout=2,
    read_timeout=5,
    retries={"max_attempts": 1, "mode": "standard"},   # 1 intento = sin reintentos
    s3={"addressing_style": "path"},                    # localstack-a:4566/bucket
)


@lru_cache
def s3(rol: str):
    """Cliente S3 de la copia indicada: 'A', 'B' o 'BACKUP'."""
    almacen = config.ALMACENES[rol]
    return boto3.client("s3", endpoint_url=almacen.endpoint, config=_CONFIG)


@lru_cache
def kms():
    return boto3.client("kms", endpoint_url=config.KMS_ENDPOINT, config=_CONFIG)


@lru_cache
def secretos():
    return boto3.client("secretsmanager", endpoint_url=config.KMS_ENDPOINT, config=_CONFIG)
