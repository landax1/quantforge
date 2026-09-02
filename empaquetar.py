"""Compila el ejecutable y deja el zip que descarga la página.

Uso: .venv\Scripts\python.exe empaquetar.py [--sin-compilar]

La página sirve dist/Botiquant-Windows.zip. Si se compila con PyInstaller
a mano y no se rehace el zip, el botón "Descargar" entrega una versión
vieja: pasó el 2 de septiembre (zip del 21 de agosto con un exe de hoy al
lado). Este script deja los dos pasos juntos para que no vuelva a pasar.
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CARPETA = RAIZ / "dist" / "Botiquant"
ZIP = RAIZ / "dist" / "Botiquant-Windows.zip"


def compilar() -> None:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "botiquant.spec"],
        cwd=RAIZ,
        check=True,
    )


def comprimir() -> None:
    exe = CARPETA / "Botiquant.exe"
    if not exe.is_file():
        raise SystemExit(f"No existe {exe}; compilá primero.")
    temporal = ZIP.with_suffix(".zip.parcial")
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for archivo in sorted(CARPETA.rglob("*")):
            if archivo.is_file():
                z.write(archivo, archivo.relative_to(CARPETA.parent))
    temporal.replace(ZIP)
    print(f"{ZIP.name}: {ZIP.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    if "--sin-compilar" not in sys.argv:
        compilar()
    comprimir()
