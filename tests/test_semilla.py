"""Instrumentos que vienen con la aplicación.

Lo que más importa acá es CUÁNDO no se cargan: sembrar de más le devuelve al
usuario instrumentos que borró a propósito y le duplica los que ya bajó.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from botiquant.data import semilla


@pytest.fixture()
def paquete(tmp_path, monkeypatch):
    """Finge un paquete con dos instrumentos incluidos.

    La suite apaga el sembrado globalmente para que los demás tests partan de
    un workspace vacío; acá hay que volver a encenderlo o no se prueba nada.
    """
    monkeypatch.delenv("BQ_SIN_SEMILLA", raising=False)
    carpeta = tmp_path / "recursos" / semilla.CARPETA
    carpeta.mkdir(parents=True)
    idx = pd.date_range("2020-01-01", periods=600, freq="1h")
    for nombre in ("uno", "dos"):
        pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05,
                      "volume": 10.0}, index=idx).to_csv(
            carpeta / f"{nombre}.csv", index_label="time")
    (carpeta / semilla.MANIFIESTO).write_text(json.dumps([
        {"archivo": "uno.csv", "nombre": "UNO H1", "source": "semilla"},
        {"archivo": "dos.csv", "nombre": "DOS H1", "source": "semilla"},
    ]), encoding="utf-8")
    monkeypatch.setattr(semilla, "raiz_recursos", lambda: tmp_path / "recursos")
    return carpeta


class _StoreFalso:
    def __init__(self):
        self.puestos = []
        self.fundings = {}

    def add(self, nombre, df, source="upload", user_id=None):
        self.puestos.append((nombre, len(df), source))
        return {"id": str(len(self.puestos))}

    def guardar_funding(self, ds_id, serie):
        self.fundings[ds_id] = len(serie)


def test_an_empty_workspace_gets_the_bundled_instruments(paquete):
    """Una aplicación de backtesting que abre sin un solo instrumento no se
    puede ni probar."""
    store = _StoreFalso()

    puestos = semilla.sembrar(store, existentes=[])

    assert puestos == 2
    assert [p[0] for p in store.puestos] == ["UNO H1", "DOS H1"]
    assert all(p[1] == 600 for p in store.puestos)


def test_nothing_is_seeded_when_the_user_already_has_data(paquete):
    """LO IMPORTANTE. Si sembrara siempre, le devolvería al usuario los
    instrumentos que borró y le duplicaría los que ya bajó en M1, dejándole dos
    entradas del mismo mercado sin saber cuál está usando."""
    store = _StoreFalso()

    assert semilla.sembrar(store, existentes=[{"source": "semilla"}]) == 0
    assert store.puestos == []


def test_a_workspace_with_only_cfds_gets_the_perpetuals(paquete):
    """Quien venía de la versión con sólo CFDs abría "Cripto" sin un solo
    perpetuo: el selector volvía a SP500 y la sección parecía no hacer nada.
    Se siembra por sección, y la que ya tiene datos se deja como está."""
    (paquete / semilla.MANIFIESTO).write_text(json.dumps([
        {"archivo": "uno.csv", "nombre": "UNO H1", "source": "semilla"},
        {"archivo": "dos.csv", "nombre": "DOSUSDT H1", "source": "binance"},
    ]), encoding="utf-8")
    store = _StoreFalso()

    puestos = semilla.sembrar(store, existentes=[{"source": "dukascopy"}])

    assert puestos == 1
    assert [p[0] for p in store.puestos] == ["DOSUSDT H1"]


def test_a_perpetual_already_downloaded_blocks_the_crypto_seed(paquete):
    """Quien ya bajó un perpetuo en M1 no recibe el mismo mercado en H1."""
    (paquete / semilla.MANIFIESTO).write_text(json.dumps([
        {"archivo": "uno.csv", "nombre": "UNO H1", "source": "semilla"},
        {"archivo": "dos.csv", "nombre": "DOSUSDT H1", "source": "binance"},
    ]), encoding="utf-8")
    store = _StoreFalso()

    assert semilla.sembrar(store, existentes=[{"source": "binance"}]) == 1
    assert [p[0] for p in store.puestos] == ["UNO H1"]


def test_an_uploaded_csv_does_not_count_as_data_of_either_world(paquete):
    store = _StoreFalso()

    assert semilla.sembrar(store, existentes=[{"source": "upload"}]) == 2


def test_a_build_without_bundled_data_still_starts(tmp_path, monkeypatch):
    """El servidor web se empaqueta sin instrumentos: no puede fallar al
    arrancar por eso."""
    monkeypatch.setattr(semilla, "raiz_recursos", lambda: tmp_path)
    store = _StoreFalso()

    assert semilla.disponible() == []
    assert semilla.sembrar(store, existentes=[]) == 0


def test_a_broken_file_does_not_block_startup(paquete):
    """Un CSV corrupto no puede impedir que la aplicación abra: siempre queda
    la opción de descargar el instrumento."""
    (paquete / "uno.csv").write_text("esto no es un csv de velas", encoding="utf-8")
    store = _StoreFalso()

    puestos = semilla.sembrar(store, existentes=[])

    assert puestos == 1
    assert [p[0] for p in store.puestos] == ["DOS H1"]


def test_a_missing_file_listed_in_the_manifest_is_skipped(paquete):
    (paquete / "dos.csv").unlink()
    store = _StoreFalso()

    assert semilla.sembrar(store, existentes=[]) == 1


def test_a_corrupt_manifest_is_not_fatal(paquete):
    (paquete / semilla.MANIFIESTO).write_text("{ roto", encoding="utf-8")
    assert semilla.disponible() == []


def test_the_real_build_ships_both_worlds():
    """Contra la semilla de verdad: si alguien la borra o la rompe, la
    aplicación empaquetada volvería a abrir vacía.

    Eran cuatro CFD; ahora van también los perpetuos: una aplicación que
    puede operar un exchange en demo pero abre sin un solo perpetuo hace
    que el primer encendido cueste una descarga. Los perpetuos llevan
    fuente "binance" —el filtro de operables la exige— y su archivo de
    funding."""
    entradas = semilla.disponible()
    if not entradas:
        pytest.skip("este árbol no tiene la semilla generada")

    nombres = " ".join(e["nombre"].upper() for e in entradas)
    for esperado in ("EURUSD", "SP500", "XAUUSD", "BTCUSD"):
        assert esperado in nombres, f"falta el CFD {esperado}"

    perpetuos = [e for e in entradas if e.get("source") == "binance"]
    if perpetuos:      # un árbol con la semilla vieja no es un error
        assert len(perpetuos) >= 10, "la tanda de perpetuos quedó a medias"
        sin_funding = [e["nombre"] for e in perpetuos if not e.get("funding")]
        assert not sin_funding, (
            f"perpetuos sembrados sin funding: {sin_funding}. Minarían "
            f"con números mejores que los reales.")


def test_a_fresh_install_opens_with_instruments(tmp_path, monkeypatch):
    """El camino completo, con el sembrado encendido.

    La suite lo apaga globalmente para que los demás tests partan de un
    workspace vacío, así que si nadie lo volviera a encender acá, el sembrado
    quedaría sin ninguna prueba de punta a punta.
    """
    from fastapi.testclient import TestClient

    import botiquant.api.app as appmod

    if not semilla.disponible():
        pytest.skip("este árbol no tiene la semilla generada")

    monkeypatch.delenv("BQ_SIN_SEMILLA", raising=False)
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)

    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        datos = c.get("/api/datasets").json()

    # SE CUENTA CONTRA EL MANIFIESTO Y NO CONTRA UN NUMERO CLAVADO.
    # Eran cuatro CFD; ahora van tambien los perpetuos, y agregar uno no
    # puede romper el unico test que prueba el arranque de punta a punta.
    # Lo que importa no es cuantos son sino que entren TODOS los que el
    # paquete dice traer.
    assert len(datos) == len(semilla.disponible()), (
        "la aplicación no levantó todo lo que el paquete trae")
    assert datos, "la aplicación abriría vacía"
    # Los perpetuos mas nuevos cotizan desde 2023, asi que el piso de
    # historia es mas bajo que el de los CFD: lo que se defiende es que
    # ninguno entre recortado, no que todos tengan veinte años.
    assert all(d["rows"] > 25_000 for d in datos), "faltan años de historia"


def test_a_second_start_does_not_duplicate(tmp_path, monkeypatch):
    """Abrir la aplicación dos veces no puede dejar ocho instrumentos."""
    from fastapi.testclient import TestClient

    import botiquant.api.app as appmod

    if not semilla.disponible():
        pytest.skip("este árbol no tiene la semilla generada")

    monkeypatch.delenv("BQ_SIN_SEMILLA", raising=False)
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)

    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        primero = len(c.get("/api/datasets").json())
    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        segundo = len(c.get("/api/datasets").json())

    assert primero == segundo == len(semilla.disponible())


def test_un_perpetuo_sembrado_lleva_su_funding(paquete, tmp_path):
    """SIN ESTO, UN INSTRUMENTO SEMBRADO MINARIA CON NUMEROS MEJORES QUE LOS
    REALES: el motor cobra el funding sobre la posición abierta, y un perpetuo
    sin su archivo de tasas es un perpetuo gratis. Además los bloques de
    funding quedarían descartados con aviso, en el único lugar donde el
    usuario no hizo nada raro.
    """
    idx = pd.date_range("2020-01-01", periods=100, freq="8h")
    pd.DataFrame({"funding": 0.0001}, index=idx).to_csv(
        paquete / "uno.funding.csv", index_label="time")
    manifiesto = json.loads((paquete / semilla.MANIFIESTO).read_text())
    manifiesto[0]["funding"] = "uno.funding.csv"
    manifiesto[0]["source"] = "binance"
    (paquete / semilla.MANIFIESTO).write_text(json.dumps(manifiesto))

    st = _StoreFalso()
    assert semilla.sembrar(st, existentes=[]) == 2
    # el primero lleva funding y fuente binance; el segundo no tiene y no pasa nada
    assert st.fundings == {"1": 100}
    assert st.puestos[0][2] == "binance", (
        "la fuente tiene que ser binance: el filtro de operables la exige")


def test_un_funding_roto_no_impide_sembrar_las_velas(paquete):
    (paquete / "uno.funding.csv").write_text("basura sin columnas")
    manifiesto = json.loads((paquete / semilla.MANIFIESTO).read_text())
    manifiesto[0]["funding"] = "uno.funding.csv"
    (paquete / semilla.MANIFIESTO).write_text(json.dumps(manifiesto))
    st = _StoreFalso()
    assert semilla.sembrar(st, existentes=[]) == 2
    assert st.fundings == {}
