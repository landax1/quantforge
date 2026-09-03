"""El secreto de un enlace compartido no puede vivir sólo en el navegador.

Un enlace publicado se apaga con su secreto, y el secreto se guardaba
únicamente en `localStorage`. Una usuaria de prueba lo encontró el 3 de
septiembre de 2026: vaciar el navegador —o abrir la aplicación en otro— dejaba
una página PUBLICADA en internet que su propio autor ya no podía bajar.

La copia que sobrevive vive en el archivo del espacio de trabajo, en la máquina
de quien compartió. No cambia el diseño de compartir —sigue sin cuentas, sigue
siendo el secreto lo único que apaga— sólo deja de depender del navegador.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app


@pytest.fixture()
def c():
    app = create_app(workdir=pathlib.Path(tempfile.mkdtemp()))
    with TestClient(app) as cliente:
        yield cliente


def test_un_enlace_anotado_se_puede_recuperar(c):
    r = c.post("/api/enlaces", json={"codigo": "abc123", "secreto": "s3cr3to",
                                     "url": "https://botiquant.com/s/abc123",
                                     "nombre": "S-007-ETH", "nivel": "mirar"})
    assert r.status_code == 200, r.text[:200]

    lista = c.get("/api/enlaces").json()
    assert len(lista) == 1
    e = lista[0]
    assert e["codigo"] == "abc123"
    assert e["secreto"] == "s3cr3to", "sin el secreto no se puede apagar nada"
    assert e["nombre"] == "S-007-ETH"
    assert e["nivel"] == "mirar"
    assert e["apagado"] == 0


def test_anotar_dos_veces_no_duplica_ni_pierde_la_fecha(c):
    c.post("/api/enlaces", json={"codigo": "abc123", "secreto": "s1", "nombre": "uno"})
    primero = c.get("/api/enlaces").json()[0]
    c.post("/api/enlaces", json={"codigo": "abc123", "secreto": "s1", "nombre": "dos"})
    lista = c.get("/api/enlaces").json()
    assert len(lista) == 1
    assert lista[0]["nombre"] == "dos"
    assert lista[0]["creado"] == primero["creado"], "la fecha original se perdió"


def test_apagar_queda_registrado(c):
    c.post("/api/enlaces", json={"codigo": "abc123", "secreto": "s1"})
    assert c.post("/api/enlaces/abc123/apagado", json={}).status_code == 200
    assert c.get("/api/enlaces").json()[0]["apagado"] == 1


def test_apagar_no_borra_el_secreto(c):
    """Se sigue pudiendo probar que era propio, y reintentar si el apagado
    remoto falló a mitad de camino."""
    c.post("/api/enlaces", json={"codigo": "abc123", "secreto": "s1"})
    c.post("/api/enlaces/abc123/apagado", json={})
    assert c.get("/api/enlaces").json()[0]["secreto"] == "s1"


def test_hace_falta_el_codigo_y_el_secreto(c):
    assert c.post("/api/enlaces", json={"codigo": "abc"}).status_code == 400
    assert c.post("/api/enlaces", json={"secreto": "s"}).status_code == 400


def test_el_registro_es_del_escritorio(c, monkeypatch):
    """En el servidor público no existe "este equipo": ahí el registro no va.

    Y no es un detalle de permisos: la tabla guarda SECRETOS, que es lo único
    que permite bajar una página publicada. En un servidor compartido serían
    los secretos de todos.

    Se cambia el módulo y no la variable de entorno: `MULTIUSER` se lee una
    sola vez al importar, así que `setenv` después no cambia nada.
    """
    import botiquant.api.app as mod

    monkeypatch.setattr(mod, "MULTIUSER", True)
    assert c.get("/api/enlaces").status_code == 404
    assert c.post("/api/enlaces", json={"codigo": "a", "secreto": "b"}).status_code == 404
