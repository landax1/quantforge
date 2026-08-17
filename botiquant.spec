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

from PyInstaller.utils.hooks import collect_submodules

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
