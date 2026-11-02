"""Prueba del cifrado de sobre.
Uso: docker compose run --rm app-pruebas python -m pruebas.prueba_cifrado
"""
import sys
import uuid

from cryptography.exceptions import InvalidTag

from comun import cifrado

fallos = 0


def resultado(condicion, mensaje):
    global fallos
    if condicion:
        print(f"OK     {mensaje}")
    else:
        fallos += 1
        print(f"FALLO  {mensaje}")


original = b"Historia clinica de prueba - paciente 1102345678 - diagnostico confidencial"
id_doc = str(uuid.uuid4())

c = cifrado.cifrar(original, id_doc)
print(f"Original   ({len(original)} bytes): {original[:40]!r}...")
print(f"Cifrado    ({len(c.contenido)} bytes): {c.contenido[:40]!r}...")
print(f"Clave cifrada por KMS: {c.clave_cifrada[:40]}...  ({len(c.clave_cifrada)} caracteres)")
print()

resultado(original not in c.contenido and b"confidencial" not in c.contenido,
          "1. El contenido cifrado no contiene el texto original")
resultado(len(c.contenido) == len(original) + 16,
          "2. Tamano cifrado = original + 16 bytes de etiqueta GCM")

recuperado = cifrado.descifrar(c.contenido, c.clave_cifrada, c.nonce, id_doc)
resultado(recuperado == original and cifrado.sha256(recuperado) == cifrado.sha256(original),
          "3. Descifrar devuelve exactamente el original (mismo SHA-256)")

c2 = cifrado.cifrar(original, id_doc)
resultado(c2.contenido != c.contenido and c2.clave_cifrada != c.clave_cifrada,
          "4. El mismo archivo cifrado dos veces produce resultados distintos")

alterado = bytearray(c.contenido)
alterado[10] ^= 0x01                                      # cambiar un solo bit
try:
    cifrado.descifrar(bytes(alterado), c.clave_cifrada, c.nonce, id_doc)
    resultado(False, "5. Un archivo alterado fue aceptado")
except InvalidTag:
    resultado(True, "5. Alterar 1 bit del archivo cifrado hace fallar el descifrado")

try:
    cifrado.descifrar(c.contenido, c.clave_cifrada, c.nonce, str(uuid.uuid4()))
    resultado(False, "6. Se descifro usando el id de otro documento")
except Exception as e:
    resultado(True, f"6. Con el id de otro documento no descifra ({type(e).__name__})")

print()
print("RESULTADO: cifrado de sobre correcto" if fallos == 0 else f"RESULTADO: {fallos} fallo(s)")
sys.exit(fallos)
