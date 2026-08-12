"""Dónde escribe la aplicación cuando está empaquetada.

Es la regla que más silenciosamente destruye datos: si el workspace queda
dentro del ejecutable, Windows borra esa carpeta al cerrar y el usuario abre la
aplicación vacía cada vez, sin ningún error que se lo explique.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from botiquant import rutas


@pytest.fixture()
def como_exe(tmp_path, monkeypatch):
    """Finge que corremos desde el .exe."""
    extraccion = tmp_path / "_MEI12345"
    extraccion.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraccion), raising=False)
    monkeypatch.delenv("BQ_WORKSPACE", raising=False)
    return extraccion


def test_from_the_repo_everything_lives_in_the_project(monkeypatch):
    monkeypatch.delenv("BQ_WORKSPACE", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert not rutas.empaquetado()
    assert rutas.carpeta_de_trabajo() == rutas.raiz_recursos() / "workspace"


def test_packaged_the_workspace_is_never_inside_the_executable(como_exe, monkeypatch):
    """El corazón del asunto. La carpeta de PyInstaller se borra al cerrar: la
    base y los gigas de velas descargadas se irían con ella."""
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\alguien\AppData\Local")

    trabajo = rutas.carpeta_de_trabajo()

    assert rutas.raiz_recursos() == como_exe
    assert como_exe not in trabajo.parents
    assert trabajo != como_exe
    assert trabajo == Path(r"C:\Users\alguien\AppData\Local") / "Botiquant"


def test_packaged_resources_come_from_the_bundle(como_exe):
    """La interfaz y la portada sí salen de adentro del ejecutable: vienen con
    el programa y son de sólo lectura."""
    assert rutas.raiz_recursos() == como_exe


def test_the_workspace_can_be_moved_with_an_env_var(tmp_path, monkeypatch):
    """Sin esto no habría forma de mover los datos a otro disco, y son gigas."""
    otro = tmp_path / "disco-d" / "Botiquant"
    monkeypatch.setenv("BQ_WORKSPACE", str(otro))
    assert rutas.carpeta_de_trabajo() == otro


def test_there_is_always_a_writable_fallback(como_exe, monkeypatch):
    """Si LOCALAPPDATA no existiera, quedarse sin carpeta dejaría la aplicación
    sin poder guardar nada. Se cae a la del usuario."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    trabajo = rutas.carpeta_de_trabajo()

    assert trabajo == Path.home() / ".botiquant"
    assert como_exe not in trabajo.parents


def test_the_app_actually_writes_where_it_says(tmp_path, monkeypatch):
    """No alcanza con que la función devuelva la ruta: la aplicación tiene que
    usarla de verdad."""
    from fastapi.testclient import TestClient

    import botiquant.api.app as appmod

    destino = tmp_path / "mis-datos"
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)

    with TestClient(appmod.create_app(workdir=destino)) as c:
        c.post("/api/datasets/sample", json={"symbol": "TEST", "bars": 900})

    assert (destino / "botiquant.sqlite").is_file()
    assert list((destino / "datasets").glob("*.csv")), "las velas no se guardaron"
