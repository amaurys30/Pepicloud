"""Prueba de failover con contenedores apagados de verdad.
  subir: python -m pruebas.prueba_failover subir > /tmp/failover.json
  leer:  python -m pruebas.prueba_failover leer  < /tmp/failover.json
"""
import json
import sys
import time
import uuid

from comun import almacenamiento as alm
from comun import cifrado

if sys.argv[1] == "subir":
    original = b"%PDF-1.4 Documento para la prueba de failover"
    id_doc = str(uuid.uuid4())
    llave = alm.construir_llave("1102345678", "EPICRISIS", id_doc, "epicrisis.pdf")
    c = cifrado.cifrar(original, id_doc)
    copias = alm.subir_copias(llave, c.contenido, alm.calcular_retencion(), id_doc,
                              roles=("A", "B", "BACKUP"))
    if not all(r.ok for r in copias.values()):
        sys.exit(f"No se pudo subir: { {k: v.error for k, v in copias.items()} }")
    json.dump({"id": id_doc, "llave": llave, "clave": c.clave_cifrada, "nonce": c.nonce,
               "sha256": cifrado.sha256(original)}, sys.stdout)
else:
    d = json.load(sys.stdin)

    def validar(datos):
        claro = cifrado.descifrar(datos, d["clave"], d["nonce"], d["id"])
        if cifrado.sha256(claro) != d["sha256"]:
            raise ValueError("SHA-256 no coincide")
        return claro

    inicio = time.monotonic()
    try:
        lectura = alm.leer_con_failover(d["llave"], validar)
        total = time.monotonic() - inicio
        print(f"Servido desde: {lectura.servido_desde}   (tiempo total {total:.2f} s)")
        for rol, estado, seg in lectura.intentos:
            print(f"   {rol:<7} {estado:<28} {seg:.2f} s")
    except alm.DocumentoNoDisponible as e:
        total = time.monotonic() - inicio
        print(f"Documento NO disponible   (tiempo total {total:.2f} s)")
        for rol, estado, seg in e.intentos:
            print(f"   {rol:<7} {estado:<28} {seg:.2f} s")
