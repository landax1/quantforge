"""Que los dos bitcoins se puedan distinguir.

Desde que existe el perpetuo hay DOS instrumentos de bitcoin en el catálogo, y
son cosas distintas: uno es un CFD que se opera por MetaTrader y paga spread,
el otro es un perpetuo que se opera en un exchange y paga comisión y funding.

`BTCUSD` y `BTCUSDT` a un carácter de distancia no le dicen eso a nadie, y en
el código `crypto` y `cripto` a una letra de distancia era peor: un typo que
compila y que manda el instrumento a la familia equivocada.
"""

from __future__ import annotations

from pathlib import Path

from botiquant.data.catalog import CATALOG

UI = Path(__file__).resolve().parents[1] / "ui"


def _por_label(label: str) -> dict:
    return [e for e in CATALOG if e["label"] == label][0]


def test_las_dos_categorias_de_cripto_no_se_parecen_a_una_letra():
    """`crypto` y `cripto` era un typo que compila.

    Escribir uno por el otro manda el instrumento a la familia equivocada sin
    ningún error: aparece en la lista, con otro ícono y otro rótulo.
    """
    cats = {e["category"] for e in CATALOG}
    assert "cripto" not in cats, "volvió el nombre que se confunde con `crypto`"
    assert {"crypto", "perpetuos"} <= cats


def test_el_cfd_de_bitcoin_no_reclama_el_nombre_del_perpetuo():
    """Estaba de cuando el perpetuo no existía: buscar BTCUSDT devolvía el CFD."""
    assert "BTCUSDT" not in _por_label("BTCUSD").get("aliases", [])


def test_cada_bitcoin_dice_para_donde_es():
    """El nombre corto no alcanza; el largo tiene que resolver la duda."""
    assert "MetaTrader" in _por_label("BTCUSD")["full_name"]
    assert "exchange" in _por_label("BTCUSDT")["full_name"]


def test_toda_categoria_tiene_su_rotulo_y_su_icono():
    """Una categoría sin rótulo se dibuja en crudo; sin ícono cae en `_otro`."""
    i18n = (UI / "i18n.js").read_text(encoding="utf-8")
    app = (UI / "app.js").read_text(encoding="utf-8")
    for cat in sorted({e["category"] for e in CATALOG}):
        assert f'"cat.{cat}"' in i18n, f"falta el rótulo de {cat}"
        assert f"\n  {cat}: {{ icono:" in app, f"falta el ícono de {cat}"


def test_cada_instrumento_tiene_su_descripcion():
    """La tarjeta muestra `t("inst." + key)`. Sin esa clave se dibuja el nombre
    de la clave en crudo —"inst.bund"— en el lugar donde va la explicación.

    No lo cubría nada: al agregar bund, wti y gas, la prueba de arriba pasaba
    —tenían rótulo de categoría e ícono— y las tres tarjetas salían con el
    texto roto.
    """
    i18n = (UI / "i18n.js").read_text(encoding="utf-8")
    faltan = [e["key"] for e in CATALOG if f'"inst.{e["key"]}"' not in i18n]
    assert not faltan, f"sin descripción: {faltan}"


def test_toda_categoria_esta_en_la_lista_de_FAMILIAS():
    """`FAMILIAS` fija qué familias se dibujan y en qué orden. Una categoría
    que no esté cae en el cajón «Otros»: se ve, pero sin su nombre y sin el
    subtítulo que explica de qué se trata.
    """
    app = (UI / "app.js").read_text(encoding="utf-8")
    bloque = app[app.index("const FAMILIAS = () => ["):]
    bloque = bloque[:bloque.index("];")]
    faltan = [c for c in sorted({e["category"] for e in CATALOG})
              if f'cat: "{c}"' not in bloque]
    assert not faltan, f"caen en «Otros»: {faltan}"


def test_cada_familia_explica_de_que_se_trata():
    """El subtítulo es donde se dice qué se paga en esa familia —spread contra
    comisión y funding— que es la diferencia que hace elegir mal."""
    i18n = (UI / "i18n.js").read_text(encoding="utf-8")
    faltan = [c for c in sorted({e["category"] for e in CATALOG})
              if f'"famsub.{c}"' not in i18n]
    assert not faltan, f"familias sin subtítulo: {faltan}"


# ---------------------------------------------------- el emparejamiento

def _cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from botiquant.api.app import create_app
    return TestClient(create_app(workdir=tmp_path / "ws"))


def _velas(n=120) -> bytes:
    """El CSV como lo espera la subida.

    `index_label="time"` NO es cosmético: sin nombre de columna la subida
    contesta 400 «No time/date column found», la prueba se queda sin datasets
    y la aserción «el CFD no se quedó con el perpetuo» pasa porque no hay
    ningún perpetuo. Encontrado así, pasando en verde.
    """
    import pandas as pd
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    base = pd.Series(range(n), dtype=float) + 100.0
    df = pd.DataFrame({"open": base.values, "high": base.values + 1,
                       "low": base.values - 1, "close": base.values,
                       "volume": 1.0}, index=idx)
    return df.to_csv(index_label="time").encode()


def _catalogo(c):
    return {x["key"]: x for x in c.get("/api/catalog").json()}


def test_el_CFD_de_bitcoin_no_se_queda_con_los_datos_del_perpetuo(tmp_path,
                                                                  monkeypatch):
    """VISTO EN LA APLICACIÓN, no deducido: la tarjeta del CFD mostraba las
    velas del perpetuo —mismo número, mismas fechas— y `/api/catalog` daba el
    mismo `dataset_id` para los dos.

    El emparejamiento buscaba por SUBCADENA, y "btcusd" está adentro de
    "btcusdt": el CFD se quedaba con el primer dataset que lo contuviera.

    Lo que costaba: apretar «buscar en éste» en la tarjeta del CFD minaba sobre
    los datos del perpetuo —otro instrumento, otra historia— con los costos del
    CFD. Sin fallar nada.
    """
    with _cliente(tmp_path, monkeypatch) as c:
        from botiquant.api import app as mod
        # se carga SÓLO el perpetuo, que es como estaba la máquina donde apareció
        c.post("/api/datasets/upload", files={
            "file": ("BTCUSDT M1.csv", _velas(), "text/csv")})
        nombres = [d["name"] for d in c.get("/api/datasets").json()]
        assert any("BTCUSDT" in n for n in nombres), (
            "sin el perpetuo cargado esta prueba no prueba nada")
        cat = _catalogo(c)
        perpetuo = cat["btcusdt"]["dataset_id"]
        assert perpetuo, "el perpetuo tendría que haberse enganchado al suyo"
        assert cat["btcusd"]["dataset_id"] != perpetuo, (
            "el CFD se quedó con el dataset del perpetuo")


def test_cada_bitcoin_se_queda_con_el_suyo(tmp_path, monkeypatch):
    """La contracara: arreglar por subcadena no puede dejar sin datos al que
    sí los tiene."""
    with _cliente(tmp_path, monkeypatch) as c:
        for nombre in ("BTCUSDT M1.csv", "BTCUSD M1 (Dukascopy).csv"):
            c.post("/api/datasets/upload", files={
                "file": (nombre, _velas(), "text/csv")})
        cat = _catalogo(c)
        ids = {k: cat[k]["dataset_id"] for k in ("btcusd", "btcusdt")}
        assert all(ids.values()), f"alguno quedó sin datos: {ids}"
        assert ids["btcusd"] != ids["btcusdt"], "los dos apuntan al mismo"


# --------------------------------------- lo que la vitrina no ofrece

def test_los_perpetuos_estan_ocultos_pero_NO_borrados():
    """El producto apunta hoy a un portafolio de EA para MetaTrader, y en esa
    vitrina un CFD de Bitcoin al lado de un perpetuo de Bitcoin se lee como el
    mismo instrumento repetido.

    Ocultos y no borrados, y la diferencia es la que importa: de la entrada del
    catálogo salen los COSTOS del instrumento. Quien ya bajó el perpetuo tiene
    datos y estrategias encima; sin su entrada, minaría con el spread de otro
    sin que nada fallara.
    """
    from botiquant.data.catalog import BY_KEY
    assert BY_KEY["btcusdt"].get("oculto") is True
    assert BY_KEY["ethusdt"].get("oculto") is True
    # siguen enteros: símbolo, costos y todo lo que hace falta para operarlos
    for k in ("btcusdt", "ethusdt"):
        assert BY_KEY[k]["commission_pct"] > 0
        assert BY_KEY[k]["binance"]


def test_los_que_se_pueden_bajar_de_verdad_estan_a_la_vista():
    """Y los que no, escondidos. Un botón «Descargar» que siempre falla es
    peor que no ofrecer el instrumento.

    Gas, WTI y Bund están ocultos porque hoy no hay de dónde bajarlos:
    Dukascopy nos rechaza —174 días de 2.695 del Bund, 197 de 3.896 del WTI,
    127 de 3.650 del gas, y las tres descargas terminaron sin nada— y
    MetaTrader no tiene ni energía ni bonos.

    Los cuatro que sí se pueden bajar tienen que seguir visibles: si alguno se
    marca por error, desaparece de la pantalla sin que nada avise.
    """
    from botiquant.data.catalog import BY_KEY
    for k in ("sp500", "eurusd", "xauusd", "btcusd"):
        assert not BY_KEY[k].get("oculto"), f"{k} desapareció de la pantalla"
    for k in ("gas", "wti", "bund"):
        assert BY_KEY[k].get("oculto") is True, (
            f"{k} se ofrece y hoy no se puede bajar")


def test_la_pantalla_muestra_igual_lo_que_ya_esta_bajado():
    """Esconderle a alguien un instrumento que tiene cargado, con estrategias
    encima, sería hacerlo desaparecer sin explicación."""
    app = (UI / "app.js").read_text(encoding="utf-8")
    assert "!c.oculto || c.dataset_id" in app


# ------------------------------------- los dos caminos del producto

def test_el_portafolio_no_esta_atado_al_modo_avanzado():
    """Son dos cosas distintas y estaban en la misma bolsa.

    `AVANZADO` esconde HERRAMIENTAS para quien ya sabe qué mirar —walk-forward,
    la columna Estado—. El portafolio no es eso: es uno de los dos OBJETIVOS
    del producto. Alguien puede venir a buscar una estrategia sola o a armar un
    conjunto de EA para una cuenta, y el segundo camino no es una versión
    avanzada del primero.

    Escondido, el conjunto sólo se podía armar exportando de a uno — y ahí cada
    EA se cree dueño del 100% de la cuenta.
    """
    app = (UI / "app.js").read_text(encoding="utf-8")
    assert "const PORTAFOLIO = true;" in app
    # las casillas y la barra tienen que colgar de PORTAFOLIO, no de AVANZADO
    assert 'PORTAFOLIO ? `<td class="tick"><input type="checkbox" data-pf=' in app
    assert "barra.hidden = !PORTAFOLIO" in app
