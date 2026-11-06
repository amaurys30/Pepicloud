"""Crea, si no existen, los buckets de las copias A, B y BACKUP con Object Lock.
Uso: python -m comun.buckets   (lo ejecuta el servicio s3-init)
"""
from botocore.exceptions import ClientError

from . import aws, config


def asegurar_bucket(rol: str) -> bool:
    """Devuelve True si tuvo que crear el bucket."""
    almacen = config.ALMACENES[rol]
    cliente = aws.s3(rol)
    try:
        cliente.head_bucket(Bucket=almacen.bucket)
        return False
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket", "NotFound"):
            raise
    # Object Lock solo se puede activar al crear el bucket (activa tambien el versionado)
    cliente.create_bucket(Bucket=almacen.bucket, ObjectLockEnabledForBucket=True)
    return True


if __name__ == "__main__":
    for rol, almacen in config.ALMACENES.items():
        creado = asegurar_bucket(rol)
        lock = aws.s3(rol).get_object_lock_configuration(
            Bucket=almacen.bucket)["ObjectLockConfiguration"]["ObjectLockEnabled"]
        print(f"[init] {rol:<6} {almacen.endpoint} -> {almacen.bucket}: "
              f"{'creado' if creado else 'ya existia'} (Object Lock {lock})", flush=True)
