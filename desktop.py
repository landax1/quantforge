"""BotiQuant Desktop: la aplicación en una ventana propia.

Por dentro es el mismo servidor de siempre, atado a la interfaz de red local y
mostrado en una ventana nativa en vez de en una pestaña del navegador. No hay
una segunda versión de la aplicación que mantener: es la misma, con otra
carcasa.

La ventana usa WebView2, el motor que ya viene con Windows 10 y 11. Por eso
suma dos megabytes y no ciento cincuenta: no empaquetamos un navegador,
usamos el que la máquina ya tiene.

Modo escritorio significa que la máquina es del usuario: puede importar sus
propios archivos, descargar instrumentos y borrar lo que quiera. Nada de eso
necesita cuenta. Lo que se comprueba es la licencia, y se comprueba sin red.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

#: Modo escritorio: un solo dueño, todos los permisos sobre su propia máquina.
#: Se fija ANTES de importar la aplicación porque se lee al importar el módulo.
os.environ.setdefault("BQ_MULTIUSER", "0")
#: Sin credenciales de Google no hay pantalla de login: en el escritorio la
#: identidad la da la licencia, no una sesión.
for _var in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
    os.environ.pop(_var, None)


def puerto_libre() -> int:
    """Un puerto que el sistema garantiza libre AHORA.

    Fijar un número trae el problema que ya conocemos: si quedó otra instancia
    abierta, o cualquier otro programa lo tomó, la aplicación no arranca y el
    mensaje no dice por qué. Pedirlo prestado al sistema operativo no puede
    chocar.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def esperar_al_servidor(puerto: int, timeout: float = 30.0) -> bool:
    """Hasta que acepte conexiones.

    Abrir la ventana antes de que el servidor conteste muestra una página de
    error, y el usuario ve una aplicación rota en el primer segundo de uso.
    Cargar pandas y numpy tarda unos segundos en un disco lento.
    """
    limite = time.time() + timeout
    while time.time() < limite:
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def main() -> int:
    import uvicorn
    import webview

    from botiquant import __version__

    puerto = puerto_libre()

    # El servidor va en un hilo de fondo; la ventana se queda con el hilo
    # principal porque las interfaces gráficas lo exigen en Windows y macOS.
    config = uvicorn.Config("botiquant.api.app:app", host="127.0.0.1",
                            port=puerto, log_level="warning")
    servidor = uvicorn.Server(config)
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()

    if not esperar_al_servidor(puerto):
        print("El servidor interno no respondió a tiempo.", file=sys.stderr)
        return 1

    ventana = webview.create_window(
        f"BotiQuant {__version__}",
        f"http://127.0.0.1:{puerto}/app",
        width=1440, height=900, min_size=(1024, 680),
        confirm_close=False,
    )

    def al_cerrar():
        # Sin esto, uvicorn sigue vivo con el puerto tomado y el proceso queda
        # colgado en segundo plano después de cerrar la ventana.
        servidor.should_exit = True

    ventana.events.closed += al_cerrar
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
