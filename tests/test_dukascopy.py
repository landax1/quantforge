"""Descarga de velas desde Dukascopy, sin Node.

Casi todo se prueba sin red: la red haría los tests lentos y dependientes de
que un servidor ajeno esté de buen humor. Lo que se prueba es el formato y las
decisiones, que es donde estaban los errores.
"""

from __future__ import annotations

import datetime as dt
import lzma
import struct

import pytest

from botiquant.data import dukascopy as dk


def _archivo(velas: list[tuple[int, int, int, int, int, float]]) -> bytes:
    """Arma un .bi5 como el que sirve Dukascopy."""
    crudo = b"".join(dk._REGISTRO.pack(*v) for v in velas)
    return lzma.compress(crudo, format=lzma.FORMAT_ALONE)


# ------------------------------------------------------------------- la URL
def test_the_month_is_zero_based():
    """Dukascopy numera enero como 00. Usar el mes normal baja el mes anterior
    sin que nada falle: los datos llegan, con las fechas corridas."""
    url = dk._url("eurusd", dt.date(2023, 1, 3))
    assert "/2023/00/03/" in url
    assert "/2023/01/03/" not in url

    assert "/2023/11/31/" in dk._url("eurusd", dt.date(2023, 12, 31))


def test_the_symbol_goes_uppercase():
    assert "/EURUSD/" in dk._url("eurusd", dt.date(2023, 1, 3))


# --------------------------------------------------------------- el formato
def test_prices_are_scaled_integers_not_floats():
    """Leerlos como float da ceros — fue el primer resultado al probarlo, y un
    dataset de ceros no rompe nada hasta que el backtest da cualquier cosa."""
    velas = [(0, 107324, 107305, 107305, 107324, 66.5)]
    filas = dk._filas(_archivo(velas), dt.date(2023, 1, 10), 1e5)

    assert len(filas) == 1
    t, o, h, l, c, v = filas[0]
    assert (o, h, l, c) == (1.07324, 1.07324, 1.07305, 1.07305)
    assert t == dt.datetime(2023, 1, 10, 0, 0)


def test_each_instrument_has_its_own_scale():
    """107896 es 1,07896 en un par de divisas y 107,896 en un índice. No se
    puede deducir del número."""
    assert dk.escala_de("eurusd") == 1e5
    assert dk.escala_de("usa500idxusd") == 1e3
    assert dk.escala_de("xauusd") == 1e3
    assert dk.escala_de("btcusd") == 1e1
    assert dk.escala_de("gbpchf") == dk.ESCALA_POR_DEFECTO


def test_the_minute_offset_becomes_a_timestamp():
    velas = [(0, 100, 100, 100, 100, 1.0), (60, 100, 100, 100, 100, 1.0),
             (86340, 100, 100, 100, 100, 1.0)]
    filas = dk._filas(_archivo(velas), dt.date(2023, 5, 4), 1e2)

    assert [f[0].strftime("%H:%M") for f in filas] == ["00:00", "00:01", "23:59"]


def test_minutes_without_a_quote_are_dropped():
    """Los minutos sin cotización vienen en cero. Dejarlos mete precios de cero
    en el medio del histórico."""
    velas = [(0, 107324, 107305, 107305, 107324, 66.5),
             (60, 0, 0, 0, 0, 0.0)]
    assert len(dk._filas(_archivo(velas), dt.date(2023, 1, 10), 1e5)) == 1


def test_a_corrupt_file_does_not_explode():
    assert dk._filas(b"esto no es lzma", dt.date(2023, 1, 10), 1e5) == []


# ------------------------------------------------------------ fines de semana
def test_weekends_are_skipped():
    """Sin esto se gastan miles de pedidos en días que nunca tienen archivo."""
    dias = list(dk._dias(dt.date(2023, 1, 2), dt.date(2023, 1, 15)))
    assert all(d.weekday() < 5 for d in dias)
    assert len(dias) == 10


# ---------------------------------------------- fallar vs. no haber datos
class _RespuestaFalsa:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content


class _ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = 0

    def get(self, url):
        self.pedidos += 1
        return self.respuestas[min(self.pedidos - 1, len(self.respuestas) - 1)]


def test_a_holiday_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(dk.time, "sleep", lambda s: None)
    estado, _ = dk._traer_dia(_ClienteFalso([_RespuestaFalsa(404)]), "eurusd",
                              dt.date(2023, 1, 2))
    assert estado == "sin_datos"


def test_a_503_is_a_failure_and_gets_retried(monkeypatch):
    """Dukascopy limita por IP. Confundir eso con un feriado deja huecos que
    nadie ve."""
    monkeypatch.setattr(dk.time, "sleep", lambda s: None)
    cliente = _ClienteFalso([_RespuestaFalsa(503)])

    estado, _ = dk._traer_dia(cliente, "eurusd", dt.date(2023, 1, 2))

    assert estado == "fallo"
    assert cliente.pedidos == dk.REINTENTOS, "no reintentó"


def test_a_503_that_recovers_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(dk.time, "sleep", lambda s: None)
    cliente = _ClienteFalso([_RespuestaFalsa(503), _RespuestaFalsa(200, b"x")])

    estado, contenido = dk._traer_dia(cliente, "eurusd", dt.date(2023, 1, 2))

    assert estado == "ok"
    assert contenido == b"x"


def test_the_download_aborts_instead_of_returning_holes(monkeypatch):
    """LO IMPORTANTE. Un histórico al que le faltan semanas no da error en
    ningún lado: da un backtest con menos operaciones y otras métricas, y nadie
    se entera. Es peor que fallar, porque el resultado parece válido."""
    monkeypatch.setattr(dk, "_traer_dia",
                        lambda cliente, simbolo, dia: ("fallo", b""))

    with pytest.raises(dk.DukascopyError, match="rechazó"):
        dk.descargar("eurusd", "2023-01-02", "2023-01-06")


def test_an_all_holiday_range_says_so(monkeypatch):
    monkeypatch.setattr(dk, "_traer_dia",
                        lambda cliente, simbolo, dia: ("sin_datos", b""))

    with pytest.raises(dk.DukascopyError, match="no devolvió datos"):
        dk.descargar("eurusd", "2023-01-02", "2023-01-06")


def test_backwards_dates_are_refused():
    with pytest.raises(dk.DukascopyError, match="posterior"):
        dk.descargar("eurusd", "2023-06-01", "2023-01-01")


def test_duplicate_minutes_are_removed(monkeypatch):
    """Pasa en los bordes de horario de verano, y un índice con repetidos
    rompe el resampleo."""
    velas = [(0, 100, 100, 100, 100, 1.0)]
    monkeypatch.setattr(dk, "_traer_dia",
                        lambda cliente, simbolo, dia: ("ok", _archivo(velas)))
    monkeypatch.setattr(dk, "_dias",
                        lambda a, b: iter([dt.date(2023, 1, 2), dt.date(2023, 1, 2)]))

    df = dk.descargar("eurusd", "2023-01-02", "2023-01-02")

    assert len(df) == 1
    assert not df.index.duplicated().any()
