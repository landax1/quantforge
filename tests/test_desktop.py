"""Arranque de BotiQuant Desktop.

No se abre la ventana: eso necesita un escritorio y bloquearía. Se prueba todo
lo demás, que es donde estaban los problemas de arranque.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

import desktop


def test_the_port_is_actually_free():
    """Fijar un número trae el problema que ya conocemos: si quedó otra
    instancia abierta, la aplicación no arranca y el mensaje no dice por qué."""
    p = desktop.puerto_libre()
    assert 1024 < p < 65536
    with socket.socket() as s:
        s.bind(("127.0.0.1", p))          # si estuviera tomado, esto reventaría


def test_two_instances_never_get_the_same_port():
    """Dos ventanas abiertas a la vez no pueden pelearse el puerto."""
    tomados = set()
    abiertos = []
    try:
        for _ in range(5):
            p = desktop.puerto_libre()
            assert p not in tomados
            tomados.add(p)
            s = socket.socket()
            s.bind(("127.0.0.1", p))
            s.listen(1)
            abiertos.append(s)
    finally:
        for s in abiertos:
            s.close()


def test_waiting_gives_up_instead_of_hanging():
    """Si el servidor nunca levanta, la espera tiene que terminar: colgada para
    siempre, la aplicación no abre ni muestra un error."""
    t0 = time.time()
    assert desktop.esperar_al_servidor(desktop.puerto_libre(), timeout=0.6) is False
    assert time.time() - t0 < 3.0


def test_waiting_returns_as_soon_as_it_answers():
    p = desktop.puerto_libre()
    listo = threading.Event()

    def servidor_falso():
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", p))
        s.listen(2)
        listo.set()
        try:
            s.settimeout(3)
            conexion, _ = s.accept()
            conexion.close()
        except OSError:
            pass
        s.close()

    h = threading.Thread(target=servidor_falso, daemon=True)
    h.start()
    listo.wait(timeout=3)

    assert desktop.esperar_al_servidor(p, timeout=3.0) is True


def test_desktop_mode_asks_for_no_account(tmp_path, monkeypatch):
    """En el escritorio la identidad la da la licencia, no una sesión: la
    pantalla tiene que abrir directo, sin rebotar a un login que no existe."""
    from fastapi.testclient import TestClient

    import botiquant.api.app as appmod

    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)

    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        assert c.get("/app", follow_redirects=False).status_code == 200
        assert c.get("/api/datasets").status_code == 200
        assert c.get("/api/auth/me").json() == {"configurado": False, "usuario": None}


def test_desktop_keeps_the_local_powers(tmp_path, monkeypatch):
    """La máquina es del usuario: importar sus archivos y borrar lo suyo no
    puede estar bloqueado como en el servidor compartido."""
    from fastapi.testclient import TestClient

    import botiquant.api.app as appmod

    monkeypatch.setenv("BQ_MULTIUSER", "0")
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)

    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        c.post("/api/datasets/sample", json={"symbol": "MIO", "bars": 900})
        ds = c.get("/api/datasets").json()[0]["id"]
        assert c.delete(f"/api/datasets/{ds}").status_code == 200
        assert c.get("/api/datasets").json() == []


@pytest.mark.parametrize("var", ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"])
def test_importing_desktop_clears_the_web_credentials(var):
    """Si el .env del desarrollo tiene credenciales, la ventana no puede
    arrancar pidiendo iniciar sesión con Google."""
    import os

    assert os.environ.get(var) in (None, "")


# --------------------------------------------------------------- la marca
def test_el_ejecutable_lleva_su_icono():
    """El icono del ARCHIVO no es el favicon: son dos cosas distintas y sólo
    estaba puesta la segunda. Sin `icon=` en el spec, Windows le pone el
    genérico a la ventana, a la barra de tareas y al Explorador — el usuario se
    baja la aplicación y en su escritorio ve un icono de sistema."""
    import pathlib

    spec = pathlib.Path(__file__).resolve().parent.parent / "botiquant.spec"
    assert 'icon="botiquant.ico"' in spec.read_text(encoding="utf-8")

    ico = spec.parent / "botiquant.ico"
    assert ico.exists(), "el spec apunta a un icono que no está"
    assert ico.stat().st_size > 5_000, "un .ico de una sola resolución no alcanza"


def test_el_icono_trae_los_tamanos_que_windows_pide():
    """Windows elige la resolución según dónde lo muestre: 16 en la barra de
    título, 32 en el Explorador, 48 en la barra de tareas. Con una sola, la
    reescala él y a 16 píxeles el pulpo queda hecho un borrón."""
    import pathlib
    import struct

    ico = pathlib.Path(__file__).resolve().parent.parent / "botiquant.ico"
    crudo = ico.read_bytes()
    # cabecera ICO: reservado(2) tipo(2) cantidad(2), y después una entrada de
    # 16 bytes por imagen que arranca con ancho y alto (0 significa 256)
    _, tipo, cantidad = struct.unpack("<HHH", crudo[:6])
    assert tipo == 1, "no es un icono"
    lados = set()
    for i in range(cantidad):
        ancho = crudo[6 + i * 16]
        lados.add(ancho or 256)
    for necesario in (16, 32, 48):
        assert necesario in lados, f"le falta la resolución de {necesario}px: {sorted(lados)}"
