"""Almacenamiento de documentos cifrados en las copias A, B y BACKUP.

- Escritura activo-activo: A y B en paralelo, con Object Lock COMPLIANCE.
- Escritura condicional (IfNoneMatch='*'): un objeto existente no se sobrescribe.
- Lectura con failover A -> B -> BACKUP, validando cada copia.
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from botocore.exceptions import BotoCoreError, ClientError

from . import aws, config

HORA_COLOMBIA = timezone(timedelta(hours=-5))    # Colombia no tiene horario de verano
ERRORES_S3 = (ClientError, BotoCoreError)


@dataclass
class ResultadoCopia:
    rol: str
    ok: bool
    version_id: str | None = None
    etag: str | None = None
    error: str | None = None


class DocumentoNoDisponible(Exception):
    def __init__(self, llave, intentos):
        super().__init__(f"Ninguna copia disponible para {llave}: {intentos}")
        self.intentos = intentos


@dataclass
class Lectura:
    datos: bytes                   # contenido ya validado (descifrado, si hay validador)
    servido_desde: str             # 'A', 'B' o 'BACKUP'
    intentos: list = field(default_factory=list)


def describir(error: Exception) -> str:
    if isinstance(error, ClientError):
        return error.response.get("Error", {}).get("Code", "ClientError")
    return type(error).__name__


def construir_llave(cedula: str, codigo_tipo: str, id_documento: str,
                    nombre_original: str, fecha: datetime | None = None) -> str:
    """cedula/TIPO/AAAA/MM/uuid.ext.enc"""
    if not re.fullmatch(r"[0-9]{5,10}", cedula):
        raise ValueError(f"Cedula invalida: {cedula!r}")
    if not re.fullmatch(r"[A-Z0-9_]+", codigo_tipo):
        raise ValueError(f"Tipo de documento invalido: {codigo_tipo!r}")
    fecha = (fecha or datetime.now(timezone.utc)).astimezone(HORA_COLOMBIA)
    ext = os.path.splitext(nombre_original)[1].lower().lstrip(".")
    if not re.fullmatch(r"[a-z0-9]{1,10}", ext):
        ext = "bin"
    return f"{cedula}/{codigo_tipo}/{fecha:%Y}/{fecha:%m}/{id_documento}.{ext}.enc"


def calcular_retencion(desde: datetime | None = None) -> datetime:
    desde = desde or datetime.now(timezone.utc)
    return desde + timedelta(minutes=config.RETENCION_MINUTOS)


def _subir_una(rol, llave, contenido, retencion_hasta, id_documento) -> ResultadoCopia:
    almacen = config.ALMACENES[rol]
    try:
        r = aws.s3(rol).put_object(
            Bucket=almacen.bucket,
            Key=llave,
            Body=contenido,
            ContentType="application/octet-stream",
            IfNoneMatch="*",                          # no sobrescribir nunca
            ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=retencion_hasta,
            Metadata={"id-documento": id_documento},
        )
        return ResultadoCopia(rol, True, r.get("VersionId"), r.get("ETag", "").strip('"'))
    except ERRORES_S3 as e:
        return ResultadoCopia(rol, False, error=describir(e))


def subir_copias(llave: str, contenido: bytes, retencion_hasta: datetime,
                 id_documento: str, roles=("A", "B")) -> dict[str, ResultadoCopia]:
    """Escribe el mismo objeto en varias copias en paralelo."""
    for rol in roles:
        aws.s3(rol)   # crear los clientes antes de usar hilos (la creacion no es thread-safe)
    with ThreadPoolExecutor(max_workers=len(roles)) as hilos:
        futuros = {rol: hilos.submit(_subir_una, rol, llave, contenido, retencion_hasta, id_documento)
                   for rol in roles}
    return {rol: f.result() for rol, f in futuros.items()}


def leer(rol: str, llave: str, version_id: str | None = None) -> bytes:
    almacen = config.ALMACENES[rol]
    extra = {"VersionId": version_id} if version_id else {}
    return aws.s3(rol).get_object(Bucket=almacen.bucket, Key=llave, **extra)["Body"].read()


def leer_con_failover(llave: str, validar=None, orden=("A", "B", "BACKUP")) -> Lectura:
    """Lee de la primera copia disponible y valida. validar(datos) debe devolver
    el contenido final o lanzar una excepcion si la copia no sirve."""
    intentos = []
    for rol in orden:
        inicio = time.monotonic()
        try:
            datos = leer(rol, llave)
            if validar:
                datos = validar(datos)
            intentos.append((rol, "OK", round(time.monotonic() - inicio, 2)))
            return Lectura(datos, rol, intentos)
        except Exception as e:
            intentos.append((rol, describir(e), round(time.monotonic() - inicio, 2)))
    raise DocumentoNoDisponible(llave, intentos)
