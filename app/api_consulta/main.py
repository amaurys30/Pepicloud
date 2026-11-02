"""PepiCloud - API de consulta: busqueda y descarga de documentos (solo lectura).

Usa el usuario usr_consulta (solo SELECT + INSERT en auditoria). Descarga con
failover A -> B -> BACKUP, verificando cada copia (descifrado + SHA-256).
"""
import time
import uuid
from datetime import date
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from comun import almacenamiento as alm
from comun import bd, cifrado
from comun.circuito import Circuito

SERVICIO = "consulta"
circuito = Circuito(espera=15)

app = FastAPI(title="PepiCloud - API de consulta", version="1.0")


def conexion():
    con = bd.conectar(SERVICIO)
    con.row_factory = dict_row
    return con


def auditar(accion, id_documento=None, detalle=None):
    with conexion() as con:
        con.execute(
            "INSERT INTO auditoria (servicio, accion, id_documento, detalle) VALUES (%s, %s, %s, %s)",
            ("api-consulta", accion, id_documento, Jsonb(detalle or {})),
        )


@app.get("/salud")
def salud():
    with conexion() as con:
        con.execute("SELECT 1")
    return {"estado": "ok", "servicio": "api-consulta", "copias_marcadas_caidas": circuito.caidas()}


@app.get("/tipos")
def tipos():
    with conexion() as con:
        return con.execute("SELECT codigo, descripcion FROM tipos_documento ORDER BY id_tipo").fetchall()


@app.get("/personas/{cedula}/documentos")
def documentos_de_persona(cedula: str, tipo: str | None = None,
                          desde: date | None = None, hasta: date | None = None,
                          incluir_eliminados: bool = False):
    with conexion() as con:
        persona = con.execute("SELECT id_persona AS cedula, nombres, apellidos FROM personas "
                              "WHERE id_persona = %s", (cedula,)).fetchone()
        if not persona:
            raise HTTPException(404, f"No existe la persona {cedula}")
        documentos = con.execute(
            "SELECT d.id_documento, t.codigo AS tipo, t.descripcion AS tipo_descripcion, d.titulo, "
            "       d.nombre_original, d.content_type, d.tamano_bytes, d.estado, "
            "       d.fecha_registro, d.retencion_hasta, d.llave_objeto, "
            "       (SELECT json_object_agg(c.rol, c.estado) FROM copias_documento c "
            "        WHERE c.id_documento = d.id_documento) AS copias "
            "FROM documentos d JOIN tipos_documento t USING (id_tipo) "
            "WHERE d.id_persona = %(cedula)s "
            "  AND (%(tipo)s::text IS NULL OR t.codigo = %(tipo)s) "
            "  AND (%(desde)s::date IS NULL OR d.fecha_registro >= %(desde)s) "
            "  AND (%(hasta)s::date IS NULL OR d.fecha_registro < %(hasta)s::date + 1) "
            "  AND (%(todos)s OR d.estado = 'ACTIVO') "
            "ORDER BY d.fecha_registro DESC",
            {"cedula": cedula, "tipo": tipo, "desde": desde, "hasta": hasta, "todos": incluir_eliminados},
        ).fetchall()
    return {"persona": persona, "documentos": documentos}


@app.get("/documentos/{id_documento}/descargar")
def descargar(id_documento: uuid.UUID):
    with conexion() as con:
        doc = con.execute(
            "SELECT id_documento::text, llave_objeto, clave_datos_cifrada, nonce, sha256_original, "
            "       nombre_original, content_type, estado FROM documentos WHERE id_documento = %s",
            (id_documento,)).fetchone()
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    if doc["estado"] != "ACTIVO":
        raise HTTPException(410, "El documento fue eliminado")

    def validar(datos: bytes) -> bytes:
        claro = cifrado.descifrar(datos, doc["clave_datos_cifrada"], doc["nonce"], doc["id_documento"])
        if cifrado.sha256(claro) != doc["sha256_original"].strip():
            raise ValueError("IntegridadFallida")
        return claro

    orden = circuito.orden()
    inicio = time.monotonic()
    try:
        lectura = alm.leer_con_failover(doc["llave_objeto"], validar, orden=orden)
    except alm.DocumentoNoDisponible as e:
        circuito.registrar(e.intentos)
        auditar("DESCARGA_FALLIDA", doc["id_documento"], {"intentos": e.intentos})
        raise HTTPException(503, {"mensaje": "Ninguna copia del documento esta disponible",
                                  "intentos": e.intentos})
    circuito.registrar(lectura.intentos)
    total = round(time.monotonic() - inicio, 2)

    detalle = {"servido_desde": lectura.servido_desde, "orden": orden,
               "intentos": lectura.intentos, "segundos": total}
    auditar("DESCARGA", doc["id_documento"], detalle)
    if lectura.servido_desde != "A":
        auditar("FAILOVER", doc["id_documento"], detalle)

    return Response(
        content=lectura.datos,
        media_type=doc["content_type"],
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc['nombre_original'])}",
            "X-Servido-Desde": lectura.servido_desde,
            "X-Tiempo-Segundos": str(total),
            "X-Orden-Intentos": ",".join(orden),
        },
    )
