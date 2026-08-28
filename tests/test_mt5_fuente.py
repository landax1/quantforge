"""Bajar velas del MetaTrader del usuario.

Lo que se defiende acá es sobre todo EL RELOJ. Las velas de MetaTrader vienen
en la hora del servidor de donde salieron, y ese reloj no es el mismo para
todos: medido, MetaQuotes-Demo corre en UTC+3. Aplicarle el ajuste que se le
aplica a Dukascopy —que viene en UTC— las corre tres horas sin que falle nada:
la estrategia se mina en una franja y el EA opera en otra.
"""

from __future__ import annotations

import datetime as dt
import re
from types import SimpleNamespace

import numpy as np
import pytest

from botiquant.data import mt5 as fuente


class _FalsoMT5:
    """Lo mínimo del módulo de MetaTrader que usa el nuestro."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

    def __init__(self, *, tick_time=None, velas=None, simbolos=None,
                 cuenta=True, arranca=True):
        self._tick = tick_time
        self._velas = velas if velas is not None else []
        self._simbolos = simbolos or []
        self._cuenta = cuenta
        self._arranca = arranca
        self.pedidos = []

    def initialize(self):
        return self._arranca

    def last_error(self):
        return (-1, "falso")

    def account_info(self):
        if not self._cuenta:
            return None
        return SimpleNamespace(server="Falso-Demo", login=123456)

    def symbol_info_tick(self, simbolo):
        if self._tick is None:
            return None
        return SimpleNamespace(time=self._tick)

    def symbols_get(self):
        return self._simbolos

    def symbol_select(self, simbolo, on):
        return simbolo != "NO_EXISTE"

    def copy_rates_from_pos(self, simbolo, tf, desde, cuantas):
        self.pedidos.append((desde, cuantas))
        trozo = self._velas[desde:desde + cuantas]
        return np.array(trozo, dtype=[("time", "i8"), ("open", "f8"),
                                      ("high", "f8"), ("low", "f8"),
                                      ("close", "f8"), ("tick_volume", "i8")]) \
            if trozo else None


def _poner(monkeypatch, falso):
    monkeypatch.setattr(fuente, "_mt5", lambda: falso)
    return falso


# ============================================================== el reloj

def test_el_desfase_se_mide_contra_el_tick(monkeypatch):
    """UTC+3 es lo que devuelve MetaQuotes-Demo, el servidor que trae
    cualquier MetaTrader 5."""
    ahora = dt.datetime.now(dt.timezone.utc).timestamp()
    _poner(monkeypatch, _FalsoMT5(tick_time=ahora + 3 * 3600))
    assert fuente.desfase_del_servidor() == 3.0


def test_un_servidor_en_UTC_devuelve_CERO_y_eso_es_un_dato(monkeypatch):
    ahora = dt.datetime.now(dt.timezone.utc).timestamp()
    _poner(monkeypatch, _FalsoMT5(tick_time=ahora))
    assert fuente.desfase_del_servidor() == 0.0


def test_con_el_mercado_cerrado_devuelve_None_y_NO_cero(monkeypatch):
    """LA DISTINCION QUE JUSTIFICA LA FUNCION.

    Con el mercado cerrado el último tick es viejo y la cuenta da cualquier
    cosa. Devolver 0 ahí sería afirmar que el servidor está en UTC — y un
    histórico corrido tres horas no falla en ningún lado: sólo hace que la
    estrategia se mine en una franja y el EA opere en otra.
    """
    viejo = dt.datetime.now(dt.timezone.utc).timestamp() - 10 * 24 * 3600
    _poner(monkeypatch, _FalsoMT5(tick_time=viejo))
    assert fuente.desfase_del_servidor() is None


def test_sin_tick_tampoco_inventa(monkeypatch):
    _poner(monkeypatch, _FalsoMT5(tick_time=None))
    assert fuente.desfase_del_servidor() is None


def test_un_desfase_que_no_es_de_horas_se_descarta(monkeypatch):
    """Los brokers usan desfases enteros o de media hora. Uno de 1,7 horas
    significa que la medición está sucia, no que el broker sea raro.

    Con la tolerancia original de doce minutos, 1,7 se aceptaba como 1,5: el
    módulo que existe para no adivinar el reloj adivinaba.
    """
    ahora = dt.datetime.now(dt.timezone.utc).timestamp()
    _poner(monkeypatch, _FalsoMT5(tick_time=ahora + 1.7 * 3600))
    assert fuente.desfase_del_servidor() is None


def test_el_desfase_viaja_en_la_conexion(monkeypatch):
    """Tiene que llegar hasta el dataset. Si se queda acá, alguien lo va a
    reemplazar por una constante global y el error vuelve."""
    ahora = dt.datetime.now(dt.timezone.utc).timestamp()
    _poner(monkeypatch, _FalsoMT5(tick_time=ahora + 2 * 3600))
    c = fuente.conectar()
    assert c.desfase_utc == 2.0
    assert c.servidor == "Falso-Demo"


# ========================================================== los errores

def test_sin_metatrader_abierto_lo_dice_con_esas_palabras(monkeypatch):
    _poner(monkeypatch, _FalsoMT5(arranca=False))
    with pytest.raises(fuente.MT5Error, match="Abrilo"):
        fuente.conectar()


def test_abierto_pero_sin_cuenta(monkeypatch):
    _poner(monkeypatch, _FalsoMT5(cuenta=False))
    with pytest.raises(fuente.MT5Error, match="sin cuenta"):
        fuente.conectar()


def test_un_simbolo_que_no_esta_en_ese_servidor(monkeypatch):
    """Pasa siempre: cada broker le pone otro nombre al S&P. Tiene que decir
    cuál falta, no fallar con un error de MetaTrader."""
    _poner(monkeypatch, _FalsoMT5())
    with pytest.raises(fuente.MT5Error, match="NO_EXISTE"):
        fuente.descargar("NO_EXISTE")


def test_una_temporalidad_que_no_existe(monkeypatch):
    _poner(monkeypatch, _FalsoMT5(velas=[(0, 1, 1, 1, 1, 1)]))
    with pytest.raises(fuente.MT5Error, match="Temporalidad"):
        fuente.descargar("EURUSD", "3m")


# ========================================================== la descarga

def _serie(n, desde=1_600_000_000):
    """n velas horarias, de la más NUEVA a la más vieja, como las da MT5."""
    return [(desde + (n - i) * 3600, 100.0 + i, 101.0 + i, 99.0 + i,
             100.5 + i, 10) for i in range(n)]


def test_cada_vela_conserva_SU_precio_al_rearmar_las_paginas(monkeypatch):
    """MetaTrader entrega las velas de la más nueva a la más vieja y por
    páginas. Rearmarlas mal mezcla precios entre fechas.

    NO alcanza con comprobar que el índice quede ordenado: `sort_index` lo
    ordena igual aunque el ensamblado esté mal, así que esa prueba pasaba
    aunque cada precio hubiera quedado en la fecha equivocada. Acá se comprueba
    el par fecha→precio, que es lo que un ensamblado malo rompe.
    """
    import pandas as pd

    velas = _serie(120)
    esperado = {pd.Timestamp(v[0], unit="s"): v[4] for v in velas}
    _poner(monkeypatch, _FalsoMT5(velas=velas))
    monkeypatch.setattr(fuente, "POR_PEDIDO", 17)      # páginas desparejas
    df = fuente.descargar("EURUSD", "1h", maximo=1000)

    assert len(df) == 120
    assert df.index.is_monotonic_increasing
    for fecha, cierre in esperado.items():
        assert df.loc[fecha, "close"] == cierre, f"{fecha} quedó con otro precio"


def test_se_pagina_porque_de_una_no_entran(monkeypatch):
    """Medido: pidiendo 100.000 velas contesta "Invalid params" y con 50.000
    anda. Sin paginar, el histórico se corta en el tope y nadie lo nota."""
    falso = _poner(monkeypatch, _FalsoMT5(velas=_serie(120)))
    monkeypatch.setattr(fuente, "POR_PEDIDO", 50)
    df = fuente.descargar("EURUSD", "1h", maximo=1000)
    assert len(df) == 120
    assert len(falso.pedidos) >= 3, f"no paginó: {falso.pedidos}"


def test_no_se_pide_mas_de_lo_pedido(monkeypatch):
    falso = _poner(monkeypatch, _FalsoMT5(velas=_serie(500)))
    monkeypatch.setattr(fuente, "POR_PEDIDO", 50)
    df = fuente.descargar("EURUSD", "1h", maximo=100)
    assert len(df) <= 100


def test_las_columnas_son_las_que_espera_el_motor(monkeypatch):
    """`tick_volume` se renombra: el resto de la aplicación pide `volume`."""
    _poner(monkeypatch, _FalsoMT5(velas=_serie(10)))
    df = fuente.descargar("EURUSD", "1h")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_sin_velas_lo_dice_y_no_devuelve_un_frame_vacio(monkeypatch):
    """Un frame vacío se guardaría como dataset y el instrumento aparecería
    listo con cero velas."""
    _poner(monkeypatch, _FalsoMT5(velas=[]))
    with pytest.raises(fuente.MT5Error, match="no devolvió velas"):
        fuente.descargar("EURUSD", "1h")


# ====================================================== los instrumentos

def test_las_doce_mil_acciones_de_nasdaq_no_entran(monkeypatch):
    """MetaQuotes-Demo trae ~12.000 acciones y ETF. Ninguna sirve para lo que
    hace la aplicación, y en una lista tapan los 162 que sí."""
    simbolos = [
        SimpleNamespace(name="EURUSD", path="Forex\\EURUSD", digits=5,
                        point=1e-5, trade_contract_size=100_000,
                        volume_min=0.01, spread=1),
        SimpleNamespace(name="US500", path="Indexes\\US500", digits=2,
                        point=0.01, trade_contract_size=1, volume_min=0.1,
                        spread=30),
        SimpleNamespace(name="AAPL", path="Nasdaq\\Stock\\AAPL", digits=2,
                        point=0.01, trade_contract_size=1, volume_min=1,
                        spread=5),
    ]
    _poner(monkeypatch, _FalsoMT5(simbolos=simbolos))
    nombres = [i["simbolo"] for i in fuente.instrumentos()]
    assert nombres == ["EURUSD", "US500"]


def test_sin_conexion_NO_dice_que_falta_el_simbolo(monkeypatch):
    """Encontrado usándolo: sin MetaTrader abierto, `symbol_select` devuelve
    False para todo y el error decía "US500 no existe en este servidor".

    Eso manda a buscar el problema donde no está: uno se pone a probar nombres
    —US500, SP500, SPX500— cuando lo que falta es abrir el programa.
    """
    falso = _FalsoMT5(arranca=False, cuenta=False)
    _poner(monkeypatch, falso)
    with pytest.raises(fuente.MT5Error, match="No hay conexión"):
        fuente.descargar("US500")


def test_con_conexion_y_simbolo_malo_si_dice_que_falta_el_simbolo(monkeypatch):
    """La contracara: arreglar el mensaje no puede tapar el caso real."""
    _poner(monkeypatch, _FalsoMT5(velas=_serie(5)))
    with pytest.raises(fuente.MT5Error, match="NO_EXISTE no existe"):
        fuente.descargar("NO_EXISTE")


def test_el_huso_de_QUIEN_MIDE_no_cambia_el_resultado(monkeypatch):
    """El reloj del usuario no entra en la cuenta, y tiene que seguir así.

    Alguien en Argentina está en UTC-3 y MetaQuotes-Demo en UTC+3: seis horas.
    Si esa diferencia se colara, la misma descarga daría un desfase distinto
    según desde dónde se corra, y el EA operaría en otra franja que la que se
    minó — sin que nada falle.

    SE COMPRUEBA SOBRE EL CODIGO Y NO CORRIENDO CON OTRO HUSO, porque en
    Windows `time.tzset` no existe: la primera versión de esta prueba cambiaba
    la variable TZ, no surtía efecto, medía tres veces lo mismo y pasaba en
    verde sin comprobar nada.

    Lo que se prohíbe es la forma concreta de colar el huso local:
    `datetime.now()` y `fromtimestamp(x)` sin zona toman la del sistema.
    """
    from pathlib import Path

    fuente_txt = (Path(fuente.__file__)).read_text(encoding="utf-8")
    codigo = " ".join(l for l in fuente_txt.splitlines()
                      if not l.strip().startswith("#"))

    assert "datetime.now()" not in codigo, (
        "`datetime.now()` sin zona toma el huso de la máquina")
    for llamada in re.findall(r"fromtimestamp\(([^)]*)\)", codigo):
        assert "timezone.utc" in llamada or "tz" in llamada, (
            f"`fromtimestamp({llamada})` sin zona toma el huso de la máquina")
    # y el desfase que devuelve sigue siendo el medido
    ahora = dt.datetime.now(dt.timezone.utc).timestamp()
    _poner(monkeypatch, _FalsoMT5(tick_time=ahora + 3 * 3600))
    assert fuente.desfase_del_servidor() == 3.0


def test_sin_el_paquete_instalado_la_aplicacion_sigue_andando(monkeypatch):
    """El paquete de MetaTrader SOLO existe para Windows.

    En el servidor de Linux no se puede instalar, así que un import al tope del
    módulo tiraría abajo la aplicación entera por una fuente de datos que ahí
    ni se usa. Se importa adentro de la función y el error dice qué falta.
    """
    import builtins

    real = builtins.__import__

    def sin_mt5(nombre, *a, **k):
        if nombre == "MetaTrader5":
            raise ImportError("No module named 'MetaTrader5'")
        return real(nombre, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sin_mt5)
    with pytest.raises(fuente.MT5Error, match="pip install MetaTrader5"):
        fuente.conectar()


def test_el_modulo_no_importa_MetaTrader5_al_tope():
    """Si alguien lo sube al encabezado, la aplicación deja de arrancar en
    Linux y el fallo aparece lejos de acá."""
    from pathlib import Path

    cabeza = Path(fuente.__file__).read_text(encoding="utf-8").split("def ")[0]
    assert "import MetaTrader5" not in cabeza
