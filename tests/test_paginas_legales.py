"""Privacidad y términos: sin estas dos páginas Google no publica la aplicación.

Con la pantalla de consentimiento en modo prueba sólo entran los correos
cargados a mano, uno por uno. Para que se registre cualquiera que llegue de un
video hay que publicarla, y para publicarla Google pide un enlace a la política
de privacidad que pueda abrir y leer.

Que existan como archivo no alcanza: tienen que responder 200 sin sesión —el
revisor de Google no tiene cuenta— y estar enlazadas desde la portada.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app

SECRET = "x" * 40


@pytest.fixture()
def client(tmp_path):
    app = create_app(workdir=tmp_path)
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("ruta", ["/privacidad", "/terminos"])
def test_se_abren_sin_cuenta(client, ruta):
    r = client.get(ruta)
    assert r.status_code == 200
    assert "<h1>" in r.text


@pytest.mark.parametrize("ruta", ["/privacidad", "/terminos"])
def test_siguen_abiertas_con_login_configurado(tmp_path, monkeypatch, ruta):
    """El caso que importa: en el servidor real hay Google configurado y el
    revisor entra sin sesión. Si la puerta de las cuentas se las tragara, la
    aplicación quedaría en modo prueba para siempre."""
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id-de-prueba")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secreto-de-prueba")
    with TestClient(create_app(workdir=tmp_path)) as c:
        assert c.get(ruta).status_code == 200


def test_la_hoja_de_estilos_tambien_carga(client):
    r = client.get("/static-landing/legal.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_la_portada_enlaza_las_dos(client):
    """Google pide el enlace a la vista, no una URL suelta que sólo sabe quien
    la escribió."""
    portada = client.get("/").text
    assert 'href="/privacidad"' in portada
    assert 'href="/terminos"' in portada


def test_dicen_lo_que_la_aplicacion_hace_de_verdad(client):
    """Una política copiada de una plantilla miente por omisión. Estas dos
    afirmaciones son las que distinguen a Botiquant y tienen que estar."""
    priv = client.get("/privacidad").text
    # el minado corre en la máquina del usuario: eso es lo que hay que declarar
    assert "sin conexión" in priv
    assert "LOCALAPPDATA" in priv
    # y lo que NO se recoge
    assert "contraseña" in priv.lower()

    term = client.get("/terminos").text
    assert "riesgo" in term.lower()
    assert "no es asesoramiento" in term.lower() or "no es un asesor" in term.lower()


def test_las_dos_paginas_se_enlazan_entre_si(client):
    assert 'href="/terminos"' in client.get("/privacidad").text
    assert 'href="/privacidad"' in client.get("/terminos").text
