"""Configuracion leida de variables de entorno. Ningun valor sensible vive en el codigo."""
import os
from dataclasses import dataclass


def _env(nombre: str, defecto: str | None = None) -> str:
    valor = os.environ.get(nombre, defecto)
    if valor is None or valor == "":
        raise RuntimeError(f"Falta la variable de entorno {nombre}")
    return valor


@dataclass(frozen=True)
class Almacen:
    """Una ubicacion fisica de los documentos: copia A, copia B o backup."""
    rol: str
    endpoint: str
    bucket: str


REGION = _env("AWS_DEFAULT_REGION", "us-east-1")

ALMACENES = {
    "A":      Almacen("A",      _env("S3_A_ENDPOINT"),      _env("S3_A_BUCKET")),
    "B":      Almacen("B",      _env("S3_B_ENDPOINT"),      _env("S3_B_BUCKET")),
    "BACKUP": Almacen("BACKUP", _env("S3_BACKUP_ENDPOINT"), _env("S3_BACKUP_BUCKET")),
}

KMS_ENDPOINT = _env("KMS_ENDPOINT")
KMS_KEY_ALIAS = _env("KMS_KEY_ALIAS", "alias/pepicloud-docs")

RETENCION_MINUTOS = int(_env("RETENCION_MINUTOS", "30"))
