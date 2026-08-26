"""El Pine de un perpetuo, que es lo que va a operar de verdad por webhook.

Cambia el estatus del exportador de Pine. Hasta ahora era un extra para mirar
la estrategia en un gráfico; con el Signal Bot de BingX pasa a ser el camino de
producción — TradingView evalúa las reglas en la nube y le manda la orden al
exchange. Si el script opera distinto de lo que se midió, la persona se entera
con su plata.

Las dos cosas que este archivo defiende:

  * en cripto el tamaño es EL MINADO, no el 10% de capital que TradingView usa
    por defecto cuando no se le pasa `qty`
  * el piso es el mínimo del exchange (0,0001 BTC) y no un contrato entero,
    que en Bitcoin son ochenta mil dólares
"""

from __future__ import annotations

import pytest

from botiquant.core.models import StrategySpec
from botiquant.data.catalog import MINIMOS_PERPETUO
from botiquant.reports.pine import export_pine


def _spec(size_mode: str = "risk_pct") -> StrategySpec:
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return StrategySpec.from_dict({
        "name": "S", "direction": "both",
        "entry_long": [{"left": ema(15), "op": "cross_above", "right": ema(60)}],
        "entry_short": [{"left": ema(15), "op": "cross_below", "right": ema(60)}],
        "risk": {"size_mode": size_mode, "size_value": 1.0,
                 "stop_type": "atr", "stop_value": 2.0,
                 "target_type": "atr", "target_value": 4.0, "atr_period": 14},
    })


def _cripto(**kw) -> str:
    return export_pine(_spec(kw.pop("size_mode", "risk_pct")), name="S",
                       symbol_hint="BTCUSDT", fraccionable=True,
                       minimo=kw.pop("minimo", 0.0001), **kw)


def _cfd() -> str:
    return export_pine(_spec(), name="S", symbol_hint="SP500")


# ------------------------------------------------------- el tamaño en cripto

def test_en_cripto_el_tamanio_minado_no_es_opcional():
    """La falla más cara posible, y era silenciosa.

    Sin `qty`, TradingView cae en el default del `strategy()`: 10% del capital.
    O sea que una estrategia minada para arriesgar 1% por operación con stop
    por ATR habría operado con un perfil de riesgo completamente distinto, sin
    ningún error a la vista — sólo resultados que no se parecen al backtest.
    """
    code = _cripto()
    assert "qty       = math.max(qtyRisk," in code
    assert "InpUseFixedQty" not in code, (
        "en cripto el tamaño minado se usa siempre; el interruptor sobra")


def test_en_cripto_el_piso_es_el_minimo_del_exchange():
    """Un contrato de BTC son ochenta mil dólares.

    El piso de `math.max(qtyRisk, 1)` protege a los índices de que un tamaño
    fraccionario se redondee a cero. En Bitcoin obliga a abrir una posición de
    ochenta mil dólares, que una cuenta de práctica no puede ni empezar.
    """
    code = _cripto(minimo=0.0001)
    assert "math.max(qtyRisk, 0.0001)" in code
    assert "math.max(qtyRisk, 1)" not in code


def test_sin_minimo_conocido_no_se_inventa_un_piso():
    """Cero es mejor que un piso prudente inventado: un piso de más obliga a
    arriesgar de más, y eso no se ve hasta que la posición ya está abierta."""
    assert "math.max(qtyRisk, 0)" in _cripto(minimo=0.0)


def test_el_minimo_de_cada_perpetuo_esta_en_el_catalogo():
    """Leídos de la ficha de contrato de BingX, no estimados."""
    assert MINIMOS_PERPETUO["BTCUSDT"] == 0.0001
    assert MINIMOS_PERPETUO["ETHUSDT"] == 0.01


# ------------------------------------------------------- los mensajes del webhook

def test_cada_orden_lleva_su_mensaje_de_webhook():
    """Tres mensajes distintos y no uno.

    BingX necesita saber si tiene que abrir un largo, abrir un corto o cerrar.
    Con un solo mensaje para todo, una señal de venta abriría un largo.
    """
    code = _cripto()
    assert "alert_message=InpMsgLong" in code
    assert "alert_message=InpMsgShort" in code
    assert code.count("alert_message=InpMsgCerrar") >= 3, (
        "las dos salidas por stop/objetivo y la salida por tiempo tienen que "
        "avisar todas: una salida que no manda mensaje deja la posición "
        "abierta en el exchange")


def test_los_mensajes_arrancan_vacios_y_no_inventados():
    """BingX le genera al usuario SU mensaje, con su identificador adentro.

    Inventar un formato produciría órdenes que el exchange descarta en
    silencio — el peor resultado posible, porque parece que está operando.
    """
    code = _cripto()
    assert 'InpMsgLong    = input.string("",' in code
    assert 'InpMsgShort   = input.string("",' in code
    assert 'InpMsgCerrar  = input.string("",' in code


# ------------------------------------------------------- lo que NO cambió

def test_el_pine_de_un_cfd_no_lleva_nada_de_esto():
    """Verificado además byte a byte contra la versión anterior.

    Un CFD sigue con el piso de un contrato y con el interruptor de tamaño,
    que es lo correcto en un instrumento que no admite fracciones.
    """
    code = _cfd()
    assert "InpUseFixedQty" in code
    assert "math.max(qtyRisk, 1)" in code
    assert "alert_message" not in code
    assert "InpMsg" not in code


def test_con_lotes_fijos_en_cripto_tampoco_hay_piso_de_un_contrato():
    code = _cripto(size_mode="fixed_units", minimo=0.0001)
    assert "math.max(qtyFixed, 0.0001)" in code
    assert "math.max(InpContracts, 1)" not in code


# ------------------------------------------------------- sigue siendo Pine válido

def test_no_quedan_llaves_del_template_sin_reemplazar():
    """Un `{bloque_webhook}` suelto compila mal en TradingView y el usuario ve
    un error incomprensible en vez de una estrategia."""
    for code in (_cripto(), _cfd()):
        # las llaves dobles de {{strategy.order.alert_message}} son legítimas
        # en un comentario, así que se buscan las simples de Python
        sospechosas = [l for l in code.splitlines()
                       if "{bloque" in l or "{msg_" in l or "{piso}" in l]
        assert not sospechosas, sospechosas


# ------------------------------------------------------- los costos del backtest

def test_la_comision_medida_viaja_al_script():
    """Estaba clavada en cero, y era la divergencia más peligrosa de todas.

    Con comisión cero, el Strategy Tester de TradingView mostraba la estrategia
    MÁS rentable que el backtest de Botiquant. Una divergencia que favorece no
    la investiga nadie —el número gusta— así que se habría descubierto
    operando, que es el único lugar donde cuesta plata.
    """
    code = export_pine(_spec(), name="S", symbol_hint="BTCUSDT",
                       fraccionable=True, minimo=0.0001, comision_pct=0.04)
    assert "commission_value=0.04" in code


def test_sin_comision_declarada_sigue_en_cero():
    """Un CFD con spread y sin comisión no tiene que heredar la de un exchange."""
    assert "commission_value=0," in _cfd()


def test_hasta_el_default_de_tamanio_es_seguro_en_cripto():
    """Defensa en profundidad, y no es paranoia.

    En cripto `qty` se pasa siempre, así que el default del `strategy()` no se
    usa nunca. Pero si alguna vez alguien quita ese argumento, TradingView cae
    en el default EN SILENCIO — y el default original, 10% del capital, es
    exactamente el error que este archivo vino a arreglar. Con el mínimo del
    exchange, lo peor que puede pasar es que abra la posición más chica.
    """
    code = _cripto(minimo=0.0001)
    assert "default_qty_type=strategy.fixed, default_qty_value=0.0001" in code
    assert "percent_of_equity" not in code


def test_el_cfd_conserva_su_default_de_porcentaje():
    """Ahí el porcentaje SÍ es lo correcto: un tamaño fraccionario en un
    instrumento sin fracciones se redondea a cero y no abre nada."""
    assert "default_qty_type=strategy.percent_of_equity, default_qty_value=10" in _cfd()


def test_el_encabezado_dice_sobre_que_fechas_se_midio():
    """Sin el rango, comparar no significa nada.

    El Strategy Tester de TradingView arranca con SU propio rango. Comparar su
    número contra el de Botiquant sin alinear las fechas es comparar dos
    períodos distintos: la diferencia que aparece no dice nada, y la que no
    aparece tampoco.
    """
    code = export_pine(_spec(), name="S", symbol_hint="BTCUSDT",
                       fraccionable=True, minimo=0.0001,
                       desde="2019-09-10", hasta="2026-08-26")
    assert "2019-09-10" in code and "2026-08-26" in code
    assert "Strategy Tester" in code


def test_sin_fechas_el_encabezado_no_inventa_un_rango():
    assert "Medida entre" not in _cfd()
