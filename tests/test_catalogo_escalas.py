"""Todo instrumento del catalogo tiene que poder averiguar su escala.

Esta prueba existe por la forma que tiene el error que evita. Agregar un
instrumento es agregar seis lineas a una lista; nada en esas seis lineas
sugiere que falte algo, y si falta el codigo de API el historico se baja con
los precios divididos por cien SIN QUE NADA FALLE: el backtest corre, las
metricas salen, y son de un mercado que no existe.

Medido: de siete instrumentos probados fuera de la tabla, SEIS necesitaban una
escala distinta a la que se hubiera adivinado.

Se pone roja en el momento en que alguien agrega el instrumento, que es el
unico momento en que el error es barato.
"""

from __future__ import annotations

from botiquant.data import catalog
from botiquant.data import dukascopy as dk


def _de_dukascopy():
    return [c for c in catalog.CATALOG
            if c.get("fuente", "dukascopy") == "dukascopy"]


def test_todos_pueden_averiguar_su_escala():
    sin = [c["key"] for c in _de_dukascopy()
           if c["dukascopy"] not in dk.ESCALA and not c.get("dukascopy_api")]
    assert not sin, (
        f"{sin} no tiene(n) `dukascopy_api`. Sin eso el historico se baja con "
        f"los precios mal por cien y ninguna prueba lo nota.")


def test_el_codigo_de_api_tiene_la_forma_que_espera_dukascopy():
    """``USD-JPY``, ``DEU.IDX-EUR``: en mayusculas y con guion. Un codigo mal
    escrito no da un error claro, da un 404 que termina en «no se pudo saber
    la escala» y parece un problema de conexion."""
    for c in _de_dukascopy():
        codigo = c.get("dukascopy_api", "")
        if codigo:
            assert codigo == codigo.upper(), c["key"]
            assert "-" in codigo, c["key"]


def test_la_descarga_le_pasa_el_codigo_al_modulo(monkeypatch):
    """Sin esto el campo existe, se completa, y no lo lee nadie."""
    visto = {}

    def _falso(simbolo, desde, hasta=None, progreso=None, codigo_api=""):
        visto["codigo"] = codigo_api
        import pandas as pd
        return pd.DataFrame(
            {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0],
             "volume": [1.0]},
            index=pd.DatetimeIndex(["2024-01-02"], name="timestamp"))

    monkeypatch.setattr(catalog, "descargar_dukascopy", _falso)
    monkeypatch.setitem(catalog.BY_KEY["sp500"], "dukascopy_api",
                        "USA500.IDX-USD")
    from pathlib import Path
    catalog.download("sp500", Path("."), "2024-01-02", "2024-01-03")
    assert visto["codigo"] == "USA500.IDX-USD"
