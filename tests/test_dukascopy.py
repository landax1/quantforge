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


def test_uno_que_no_esta_en_la_tabla_ya_no_cae_a_un_default():
    """Antes gbpchf devolvia 1e5 «por las dudas». Medido despues: de siete
    instrumentos probados fuera de la tabla, SEIS necesitaban 1e3 y solo
    GBPUSD 1e5 — el default acertaba una de cada siete veces, y las otras seis
    bajaban con los precios divididos por cien sin que nada fallara.

    Ahora se consulta, y si no se puede saber se levanta. Ver
    tests/test_escala_dukascopy.py.
    """
    with pytest.raises(dk.DukascopyError):
        dk.escala_de("gbpchf")


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
    monkeypatch.setattr(dk.time, "sleep", lambda *_: None)

    # "siguió rechazando" y no "rechazó": ahora hay una segunda pasada de a uno
    # antes de rendirse, y el mensaje lo dice para que quien lo lea sepa que
    # reintentar en el momento no va a cambiar nada.
    with pytest.raises(dk.DukascopyError, match="siguió rechazando"):
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


# ------------------------------------------- pedir un timeframe mas fino
def test_asking_for_a_finer_timeframe_is_refused():
    """Agrupar velas sólo funciona hacia arriba. Pedir 15 minutos sobre velas
    horarias devolvía las MISMAS velas horarias con la etiqueta equivocada: la
    estrategia se buscaba en H1, se exportaba como M15 y en MetaTrader corría
    sobre un gráfico donde nunca se probó."""
    import pandas as pd

    from botiquant.data.loader import resample_ohlcv

    idx = pd.date_range("2020-01-01", periods=48, freq="1h")
    h1 = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.5, "volume": 10.0}, index=idx)

    # los que la interfaz realmente ofrece; "1m" no está en la lista y da otro
    # error, también correcto, pero por un motivo distinto
    for fino in ("5m", "15m", "30m"):
        with pytest.raises(ValueError, match="No se puede"):
            resample_ohlcv(h1, fino)


def test_grouping_upwards_still_works():
    """El caso normal no puede quedar bloqueado por la validación."""
    import pandas as pd

    from botiquant.data.loader import resample_ohlcv

    idx = pd.date_range("2020-01-01", periods=48, freq="1h")
    h1 = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.5, "volume": 10.0}, index=idx)

    assert len(resample_ohlcv(h1, "4h")) == 12
    assert len(resample_ohlcv(h1, "1d")) == 2
    assert len(resample_ohlcv(h1, "1h")) == 48


def test_m1_data_can_still_be_asked_for_anything():
    import pandas as pd

    from botiquant.data.loader import resample_ohlcv

    idx = pd.date_range("2020-01-01", periods=60 * 8, freq="1min")
    m1 = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.5, "volume": 10.0}, index=idx)

    assert len(resample_ohlcv(m1, "15m")) == 32
    assert len(resample_ohlcv(m1, "1h")) == 8


# ------------------------------- la segunda pasada sobre los rechazados

def _cliente_que_falla_las_primeras(monkeypatch, cuantas_fallan):
    """Falla los primeros `cuantas_fallan` pedidos y después contesta bien.

    Reproduce lo que hace Dukascopy con un tropiezo de límite: unos cuantos
    días rechazados en la tanda paralela que sí contestan pedidos de a uno.
    """
    estado = {"n": 0}
    velas = _archivo([(0, 107324, 107305, 107305, 107324, 66.5)])

    class _R:
        def __init__(self, code, contenido=b""):
            self.status_code = code
            self.content = contenido

    class _C:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url):
            estado["n"] += 1
            if estado["n"] <= cuantas_fallan:
                return _R(503)
            return _R(200, velas)

    monkeypatch.setattr(dk.httpx, "Client", _C)
    monkeypatch.setattr(dk.time, "sleep", lambda *_: None)
    return estado


def test_los_dias_rechazados_se_reintentan_de_a_uno(monkeypatch):
    """Lo que convierte un tropiezo del 5% en perder el 95% ya bajado.

    MEDIDO bajando los tres instrumentos nuevos: Bund 174 días rechazados de
    2.695, WTI 197 de 3.896, gas 127 de 3.650 —entre 3% y 6%— y las tres
    descargas terminaron sin dejar nada después de diez minutos cada una.
    Con eso, agregar un instrumento al catálogo no funcionaba para nadie.
    """
    # cada día se pide con REINTENTOS internos, así que se hacen fallar los
    # primeros pedidos enteros de un par de días
    _cliente_que_falla_las_primeras(monkeypatch, dk.REINTENTOS * 2)
    df = dk.descargar("eurusd", "2023-01-02", "2023-01-06")
    assert not df.empty, "la segunda pasada tendría que haber recuperado los días"


def test_si_siguen_fallando_despues_de_la_segunda_pasada_aborta(monkeypatch):
    """La regla que NO cambia: nada a medias.

    Un histórico con semanas faltantes no da error en ningún lado — da un
    backtest con menos operaciones y otras métricas, y nadie se entera.
    """
    _cliente_que_falla_las_primeras(monkeypatch, 10_000)
    with pytest.raises(dk.DukascopyError, match="siguió rechazando"):
        dk.descargar("eurusd", "2023-01-02", "2023-01-06")


def test_la_segunda_pasada_va_espaciada(monkeypatch):
    """De a uno y con espera: si lo que sobra son pedidos, repetirlos rápido
    choca contra el mismo límite."""
    assert dk.ESPERA_SEGUNDA_PASADA >= 1.0
