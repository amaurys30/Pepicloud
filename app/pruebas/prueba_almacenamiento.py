"""Prueba del almacenamiento activo-activo con Object Lock.
Uso: docker compose run --rm -e RETENCION_MINUTOS=2 app-pruebas python -m pruebas.prueba_almacenamiento
"""
import re
import sys
import uuid

from comun import almacenamiento as alm
from comun import aws, cifrado, config

fallos = 0


def resultado(condicion, mensaje):
    global fallos
    if condicion:
        print(f"OK     {mensaje}")
    else:
        fallos += 1
        print(f"FALLO  {mensaje}")


original = b"%PDF-1.4 Historia clinica de prueba - diagnostico confidencial"
id_doc = str(uuid.uuid4())

# 1. Llave del objeto
llave = alm.construir_llave("1102345678", "HISTORIA_CLINICA", id_doc, "examen.PDF")
print(f"Llave: {llave}\n")
resultado(re.fullmatch(rf"1102345678/HISTORIA_CLINICA/\d{{4}}/\d{{2}}/{id_doc}\.pdf\.enc", llave),
          "1. Llave con formato cedula/TIPO/AAAA/MM/uuid.ext.enc")
try:
    alm.construir_llave("../../etc", "HISTORIA_CLINICA", id_doc, "x.pdf")
    resultado(False, "1b. Se acepto una cedula con ruta maliciosa")
except ValueError:
    resultado(True, "1b. Cedula con ruta maliciosa rechazada")

# 2. Cifrar y subir a A y B en paralelo
c = cifrado.cifrar(original, id_doc)
hasta = alm.calcular_retencion()
copias = alm.subir_copias(llave, c.contenido, hasta, id_doc)
for rol, r in copias.items():
    print(f"   Copia {rol}: ok={r.ok} version={r.version_id} error={r.error}")
resultado(all(r.ok and r.version_id for r in copias.values()),
          f"2. Subido a A y B en paralelo, retencion {config.RETENCION_MINUTOS} min")

# 3. Cada copia existe en su propia instancia; el backup aun no (lo hara el worker)
existe = {}
for rol in ("A", "B", "BACKUP"):
    try:
        aws.s3(rol).head_object(Bucket=config.ALMACENES[rol].bucket, Key=llave)
        existe[rol] = True
    except Exception:
        existe[rol] = False
resultado(existe["A"] and existe["B"] and not existe["BACKUP"],
          f"3. Existe en A y B, no en BACKUP todavia {existe}")

# 4. Cifrado en reposo: lo guardado en el bucket es ilegible e identico en A y B
crudo_a = alm.leer("A", llave)
crudo_b = alm.leer("B", llave)
resultado(b"confidencial" not in crudo_a and crudo_a == crudo_b,
          "4. El objeto guardado esta cifrado y es identico en A y B")

# 5. Retencion COMPLIANCE en ambas copias
modos = {rol: aws.s3(rol).get_object_retention(Bucket=config.ALMACENES[rol].bucket, Key=llave,
                                               VersionId=copias[rol].version_id)["Retention"]["Mode"]
         for rol in ("A", "B")}
resultado(modos == {"A": "COMPLIANCE", "B": "COMPLIANCE"}, f"5. Retencion en ambas copias: {modos}")

# 6. Intento de modificar (subir otro contenido con la misma llave)
otro = cifrado.cifrar(b"contenido alterado", id_doc)
intento = alm.subir_copias(llave, otro.contenido, hasta, id_doc)
resultado(not any(r.ok for r in intento.values()),
          f"6. Sobrescribir rechazado: { {rol: r.error for rol, r in intento.items()} }")

# 7. Intento de borrar la version protegida
try:
    aws.s3("A").delete_object(Bucket=config.ALMACENES["A"].bucket, Key=llave,
                              VersionId=copias["A"].version_id)
    resultado(False, "7. Se borro la version protegida en A")
except Exception as e:
    resultado(True, f"7. Borrar la version protegida rechazado ({alm.describir(e)})")


# 8. Lectura normal con validacion: descifrar + comparar SHA-256
def validar_para(doc_id, cif, sha_esperado):
    def validar(datos):
        claro = cifrado.descifrar(datos, cif.clave_cifrada, cif.nonce, doc_id)
        if cifrado.sha256(claro) != sha_esperado:
            raise ValueError("SHA-256 no coincide")
        return claro
    return validar


lectura = alm.leer_con_failover(llave, validar_para(id_doc, c, cifrado.sha256(original)))
resultado(lectura.servido_desde == "A" and lectura.datos == original,
          f"8. Lectura normal servida desde {lectura.servido_desde}, contenido intacto")

# 9. Failover: documento que solo existe en B
id_doc2 = str(uuid.uuid4())
llave2 = alm.construir_llave("1102345678", "LABORATORIO", id_doc2, "lab.pdf")
c2 = cifrado.cifrar(original, id_doc2)
alm.subir_copias(llave2, c2.contenido, hasta, id_doc2, roles=("B",))
lectura2 = alm.leer_con_failover(llave2, validar_para(id_doc2, c2, cifrado.sha256(original)))
print(f"   Intentos: {lectura2.intentos}")
resultado(lectura2.servido_desde == "B" and lectura2.datos == original,
          "9. Sin la copia A, el documento se recupero desde B sin volver a cargarlo")

print()
print("RESULTADO: almacenamiento correcto" if fallos == 0 else f"RESULTADO: {fallos} fallo(s)")
sys.exit(fallos)
