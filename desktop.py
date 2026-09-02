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


def soltar_la_marca_de_internet() -> int:
    """Le saca a los archivos propios la marca de "bajado de internet".

    Sin esto la aplicación no abre en la máquina de nadie que la haya
    descargado, que son todas. Está medido: mismo binario, con la marca muere
    con un Traceback y sin la marca abre la ventana.

    Windows marca el ZIP al descargarlo y el Explorador propaga esa marca a
    cada archivo que extrae. .NET Framework se niega a cargar un ensamblado
    marcado, así que ``Python.Runtime.dll`` —que es lo que pywebview necesita
    para dibujar la ventana— no carga nunca.

    La marca es un flujo alternativo de NTFS colgado del archivo
    (``algo.dll:Zone.Identifier``) y se borra como se borra cualquier archivo.
    Se hace acá, al principio de todo, porque después de importar ``webview``
    ya es tarde.

    Devuelve cuántas quitó. Nunca levanta excepción: si falla, lo peor que
    puede pasar es el error que ya teníamos.
    """
    if not getattr(sys, "frozen", False):
        return 0                      # en desarrollo no hay nada descargado
    # En un empaquetado de carpeta, _MEIPASS es `_internal`, que es donde viven
    # los DLL. El .exe está justo afuera.
    interno = Path(getattr(sys, "_MEIPASS", "") or RAIZ)
    quitadas = 0
    for archivo in list(interno.rglob("*")) + [Path(sys.executable)]:
        try:
            if not archivo.is_file():
                continue
            # borrar el flujo, no el archivo. Si no existe, FileNotFoundError.
            os.remove(f"{archivo}:Zone.Identifier")
            quitadas += 1
        except OSError:
            # no existe (lo normal), o la carpeta es de sólo lectura. En el
            # segundo caso el arranque va a fallar igual y el mensaje de más
            # abajo lo explica; acá no hay nada que hacer.
            continue
    return quitadas


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


def perfil_del_navegador(workdir: Path) -> Path:
    """Dónde guarda el navegador interno lo suyo: cookies, preferencias,
    almacenamiento local. Dentro del espacio de trabajo, por encima de la
    carpeta temporal que pywebview usaría —y abandonaría— si no se le dice."""
    perfil = Path(workdir) / "navegador"
    perfil.mkdir(parents=True, exist_ok=True)
    return perfil


def main() -> int:
    import uvicorn

    # ANTES de importar webview, que es lo que arrastra a .NET. Después de esta
    # línea ya no se puede arreglar: el import falla y se lleva el proceso.
    soltar_la_marca_de_internet()

    try:
        import webview
    except Exception as exc:      # noqa: BLE001 — cualquier fallo del import
        # Si a pesar de la limpieza .NET sigue sin cargar, el usuario merece
        # una frase y no ochenta líneas de Traceback que no le dicen nada.
        # El caso conocido es una carpeta donde no se puede escribir: dentro
        # del propio ZIP, en una carpeta de red, o en Archivos de programa.
        print(
            "Botiquant no pudo abrir su ventana.\n\n"
            "Casi siempre es porque se está ejecutando desde adentro del ZIP o "
            "desde una carpeta protegida.\n"
            "Extraé la carpeta Botiquant a tu Escritorio o a Documentos y abrí "
            "Botiquant.exe desde ahí.\n\n"
            f"Detalle técnico: {exc}",
            file=sys.stderr)
        return 1

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

    # pywebview CANCELA todas las descargas por defecto: su manejador pone
    # `args.Cancel = True` y no avisa a nadie. Con eso, el botón de bajar el
    # Expert Advisor no hacía nada — ni archivo, ni error, ni mensaje. Es la
    # clase de falla peor que un error, porque parece que la aplicación te
    # ignora.
    #
    # La aplicación guarda los .mq5 y los .pine ella misma en una carpeta fija
    # (ver rutas.carpeta_de_estrategias), que es mejor que una descarga porque
    # no hay diálogo y la ruta se puede decir. Esto queda igual habilitado para
    # todo lo demás que el navegador sí baja por su cuenta: los informes en
    # HTML, el Excel y los CSV de operaciones.
    webview.settings["ALLOW_DOWNLOADS"] = True

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
    # EL NAVEGADOR INTERNO TIENE QUE RECORDAR. pywebview abre en modo privado
    # por defecto: cada arranque estrenaba un perfil en %TEMP% y lo dejaba
    # ahí (41 carpetas, 99 MB, medido el 2 de septiembre), y ninguna
    # preferencia sobrevivía a cerrar: idioma, tema, qué sección se opera,
    # la búsqueda que había que retomar. El perfil vive junto a la base de
    # datos, así que borrar el espacio de trabajo también lo borra.
    from botiquant.api.app import WORK_DIR

    webview.start(private_mode=False, storage_path=str(perfil_del_navegador(WORK_DIR)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
