# -*- mode: python ; coding: utf-8 -*-
"""Empaquetado de BotiQuant Desktop.

Se usa un .spec y no la línea de comandos porque hay tres cosas que PyInstaller
no adivina solo y que, si faltan, fallan recién al ejecutar y no al compilar:

* La interfaz y la portada son archivos de datos, no módulos: hay que decirle
  explícitamente que los incluya.
* uvicorn y fastapi cargan partes suyas por nombre en tiempo de ejecución, así
  que el análisis estático no las ve.
* pandas y numpy arrastran binarios enormes; sin excluir lo que no usamos, el
  ejecutable se va a más de 400 MB.
"""

import sys

from PyInstaller.utils.hooks import collect_submodules

# `botiquant` no esta instalado en el entorno: se importa porque la raiz del
# proyecto esta en sys.path. Con `python -m PyInstaller` eso pasa solo, porque
# sys.path[0] es el directorio actual; con `pyinstaller.exe` NO, porque
# sys.path[0] es `.venv/Scripts`. Sin esta linea, el collect_submodules de mas
# abajo devuelve una lista vacia — no falla, devuelve vacia — y el ejecutable
# sale sin la aplicacion adentro.
if SPECPATH not in sys.path:                                   # noqa: F821
    sys.path.insert(0, SPECPATH)                               # noqa: F821

RECURSOS = [
    ("ui", "ui"),                 # la aplicación
    ("landing", "landing"),       # portada y página de cuenta
    ("semilla", "semilla"),       # instrumentos H1 para no abrir vacío
]

# Lo que se carga por nombre y el análisis estático no puede ver.
OCULTOS = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    *collect_submodules("botiquant"),
]

# Un empaquetado roto que se publica es peor que uno que no se genera.
#
# Esto ya paso: `collect_submodules` no encontro el paquete, devolvio vacio, y
# PyInstaller construyo un .exe de 6 MB sin la aplicacion ni pandas, con cero
# errores y cero advertencias. Se descubrio comparando el tamanio con el
# anterior. Sin este corte se descubre cuando lo abre un usuario.
_DEL_PAQUETE = [m for m in OCULTOS if m.startswith("botiquant")]
if len(_DEL_PAQUETE) < 20:
    raise SystemExit(
        f"Empaquetado abortado: solo se encontraron {len(_DEL_PAQUETE)} modulos "
        "de botiquant (tendrian que ser unos cincuenta).\n"
        "El paquete no es importable desde aca, asi que el ejecutable saldria "
        "sin la aplicacion adentro.\n"
        "Correlo desde la raiz del proyecto."
    )

# Sin esto entran matplotlib, tkinter y las pruebas de scipy: cientos de
# megabytes que la aplicación no usa nunca.
FUERA = [
    "matplotlib", "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6",
    "IPython", "jupyter", "notebook", "pytest", "sphinx",
    "numpy.testing", "pandas.tests", "scipy",
    # Pillow entró de arrastre al instalarlo para procesar el logo de la marca.
    # La aplicación no abre imágenes: el pulpo viaja como base64 dentro del CSS.
    # Son 13 MB en una descarga que el usuario espera.
    "PIL", "Pillow",
]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=RECURSOS,
    hiddenimports=OCULTOS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=FUERA,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Botiquant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Sin consola: es una aplicación de ventana. Los errores de arranque se
    # muestran en la propia ventana, no en una terminal negra que asusta.
    console=False,
    # El icono del ARCHIVO, que no es el favicon: son dos cosas distintas y
    # sólo estaba puesta la segunda. Sin esto Windows le pone el genérico a la
    # ventana, a la barra de tareas y al Explorador — el usuario se baja la
    # aplicación y en su escritorio ve un icono de sistema, no su marca.
    #
    # Lleva siete resoluciones porque Windows elige según dónde lo muestre:
    # 16 en la barra de título, 32 en el Explorador, 48 en la barra de tareas,
    # 256 en vista grande. Con una sola, Windows la reescala y a 16 píxeles el
    # pulpo se convierte en un borrón.
    icon="botiquant.ico",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Carpeta y no archivo único: un .exe de un solo archivo se descomprime entero
# en disco en cada arranque, y con pandas adentro eso son varios segundos de
# espera cada vez que se abre la aplicación.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Botiquant",
)
