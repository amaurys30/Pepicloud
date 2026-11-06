"""PepiCloud - API de registro: personas, carga y eliminacion de documentos.

Usa el usuario de BD usr_registro (sin permiso DELETE) y el token de administrador
para eliminar. Nunca escribe archivos en PostgreSQL: solo metadatos y referencias.
"""
import hmac
import os
import uuid
from datetime import date, datetime, timezone

import psycopg
from botocore.exceptions import ClientError
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from comun import almacenamiento as alm
from comun import aws, bd, cifrado, config

SERVICIO = "registro"
TAMANO_MAXIMO = 20 * 1024 * 1024
EXTENSIONES = {"pdf": "application/pdf", "jpg": "image/jpeg",
               "jpeg": "image/jpeg", "png": "image/png"}

app = FastAPI(title="PepiCloud - API de registro", version="1.0")


def conexion():
    con = bd.conectar(SERVICIO)
    con.row_factory = dict_row
    return con


def auditar(con, accion, id_documento=None, detalle=None):
    con.execute(
        "INSERT INTO auditoria (servicio, accion, id_documento, detalle) VALUES (%s, %s, %s, %s)",
        ("api-registro", accion, id_documento, Jsonb(detalle or {})),
    )


def token_admin() -> str:
    with open("/run/secrets/api_admin_token") as f:
        return f.read().strip()


class PersonaNueva(BaseModel):
    cedula: str = Field(pattern=r"^[0-9]{5,10}$", examples=["1102345678"])
    nombres: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)
    fecha_nacimiento: date | None = None


@app.get("/salud")
def salud():
    with conexion() as con:
        con.execute("SELECT 1")
    return {"estado": "ok", "servicio": "api-registro", "retencion_minutos": config.RETENCION_MINUTOS}


@app.get("/tipos")
def tipos():
    with conexion() as con:
        return con.execute("SELECT codigo, descripcion FROM tipos_documento ORDER BY id_tipo").fetchall()


@app.post("/personas", status_code=201)
def crear_persona(p: PersonaNueva):
    try:
        with conexion() as con:
            con.execute(
                "INSERT INTO personas (id_persona, nombres, apellidos, fecha_nacimiento) "
                "VALUES (%s, %s, %s, %s)",
                (p.cedula, p.nombres.strip(), p.apellidos.strip(), p.fecha_nacimiento),
            )
            auditar(con, "PERSONA_CREADA", detalle={"cedula": p.cedula})
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, f"Ya existe una persona con cedula {p.cedula}")
    return {"cedula": p.cedula, "mensaje": "Persona registrada"}


@app.get("/personas/{cedula}")
def obtener_persona(cedula: str):
    with conexion() as con:
        persona = con.execute(
            "SELECT p.id_persona AS cedula, p.nombres, p.apellidos, p.fecha_nacimiento, "
            "       count(d.id_documento) AS documentos "
            "FROM personas p LEFT JOIN documentos d ON d.id_persona = p.id_persona "
            "WHERE p.id_persona = %s GROUP BY p.id_persona", (cedula,)
        ).fetchone()
    if not persona:
        raise HTTPException(404, f"No existe la persona {cedula}")
    return persona


@app.post("/documentos", status_code=201)
def cargar_documento(cedula: str = Form(...), codigo_tipo: str = Form(...),
                     titulo: str = Form(..., min_length=1, max_length=200),
                     archivo: UploadFile = File(...)):
    # 1. Validaciones
    ext = os.path.splitext(archivo.filename or "")[1].lower().lstrip(".")
    if ext not in EXTENSIONES:
        raise HTTPException(415, f"Tipo de archivo no permitido: .{ext} (use PDF, JPG o PNG)")
    datos = archivo.file.read(TAMANO_MAXIMO + 1)
    if not datos:
        raise HTTPException(422, "El archivo esta vacio")
    if len(datos) > TAMANO_MAXIMO:
        raise HTTPException(413, "El archivo supera 20 MB")

    with conexion() as con:
        if not con.execute("SELECT 1 FROM personas WHERE id_persona = %s", (cedula,)).fetchone():
            raise HTTPException(404, f"No existe la persona {cedula}")
        tipo = con.execute("SELECT id_tipo FROM tipos_documento WHERE codigo = %s",
                           (codigo_tipo,)).fetchone()
        if not tipo:
            raise HTTPException(422, f"Tipo de documento desconocido: {codigo_tipo}")

    # 2-4. Cifrar y subir a A y B en paralelo, con retencion COMPLIANCE
    id_doc = str(uuid.uuid4())
    ahora = datetime.now(timezone.utc)
    hasta = alm.calcular_retencion(ahora)
    llave = alm.construir_llave(cedula, codigo_tipo, id_doc, archivo.filename, ahora)
    doc = cifrado.cifrar(datos, id_doc)
    copias = alm.subir_copias(llave, doc.contenido, hasta, id_doc)

    # 5. Sin ninguna copia operativa no se registra nada
    if not any(r.ok for r in copias.values()):
        raise HTTPException(503, {"mensaje": "Ninguna copia operativa disponible",
                                  "copias": {rol: r.error for rol, r in copias.items()}})

    # 6. Metadatos, copias y auditoria en una sola transaccion
    with conexion() as con:
        con.execute(
            "INSERT INTO documentos (id_documento, id_persona, id_tipo, titulo, nombre_original, "
            " content_type, tamano_bytes, sha256_original, llave_objeto, clave_datos_cifrada, nonce, "
            " fecha_registro, retencion_hasta) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (id_doc, cedula, tipo["id_tipo"], titulo.strip(), archivo.filename, EXTENSIONES[ext],
             len(datos), cifrado.sha256(datos), llave, doc.clave_cifrada, doc.nonce, ahora, hasta),
        )
        for rol in ("A", "B", "BACKUP"):
            almacen = config.ALMACENES[rol]
            r = copias.get(rol)
            estado = "PENDIENTE" if r is None else ("OK" if r.ok else "FALLIDA")
            con.execute(
                "INSERT INTO copias_documento (id_documento, rol, endpoint, bucket, llave_objeto, "
                " version_id, etag, estado, ultima_verificacion) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (id_doc, rol, almacen.endpoint, almacen.bucket, llave,
                 r.version_id if r else None, r.etag if r else None, estado, ahora if r else None),
            )
        auditar(con, "CARGA", id_doc, {
            "cedula": cedula, "tipo": codigo_tipo, "tamano": len(datos),
            "copias": {rol: (r.version_id if r.ok else f"FALLIDA: {r.error}") for rol, r in copias.items()},
        })

    return {
        "id_documento": id_doc,
        "llave_objeto": llave,
        "retencion_hasta": hasta.isoformat(),
        "copias": {rol: {"ok": r.ok, "version_id": r.version_id, "error": r.error}
                   for rol, r in copias.items()},
    }


@app.get("/documentos/recientes")
def documentos_recientes(limite: int = 20):
    with conexion() as con:
        return con.execute(
            "SELECT d.id_documento, d.id_persona AS cedula, p.nombres || ' ' || p.apellidos AS persona, "
            "       t.codigo AS tipo, d.titulo, d.nombre_original, d.tamano_bytes, d.estado, "
            "       d.fecha_registro, d.retencion_hasta, "
            "       (SELECT json_object_agg(c.rol, c.estado) FROM copias_documento c "
            "        WHERE c.id_documento = d.id_documento) AS copias "
            "FROM documentos d JOIN personas p USING (id_persona) "
            "JOIN tipos_documento t USING (id_tipo) "
            "ORDER BY d.fecha_registro DESC LIMIT %s", (min(max(limite, 1), 100),)
        ).fetchall()


@app.delete("/documentos/{id_documento}")
def eliminar_documento(id_documento: uuid.UUID, authorization: str | None = Header(None)):
    # Permisos: solo con el token de administrador
    if not hmac.compare_digest(authorization or "", f"Bearer {token_admin()}"):
        raise HTTPException(403, "Se requiere el token de administrador")

    with conexion() as con:
        doc = con.execute("SELECT estado, retencion_hasta FROM documentos WHERE id_documento = %s",
                          (id_documento,)).fetchone()
        if not doc:
            raise HTTPException(404, "Documento no encontrado")
        if doc["estado"] == "ELIMINADO":
            raise HTTPException(409, "El documento ya fue eliminado")
        copias = con.execute("SELECT rol, bucket, llave_objeto, version_id FROM copias_documento "
                             "WHERE id_documento = %s AND version_id IS NOT NULL",
                             (id_documento,)).fetchall()

    # No se pre-verifica la fecha: es S3 (Object Lock) quien debe impedir el borrado
    resultados = {}
    for c in copias:
        try:
            aws.s3(c["rol"]).delete_object(Bucket=c["bucket"], Key=c["llave_objeto"],
                                           VersionId=c["version_id"])
            resultados[c["rol"]] = "ELIMINADA"
        except ClientError as e:
            codigo = alm.describir(e)
            if alm.es_bloqueo(e):
                resultados[c["rol"]] = "PROTEGIDA_OBJECT_LOCK"
            else:
                resultados[c["rol"]] = {"NoSuchKey": "NO_EXISTIA",
                                        "NoSuchVersion": "NO_EXISTIA"}.get(codigo, codigo)
        except Exception as e:
            resultados[c["rol"]] = alm.describir(e)

    if "PROTEGIDA_OBJECT_LOCK" in resultados.values():
        with conexion() as con:
            auditar(con, "ELIMINACION_RECHAZADA", str(id_documento), resultados)
        raise HTTPException(423, {"mensaje": "Documento protegido: la retencion no ha vencido",
                                  "retencion_hasta": doc["retencion_hasta"].isoformat(),
                                  "copias": resultados})

    try:
        with conexion() as con:
            con.execute("UPDATE documentos SET estado = 'ELIMINADO', eliminado_en = now() "
                        "WHERE id_documento = %s", (id_documento,))
            borradas = [rol for rol, r in resultados.items() if r in ("ELIMINADA", "NO_EXISTIA")]
            if borradas:
                con.execute("UPDATE copias_documento SET estado = 'ELIMINADA', ultima_verificacion = now() "
                            "WHERE id_documento = %s AND rol = ANY(%s)", (id_documento, borradas))
            auditar(con, "ELIMINACION", str(id_documento), resultados)
    except psycopg.errors.InsufficientPrivilege as e:
        # Segunda barrera: el trigger de PostgreSQL
        raise HTTPException(423, {"mensaje": "La base de datos rechazo la eliminacion",
                                  "detalle": str(e).splitlines()[0]})
    # Copias inalcanzables quedan para que el worker las limpie
    return {"id_documento": str(id_documento), "estado": "ELIMINADO", "copias": resultados}
