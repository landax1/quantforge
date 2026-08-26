"""El archivo que enlaza una estrategia con BingX.

A diferencia de los otros dos exportadores, lo que sale de acá no lo lee una
persona ni un compilador: lo lee un programa que manda órdenes con plata. Por
eso las pruebas se concentran en dos cosas —que no salga lo que no tiene que
salir, y que un archivo roto se rechace ANTES de conectarse a ningún lado— más
que en el formato del texto.
"""

from __future__ import annotations

import json

import pytest

from botiquant.core.models import StrategySpec
from botiquant.reports.bingx import (FORMATO, VERSION, a_simbolo_bingx,
                                     export_bingx, leer_bingx)


@pytest.fixture
def spec() -> StrategySpec:
    return StrategySpec.from_dict({
        "name": "prueba", "direction": "both",
        "entry_long": [{"op": "cross_above",
                        "left": {"type": "indicator", "name": "EMA",
                                 "params": {"period": 10}},
                        "right": {"type": "indicator", "name": "EMA",
                                  "params": {"period": 30}}}],
        "entry_short": [{"op": "cross_below",
                         "left": {"type": "indicator", "name": "EMA",
                                  "params": {"period": 10}},
                         "right": {"type": "indicator", "name": "EMA",
                                   "params": {"period": 30}}}],
        "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                 "stop_type": "atr", "stop_value": 2.0,
                 "target_type": "atr", "target_value": 4.0,
                 "reward_ratio": 2.0, "atr_period": 14},
    })


# ------------------------------------------------------------ los símbolos

@pytest.mark.parametrize("origen,esperado", [
    ("BTCUSDT", "BTC-USDT"),
    ("ETHUSDT", "ETH-USDT"),
    ("BTCUSDC", "BTC-USDC"),
])
def test_traduce_el_simbolo_al_formato_del_exchange(origen, esperado):
    assert a_simbolo_bingx(origen) == esperado


def test_no_parte_por_longitud_fija():
    """USDT son cuatro letras y USD son tres.

    Partir a lo bruto por las últimas tres daría "BTCU" + "SDT": un símbolo que
    no existe, o peor, uno que existe y es otro.
    """
    assert a_simbolo_bingx("BTCUSDT") == "BTC-USDT"
    assert a_simbolo_bingx("XAUUSD") == "XAU-USD"


def test_un_simbolo_desconocido_se_deja_como_esta():
    """No inventa. Que falle del lado del exchange con su propio mensaje."""
    assert a_simbolo_bingx("SP500") == "SP500"


# ------------------------------------------------------------ el contenido

def test_la_clave_de_api_nunca_esta_en_el_archivo(spec):
    """La prueba más importante de este archivo.

    El de enlace se puede mandar por mail, subir a un foro o pegarlo en un
    video sin consecuencias. Si algún día alguien agrega un campo de
    credenciales "para que sea un solo archivo", esto tiene que ponerse rojo.
    """
    texto = export_bingx(spec, symbol_source="BTCUSDT").lower()
    for prohibido in ("apikey", "api_key", "secret", "clave", "password",
                      "passphrase", "token"):
        assert prohibido not in texto, f"apareció '{prohibido}' en el archivo"


def test_los_dos_simbolos_viajan_separados(spec):
    """Se mina en Binance y se opera en BingX, y no son el mismo instrumento.

    Correlacionan 0,99974, que para decidir es lo mismo — pero lo mismo no es
    idéntico, y el archivo tiene que dejar dicho de dónde salió cada cosa en
    vez de que alguien lo deduzca seis meses después.
    """
    doc = json.loads(export_bingx(spec, symbol_source="BTCUSDT"))
    assert doc["medido_en"]["simbolo"] == "BTCUSDT"
    assert doc["medido_en"]["fuente"] == "binance"
    assert doc["ejecucion"]["simbolo"] == "BTC-USDT"
    assert doc["ejecucion"]["exchange"] == "bingx"


def test_arranca_sin_apalancamiento(spec):
    """El backtest midió con el tamaño que dice `risk`.

    Multiplicarlo del lado del exchange haría que lo que opera no sea lo que se
    midió, y el número del respaldo pasaría a ser una mentira silenciosa.
    """
    doc = json.loads(export_bingx(spec, symbol_source="BTCUSDT"))
    assert doc["ejecucion"]["apalancamiento"] == 1


def test_el_respaldo_del_backtest_viaja_con_la_estrategia(spec):
    """Para poder mirar, al arrancar el bot, sobre qué se está parando."""
    doc = json.loads(export_bingx(
        spec, symbol_source="BTCUSDT",
        metrics={"net_profit": 1234.5, "trades": 88},
        costs={"commission_pct": 0.04},
        measured_from="2019-09-10", measured_to="2026-08-26"))
    assert doc["respaldo"]["trades"] == 88
    assert doc["costos"]["commission_pct"] == 0.04
    assert doc["medido_en"]["desde"] == "2019-09-10"


def test_la_estrategia_sobrevive_la_ida_y_la_vuelta(spec):
    """El runner usa el MISMO motor, así que el spec tiene que reconstruirse igual."""
    doc = json.loads(export_bingx(spec, symbol_source="BTCUSDT"))
    assert StrategySpec.from_dict(doc["estrategia"]).to_dict() == spec.to_dict()


# ------------------------------------------------------------ la validación

def test_un_archivo_valido_se_lee(spec):
    doc = leer_bingx(export_bingx(spec, symbol_source="BTCUSDT"))
    assert doc["formato"] == FORMATO


def test_un_json_de_otro_programa_se_rechaza():
    with pytest.raises(ValueError, match="no lo exportó"):
        leer_bingx('{"algo": 1}')


def test_un_archivo_que_no_es_json_se_rechaza():
    with pytest.raises(ValueError, match="JSON"):
        leer_bingx("esto no es json")


def test_una_version_mas_nueva_se_niega_a_operar(spec):
    """Un runner viejo con un archivo nuevo NO interpreta lo que entienda.

    Ejecutar la mitad de una estrategia —las entradas sí y un filtro nuevo no—
    es peor que no ejecutarla: opera de verdad y no es lo que se midió.
    """
    doc = json.loads(export_bingx(spec, symbol_source="BTCUSDT"))
    doc["version"] = VERSION + 1
    with pytest.raises(ValueError, match="más nueva"):
        leer_bingx(json.dumps(doc))


def test_sin_simbolo_no_se_opera(spec):
    doc = json.loads(export_bingx(spec, symbol_source="BTCUSDT"))
    doc["ejecucion"]["simbolo"] = ""
    with pytest.raises(ValueError, match="símbolo"):
        leer_bingx(json.dumps(doc))


def test_sin_estrategia_no_se_opera(spec):
    doc = json.loads(export_bingx(spec, symbol_source="BTCUSDT"))
    doc["estrategia"] = {}
    with pytest.raises(ValueError, match="estrategia"):
        leer_bingx(json.dumps(doc))


# ------------------------------------------------- de punta a punta, al disco
#
# Lo de arriba prueba el renderizado. Esto prueba lo otro: que apretar el botón
# produzca un archivo. Es la distinción que ya nos costó una vez —la ventana
# nativa cancelaba las descargas del navegador y el botón no hacía nada, sin
# error ni aviso, mientras todos los tests del renderizado pasaban.

from pathlib import Path                                          # noqa: E402

from fastapi.testclient import TestClient                         # noqa: E402

from botiquant.api.app import create_app                          # noqa: E402


@pytest.fixture()
def salida(tmp_path, monkeypatch) -> Path:
    destino = tmp_path / "salida"
    monkeypatch.setenv("BQ_EXPORTS", str(destino))
    return destino


@pytest.fixture()
def client(tmp_path):
    app = create_app(workdir=tmp_path / "ws")
    with TestClient(app) as c:
        c.post("/api/datasets/sample", json={"symbol": "EURUSD", "bars": 900})
        yield c


def _spec_api() -> dict:
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return {"name": "bot", "direction": "long",
            "entry_long": [{"left": ema(15), "op": "cross_above", "right": ema(60)}],
            "risk": {"stop_type": "atr", "stop_value": 2,
                     "target_type": "atr", "target_value": 3}}


def _ds_id(client) -> str:
    return client.get("/api/datasets").json()[0]["id"]


def test_el_endpoint_devuelve_un_archivo_de_enlace_valido(client):
    r = client.post("/api/export/bingx", json={
        "spec": _spec_api(), "name": "BQ Bot", "dataset_id": _ds_id(client)})
    assert r.status_code == 200, r.text
    assert ".bqbot" in r.headers.get("content-disposition", "")
    doc = leer_bingx(r.text)          # se valida con el mismo lector del runner
    assert doc["formato"] == FORMATO


def test_sin_instrumento_se_niega_a_exportar(client):
    """Un archivo sin símbolo es un archivo que el runner va a rechazar.

    Entregarlo igual traslada el error al momento de querer operar, que es el
    peor momento posible para descubrirlo. Se falla acá, con el usuario
    mirando la pantalla de la que salió.
    """
    r = client.post("/api/export/bingx", json={"spec": _spec_api(), "name": "BQ Bot"})
    assert r.status_code == 400
    assert "instrumento" in r.json()["detail"]


def test_el_bot_termina_siendo_un_archivo(client, salida):
    r = client.post("/api/export/bingx/archivo",
                    json={"spec": _spec_api(), "name": "BQ_Bot",
                          "dataset_id": _ds_id(client)})
    assert r.status_code == 200, r.text
    destino = Path(r.json()["ruta"])
    assert destino.exists()
    assert destino.name == "BQ_Bot.bqbot"
    leer_bingx(destino.read_text(encoding="utf-8"))


def test_el_endpoint_no_vuelca_lo_que_le_manden(client):
    """Encontró un agujero de verdad la primera vez que corrió.

    El endpoint copiaba `settings` entero adentro del archivo, así que
    cualquier cosa que el cliente metiera ahí terminaba en un archivo pensado
    para mandarse por mail. Ahora los costos se copian campo por campo.
    """
    r = client.post("/api/export/bingx", json={
        "spec": _spec_api(), "name": "BQ Bot", "dataset_id": _ds_id(client),
        "settings": {"commission_pct": 0.04, "api_key": "NO_DEBE_VIAJAR"}})
    assert r.status_code == 200, r.text
    assert "NO_DEBE_VIAJAR" not in r.text
    assert json.loads(r.text)["costos"]["commission_pct"] == 0.04
