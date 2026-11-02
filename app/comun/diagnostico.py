"""Verifica que el contenedor alcanza las 4 instancias LocalStack.
Uso: docker compose run --rm app-pruebas
"""
import sys

from . import aws, config

fallos = 0


def ok(msg):
    print(f"OK     {msg}")


def fallo(msg):
    global fallos
    fallos += 1
    print(f"FALLO  {msg}")


for rol, almacen in config.ALMACENES.items():
    try:
        cliente = aws.s3(rol)
        cliente.head_bucket(Bucket=almacen.bucket)
        lock = cliente.get_object_lock_configuration(Bucket=almacen.bucket)
        estado = lock["ObjectLockConfiguration"]["ObjectLockEnabled"]
        ok(f"Copia {rol:<6} {almacen.endpoint} -> {almacen.bucket} (Object Lock {estado})")
    except Exception as e:
        fallo(f"Copia {rol:<6} {almacen.endpoint} -> {type(e).__name__}: {e}")

try:
    clave = aws.kms().describe_key(KeyId=config.KMS_KEY_ALIAS)["KeyMetadata"]
    ok(f"KMS    {config.KMS_KEY_ALIAS} -> {clave['KeyState']}")
except Exception as e:
    fallo(f"KMS    {type(e).__name__}: {e}")

try:
    nombres = [s["Name"] for s in aws.secretos().list_secrets()["SecretList"]]
    ok(f"Secrets Manager -> {', '.join(sorted(nombres))}")
except Exception as e:
    fallo(f"Secrets Manager {type(e).__name__}: {e}")

print()
print("RESULTADO: conectividad correcta" if fallos == 0 else f"RESULTADO: {fallos} fallo(s)")
sys.exit(fallos)
