"""Circuit breaker: recuerda por unos segundos que una copia esta caida.

Una copia que falla por conexion se manda al final de la fila durante ESPERA
segundos; asi solo la primera lectura paga el tiempo del failover. No se omite:
si las demas fallan, igual se intenta como ultimo recurso.
"""
import threading
import time

ERRORES_DE_CONEXION = {"EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError",
                       "ConnectionClosedError"}


class Circuito:
    def __init__(self, espera: float = 15):
        self.espera = espera
        self._caida_hasta: dict[str, float] = {}
        self._candado = threading.Lock()

    def orden(self, roles=("A", "B", "BACKUP")) -> list[str]:
        ahora = time.monotonic()
        with self._candado:
            sanas = [r for r in roles if self._caida_hasta.get(r, 0) <= ahora]
            caidas = [r for r in roles if self._caida_hasta.get(r, 0) > ahora]
        return sanas + caidas

    def caidas(self) -> list[str]:
        ahora = time.monotonic()
        with self._candado:
            return [r for r, hasta in self._caida_hasta.items() if hasta > ahora]

    def registrar(self, intentos):
        """intentos: [(rol, estado, segundos), ...] de leer_con_failover."""
        with self._candado:
            for rol, estado, _ in intentos:
                if estado in ERRORES_DE_CONEXION:
                    self._caida_hasta[rol] = time.monotonic() + self.espera
                elif estado == "OK":
                    self._caida_hasta.pop(rol, None)
