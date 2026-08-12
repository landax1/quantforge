"""Dónde está cada cosa, corriendo desde el repositorio o desde el .exe.

Son dos situaciones con reglas distintas y mezclarlas rompe cosas silenciosas.

Corriendo desde el repositorio todo cuelga de la carpeta del proyecto, que es
lo cómodo para desarrollar: se edita la interfaz y se recarga.

Empaquetado hay que separar dos cosas que en desarrollo viven juntas:

* Lo que VIENE con el programa (la interfaz, la portada) sale de la carpeta
  temporal donde PyInstaller descomprime el ejecutable. Es de sólo lectura y
  Windows la borra al cerrar.

* Lo que el usuario GENERA (su base, sus velas, sus estrategias) tiene que ir
  a una carpeta suya y permanente. Dejarlo junto al programa —que es lo que
  hacía -- significaba que la base y los gigas de datos descargados se
  borraban en cada cierre, y el usuario abría la aplicación vacía cada vez sin
  entender por qué.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def empaquetado() -> bool:
    """True si estamos dentro del ejecutable y no en el repositorio."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def raiz_recursos() -> Path:
    """De dónde salen los archivos que vienen CON el programa."""
    if empaquetado():
        return Path(sys._MEIPASS)                        # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def carpeta_de_trabajo() -> Path:
    """Dónde se guarda lo que el usuario genera. Siempre escribible.

    `BQ_WORKSPACE` la fuerza, que es lo que usan los tests y lo que permite
    mover los datos a otro disco sin reinstalar.
    """
    forzada = os.environ.get("BQ_WORKSPACE", "").strip()
    if forzada:
        return Path(forzada)

    if not empaquetado():
        return raiz_recursos() / "workspace"

    # En Windows LOCALAPPDATA es la carpeta para datos de aplicación que no
    # viajan con el perfil: son gigas de velas, no tiene sentido sincronizarlos.
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "Botiquant"
    return Path.home() / ".botiquant"
