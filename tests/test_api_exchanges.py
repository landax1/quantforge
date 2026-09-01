"""La pantalla de exchanges, del lado del servidor.

Lo que se defiende acá es que la clave entre, se guarde cifrada, y NO vuelva a
salir por ningún endpoint. Un secreto que se puede leer con un GET deja de
estar protegido por más cifrado que tenga el archivo.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app

CLAVE = "CLAVE_PUBLICA_1234"
SECRETO = "SECRETO_QUE_NO_PUEDE_SALIR_POR_NINGUN_ENDPOINT"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(workdir=tmp_path / "ws")) as c:
        yield c


def _guardar(client, entorno="practica", **kw):
    cuerpo = {"api_key": CLAVE, "secret": SECRETO}
    cuerpo.update(kw)
    return client.post(f"/api/exchanges/bingx/{entorno}", json=cuerpo)


# ------------------------------------------------------------ guardar y ver

def test_se_guarda_y_aparece_como_configurada(client):
    r = _guardar(client)
    assert r.status_code == 200, r.text
    assert r.json()["configurada"] is True

    listado = client.get("/api/exchanges").json()
    practica = [x for x in listado if x["entorno"] == "practica"][0]
    assert practica["configurada"] is True
    assert practica["termina_en"] == CLAVE[-4:]


def test_ningun_endpoint_devuelve_el_secreto(client):
    """La prueba central de toda la pantalla.

    El cifrado del archivo no sirve de nada si el secreto sale por un GET.
    Se revisan las tres respuestas que ve el navegador.
    """
    guardado = _guardar(client).text
    listado = client.get("/api/exchanges").text
    comprobado = client.post("/api/exchanges/bingx/practica/comprobar").text

    for cuerpo, donde in ((guardado, "guardar"), (listado, "listar"),
                          (comprobado, "comprobar")):
        assert SECRETO not in cuerpo, f"el secreto salió por {donde}"
        assert CLAVE not in cuerpo, f"la clave entera salió por {donde}"


def test_practica_y_real_no_se_pisan(client):
    _guardar(client, entorno="practica", api_key="DEMO1234")
    _guardar(client, entorno="real", api_key="REAL5678")
    # Se indexa por exchange Y entorno: con mas de un exchange, la practica de
    # uno pisaba la del otro y el test pasaba por casualidad.
    listado = {(x["exchange"], x["entorno"]): x
               for x in client.get("/api/exchanges").json()}
    assert listado[("bingx", "practica")]["termina_en"] == "1234"
    assert listado[("bingx", "real")]["termina_en"] == "5678"


def test_sin_configurar_lo_dice_y_no_revienta(client):
    listado = client.get("/api/exchanges").json()
    assert all(x["configurada"] is False for x in listado)


# ---------------------------------------------------------------- validar

def test_una_clave_vacia_se_rechaza(client):
    assert _guardar(client, secret="").status_code == 400


def test_un_exchange_desconocido_se_rechaza(client):
    r = client.post("/api/exchanges/kraken/practica",
                    json={"api_key": CLAVE, "secret": SECRETO})
    assert r.status_code == 400


def test_binance_en_REAL_se_rechaza(client):
    """Binance está habilitado sólo en demo. Guardar una clave real dejaría en
    pantalla un "configurada" que promete algo que la aplicación no puede
    hacer."""
    r = client.post("/api/exchanges/binance/real",
                    json={"api_key": CLAVE, "secret": SECRETO})
    assert r.status_code == 400


def test_binance_en_practica_se_acepta(client):
    r = client.post("/api/exchanges/binance/practica",
                    json={"api_key": CLAVE, "secret": SECRETO})
    assert r.status_code == 200 and r.json()["configurada"] is True


def test_un_entorno_inventado_se_rechaza(client):
    r = client.post("/api/exchanges/bingx/produccion",
                    json={"api_key": CLAVE, "secret": SECRETO})
    assert r.status_code == 400


# ---------------------------------------------------------------- borrar

def test_borrar_la_saca_de_la_maquina(client):
    _guardar(client)
    assert client.delete("/api/exchanges/bingx/practica").json()["borrada"] is True
    listado = {x["entorno"]: x for x in client.get("/api/exchanges").json()}
    assert listado["practica"]["configurada"] is False


def test_borrar_lo_que_no_hay_no_es_un_error(client):
    assert client.delete("/api/exchanges/bingx/practica").json()["borrada"] is False


# ------------------------------------------------------------- comprobar

def test_comprobar_sin_clave_corta_en_el_paso_de_la_clave(client):
    """Los primeros pasos NO usan la clave.

    Si fallan, el problema es de red o de región y no de credenciales.
    Distinguirlo acá ahorra media hora revisando una clave que estaba bien.
    """
    r = client.post("/api/exchanges/bingx/practica/comprobar").json()
    assert r["listo"] is False
    nombres = [p["paso"] for p in r["pasos"]]
    assert "clave" in nombres
    fallo = [p for p in r["pasos"] if not p["ok"]][0]
    assert fallo["paso"] == "clave", (
        "tendría que haber pasado la comprobación que no necesita clave")


def test_comprobar_nunca_manda_una_orden(client, monkeypatch):
    """Es una comprobación, no una prueba de operar.

    Si algún día alguien agrega un "y probamos una orden mínima" acá, esto se
    pone rojo: comprobar la conexión no puede mover plata.
    """
    from botiquant.vivo import adaptador

    def _prohibido(*a, **k):
        raise AssertionError("comprobar la conexión mandó una orden")

    monkeypatch.setattr(adaptador.BingX, "abrir", _prohibido)
    monkeypatch.setattr(adaptador.BingX, "cerrar", _prohibido)
    _guardar(client)
    client.post("/api/exchanges/bingx/practica/comprobar")


# ---------------------------------------------------- sólo en el escritorio

def test_servido_a_varios_estos_endpoints_no_existen(tmp_path, monkeypatch):
    """Guardar las claves de trading de otras personas es custodia de
    credenciales ajenas, que es un problema completamente distinto y no es lo
    que esta aplicación hace."""
    monkeypatch.setenv("BQ_MULTIUSER", "1")
    import importlib

    from botiquant.api import app as modulo
    importlib.reload(modulo)
    try:
        with TestClient(modulo.create_app(workdir=tmp_path / "ws")) as c:
            assert c.get("/api/exchanges").status_code == 404
            assert c.post("/api/exchanges/bingx/practica",
                          json={"api_key": "a", "secret": "b"}).status_code == 404
    finally:
        monkeypatch.delenv("BQ_MULTIUSER", raising=False)
        importlib.reload(modulo)


def test_el_rechazo_del_exchange_no_viene_envuelto_en_espaniol(client):
    """La interfaz está en dos idiomas; el texto de BingX viene en inglés.

    Una frase en español alrededor de un mensaje en inglés queda mal en los
    dos idiomas. Se muestra el código y el texto del exchange, que además es
    lo que se busca cuando hay que preguntarle a alguien.
    """
    _guardar(client, api_key="CLAVE_QUE_NO_EXISTE_1234")
    r = client.post("/api/exchanges/bingx/practica/comprobar").json()
    fallo = [p for p in r["pasos"] if not p["ok"]]
    if not fallo:
        pytest.skip("hoy BingX aceptó la clave falsa; nada que comprobar")
    detalle = fallo[0]["detalle"]
    assert "rechazó" not in detalle, "el envoltorio en español volvió"
    assert detalle.startswith("[") or "No hay claves" in detalle
