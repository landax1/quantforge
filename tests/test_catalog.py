"""Instrument catalogue: entries are well-formed and readiness is honest."""

from __future__ import annotations

import pandas as pd

from botiquant.data.catalog import BY_KEY, CATALOG, to_server_time


def test_catalog_entries_complete():
    keys = {c["key"] for c in CATALOG}
    assert {"sp500", "eurusd", "xauusd", "btcusd"} <= keys
    for c in CATALOG:
        assert c["slippage"] >= 0
        assert c["category"] and c["full_name"]
        # CADA FUENTE COBRA EN UN LUGAR DISTINTO, y esto lo comprueba por
        # separado en vez de pedirle spread a todos.
        #
        # Un CFD cobra en el SPREAD, en unidades de precio. Un perpetuo de
        # exchange tiene el libro ajustado y cobra COMISIÓN, en % del nocional:
        # ponerle también spread sería cobrarle dos veces, y dejarlo sin
        # comisión sería no cobrarle nada. Medido, ida y vuelta: el spread del
        # S&P son 0,0072% del precio y la comisión taker de un exchange 0,10%.
        fuente = c.get("fuente", "dukascopy")
        assert fuente in ("dukascopy", "binance"), (
            f"{c['key']}: fuente desconocida {fuente!r}")
        assert c[fuente], f"{c['key']}: no dice su símbolo en {fuente}"
        if fuente == "dukascopy":
            assert c["spread"] > 0, (
                f"{c['key']}: un CFD sin spread se minaría sin costo de cruce")
        else:
            assert c.get("commission_pct", 0) > 0, (
                f"{c['key']}: un perpetuo sin comisión se minaría gratis, y la "
                "comisión es TODO su costo de transacción")
            assert c["spread"] == 0, (
                f"{c['key']}: tiene spread Y comisión, o sea que paga dos veces")
        # La categoría es una CLAVE para la interfaz, no un rótulo. Si vuelve a
        # ser texto visible ("Índices"), la versión en inglés lo muestra en
        # español en medio de una pantalla en inglés.
        assert c["category"] == c["category"].lower(), (
            f"{c['key']}: la categoría volvió a ser un rótulo y no una clave")
        assert c["category"].isascii(), (
            f"{c['key']}: una clave con acentos no sirve de identificador")
        assert "note" not in c, (
            f"{c['key']}: el texto descriptivo vive en ui/i18n.js, no acá")
        assert BY_KEY[c["key"]] is c


def test_server_time_shift():
    idx = pd.date_range("2024-06-03 12:00", periods=3, freq="1min")  # UTC
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                      index=idx)
    out = to_server_time(df)
    # June => New York is UTC-4, +7 server offset => UTC+3
    assert out.index[0] == pd.Timestamp("2024-06-03 15:00")
    assert len(out) == len(df)


def test_sample_datasets_never_count_as_ready(client_with_sample):
    """A synthetic dataset named EURUSD must not mark the instrument downloaded."""
    catalog = client_with_sample.get("/api/catalog").json()
    eurusd = next(c for c in catalog if c["key"] == "eurusd")
    assert eurusd["dataset_id"] is None, "sample data must not be reported as real history"
