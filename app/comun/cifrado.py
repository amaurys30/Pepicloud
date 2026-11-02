"""Cifrado de sobre (envelope encryption) con KMS + AES-256-GCM.

- KMS genera una clave de datos por documento y la entrega en claro y cifrada.
- El archivo se cifra con la clave en claro (AES-256-GCM); luego se descarta.
- Se guarda la clave CIFRADA (en PostgreSQL) y el archivo cifrado (en S3).
- El id del documento se liga como contexto: un archivo no puede descifrarse
  con la clave de otro documento.
"""
import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import aws, config


@dataclass(frozen=True)
class DocumentoCifrado:
    contenido: bytes        # archivo cifrado + etiqueta GCM (16 bytes)
    clave_cifrada: str      # clave de datos cifrada por KMS, en base64
    nonce: str              # vector de inicializacion (12 bytes), en base64


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def cifrar(datos: bytes, id_documento: str) -> DocumentoCifrado:
    respuesta = aws.kms().generate_data_key(
        KeyId=config.KMS_KEY_ALIAS,
        KeySpec="AES_256",
        EncryptionContext={"id_documento": id_documento},
    )
    nonce = os.urandom(12)
    contenido = AESGCM(respuesta["Plaintext"]).encrypt(nonce, datos, id_documento.encode())
    # La clave en claro no se guarda en ningun lado; solo sale la version cifrada
    return DocumentoCifrado(contenido, _b64(respuesta["CiphertextBlob"]), _b64(nonce))


def descifrar(contenido: bytes, clave_cifrada: str, nonce: str, id_documento: str) -> bytes:
    respuesta = aws.kms().decrypt(
        CiphertextBlob=base64.b64decode(clave_cifrada),
        EncryptionContext={"id_documento": id_documento},
    )
    # Lanza InvalidTag si el contenido fue alterado o no corresponde al documento
    return AESGCM(respuesta["Plaintext"]).decrypt(
        base64.b64decode(nonce), contenido, id_documento.encode()
    )
