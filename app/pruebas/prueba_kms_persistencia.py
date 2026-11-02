"""Prueba que un documento cifrado sigue siendo descifrable tras recrear localstack-kms.
Paso 1: python -m pruebas.prueba_kms_persistencia cifrar  > /tmp/doc_cifrado.json
Paso 2: (recrear localstack-kms)
Paso 3: python -m pruebas.prueba_kms_persistencia descifrar < /tmp/doc_cifrado.json
"""
import base64
import json
import sys
import uuid

from comun import cifrado

ORIGINAL = b"Documento que debe sobrevivir al reinicio de KMS"

if sys.argv[1] == "cifrar":
    id_doc = str(uuid.uuid4())
    c = cifrado.cifrar(ORIGINAL, id_doc)
    json.dump({"id": id_doc, "contenido": base64.b64encode(c.contenido).decode(),
               "clave": c.clave_cifrada, "nonce": c.nonce}, sys.stdout)
else:
    d = json.load(sys.stdin)
    try:
        datos = cifrado.descifrar(base64.b64decode(d["contenido"]), d["clave"], d["nonce"], d["id"])
        print("OK     Documento descifrado tras recrear KMS:", datos.decode())
        print("RESULTADO: la clave maestra sobrevive a la recreacion del contenedor")
    except Exception as e:
        print(f"FALLO  No se pudo descifrar: {type(e).__name__}: {e}")
        sys.exit(1)
