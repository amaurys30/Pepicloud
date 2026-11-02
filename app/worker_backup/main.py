"""PepiCloud - worker de backup y reparacion.

Cada ciclo:
  1. BACKUP:       copia a localstack-backup y a la boveda en disco los documentos pendientes.
  2. VERIFICACION: confirma que cada copia exista realmente en su instancia.
  3. REPARACION:   reconstruye copias fallidas o perdidas desde una copia sana o la boveda.
  4. LIMPIEZA:     borra las copias de documentos ya eliminados.
Nunca descifra: copia bytes cifrados y verifica su integridad con el MD5 (ETag).
"""
import hashlib
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from botocore.exceptions import ClientError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from comun import almacenamiento as alm
from comun import aws, bd, config
from comun.circuito import ERRORES_DE_CONEXION

INTERVALO = int(os.environ.get("WORKER_INTERVALO", "15"))
BOVEDA = Path(os.environ.get("BOVEDA_DIR", "/boveda"))
ROLES = ("A", "B", "BACKUP")


def log(mensaje):
    print(f"{datetime.now(alm.HORA_COLOMBIA):%H:%M:%S} {mensaje}", flush=True)


def md5(datos: bytes) -> str:
    return hashlib.md5(datos).hexdigest()


def conexion():
    con = bd.conectar("worker")
    con.row_factory = dict_row
    return con


def auditar(accion, id_documento, detalle):
    with conexion() as con:
        con.execute("INSERT INTO auditoria (servicio, accion, id_documento, detalle) "
                    "VALUES ('worker-backup', %s, %s, %s)", (accion, id_documento, Jsonb(detalle)))


def actualizar_copia(id_doc, rol, estado, version_id=None, etag=None):
    with conexion() as con:
        con.execute(
            "UPDATE copias_documento SET estado = %s, ultima_verificacion = now(), "
            "  version_id = COALESCE(%s, version_id), etag = COALESCE(%s, etag) "
            "WHERE id_documento = %s AND rol = %s", (estado, version_id, etag, id_doc, rol))


# ------------------------------------------------------------------ boveda en disco
def ruta_boveda(llave: str) -> Path:
    ruta = (BOVEDA / llave).resolve()
    if BOVEDA.resolve() not in ruta.parents:
        raise ValueError(f"Llave fuera de la boveda: {llave}")
    return ruta


def guardar_en_boveda(llave: str, datos: bytes):
    ruta = ruta_boveda(llave)
    if ruta.exists():
        return
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_bytes(datos)
    os.chmod(temporal, 0o444)                  # solo lectura
    temporal.rename(ruta)                      # escritura atomica


# ------------------------------------------------------------------ S3
def estado_en_s3(rol, llave, version_id) -> str:
    """PRESENTE, AUSENTE (la instancia respondio que no esta) o INALCANZABLE."""
    extra = {"VersionId": version_id} if version_id else {}
    try:
        aws.s3(rol).head_object(Bucket=config.ALMACENES[rol].bucket, Key=llave, **extra)
        return "PRESENTE"
    except ClientError as e:
        codigo = alm.describir(e)
        return "AUSENTE" if codigo in ("404", "400", "NoSuchKey", "NoSuchVersion", "NotFound") else codigo
    except Exception as e:
        return "INALCANZABLE" if alm.describir(e) in ERRORES_DE_CONEXION else alm.describir(e)


def obtener_contenido(doc, excluir, etag_esperado):
    """Busca una copia sana (MD5 = ETag original) en otra instancia o en la boveda."""
    for c in doc["copias"]:
        if c["rol"] == excluir or c["estado"] != "OK":
            continue
        try:
            datos = alm.leer(c["rol"], doc["llave"], c["version_id"])
            if etag_esperado is None or md5(datos) == etag_esperado:
                return datos, c["rol"]
        except Exception:
            continue
    try:
        datos = ruta_boveda(doc["llave"]).read_bytes()
        if etag_esperado is None or md5(datos) == etag_esperado:
            return datos, "BOVEDA"
    except (FileNotFoundError, ValueError):
        pass
    return None, None


def escribir_copia(rol, doc, datos):
    """Escribe la copia con la retencion restante del documento (si aun no vencio)."""
    extra = {}
    if doc["retencion_hasta"] > datetime.now(timezone.utc) + timedelta(seconds=5):
        extra = {"ObjectLockMode": "COMPLIANCE", "ObjectLockRetainUntilDate": doc["retencion_hasta"]}
    r = aws.s3(rol).put_object(Bucket=config.ALMACENES[rol].bucket, Key=doc["llave"], Body=datos,
                               ContentType="application/octet-stream", IfNoneMatch="*",
                               Metadata={"id-documento": doc["id"]}, **extra)
    return r.get("VersionId"), r.get("ETag", "").strip('"'), bool(extra)


# ------------------------------------------------------------------ tareas
def atender_documento(doc):
    etag_esperado = next((c["etag"] for c in doc["copias"] if c["etag"]), None)

    for c in doc["copias"]:
        rol = c["rol"]
        if c["estado"] in ("PENDIENTE", "FALLIDA", "PERDIDA"):
            motivo = c["estado"]
        else:
            estado = estado_en_s3(rol, doc["llave"], c["version_id"])
            if estado == "PRESENTE":
                actualizar_copia(doc["id"], rol, "OK")
                if rol == "BACKUP" and not ruta_boveda(doc["llave"]).exists():
                    datos, _ = obtener_contenido(doc, None, etag_esperado)
                    if datos:
                        guardar_en_boveda(doc["llave"], datos)
                        log(f"BOVEDA     {doc['id'][:8]} guardado en disco")
                continue
            if estado != "AUSENTE":
                log(f"OMITIDA    {doc['id'][:8]} copia {rol}: instancia {estado} (no se marca perdida)")
                continue
            motivo = "PERDIDA"
            actualizar_copia(doc["id"], rol, "PERDIDA")
            log(f"PERDIDA    {doc['id'][:8]} copia {rol} ya no existe en su instancia")

        datos, fuente = obtener_contenido(doc, rol, etag_esperado)
        if datos is None:
            log(f"SIN FUENTE {doc['id'][:8]} copia {rol}: ninguna copia sana disponible")
            continue
        try:
            version, etag, con_lock = escribir_copia(rol, doc, datos)
        except Exception as e:
            log(f"ERROR      {doc['id'][:8]} copia {rol}: {alm.describir(e)}")
            continue
        if rol == "BACKUP":
            guardar_en_boveda(doc["llave"], datos)
        actualizar_copia(doc["id"], rol, "OK", version, etag)
        accion = "BACKUP" if motivo == "PENDIENTE" else "REPARACION"
        auditar(accion, doc["id"], {"copia": rol, "motivo": motivo, "fuente": fuente,
                                    "object_lock": con_lock, "version_id": version})
        log(f"{accion:<10} {doc['id'][:8]} copia {rol} <- {fuente} (motivo {motivo}, lock={con_lock})")
        c["estado"], c["version_id"], c["etag"] = "OK", version, etag


def limpiar_documento(doc):
    for c in doc["copias"]:
        if c["estado"] == "ELIMINADA":
            continue
        if c["version_id"]:
            try:
                aws.s3(c["rol"]).delete_object(Bucket=config.ALMACENES[c["rol"]].bucket,
                                               Key=doc["llave"], VersionId=c["version_id"])
            except ClientError as e:
                if alm.describir(e) not in ("NoSuchKey", "NoSuchVersion", "404"):
                    log(f"ERROR      limpieza {doc['id'][:8]} copia {c['rol']}: {alm.describir(e)}")
                    continue
            except Exception as e:
                log(f"OMITIDA    limpieza {doc['id'][:8]} copia {c['rol']}: {alm.describir(e)}")
                continue
        actualizar_copia(doc["id"], c["rol"], "ELIMINADA")
        log(f"LIMPIEZA   {doc['id'][:8]} copia {c['rol']} eliminada")
    try:
        ruta_boveda(doc["llave"]).unlink(missing_ok=True)
    except ValueError:
        pass


def ciclo():
    with conexion() as con:
        filas = con.execute(
            "SELECT d.id_documento::text AS id, d.llave_objeto AS llave, d.retencion_hasta, "
            "       d.estado AS estado_doc, c.rol, c.version_id, c.etag, c.estado "
            "FROM documentos d JOIN copias_documento c USING (id_documento) "
            "WHERE d.estado = 'ACTIVO' OR c.estado <> 'ELIMINADA' "
            "ORDER BY d.fecha_registro, c.rol").fetchall()
    documentos = {}
    for f in filas:
        doc = documentos.setdefault(f["id"], {"id": f["id"], "llave": f["llave"],
                                              "retencion_hasta": f["retencion_hasta"],
                                              "estado": f["estado_doc"], "copias": []})
        doc["copias"].append({"rol": f["rol"], "version_id": f["version_id"],
                              "etag": f["etag"], "estado": f["estado"]})
    for doc in documentos.values():
        try:
            if doc["estado"] == "ELIMINADO":
                limpiar_documento(doc)
            else:
                atender_documento(doc)
        except Exception:
            log(f"ERROR      {doc['id'][:8]}:\n{traceback.format_exc()}")
    return len(documentos)


if __name__ == "__main__":
    log(f"worker-backup iniciado (cada {INTERVALO} s, boveda en {BOVEDA})")
    while True:
        try:
            ciclo()
        except Exception:
            log(f"ERROR en el ciclo:\n{traceback.format_exc()}")
        time.sleep(INTERVALO)
