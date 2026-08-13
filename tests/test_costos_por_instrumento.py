"""El spread no es una preferencia: es un dato del mercado.

0.36 puntos es el spread del S&P. Sobre EURUSD a 1.15 significa pagar 31% por
operación y todas las candidatas dan -100%. Esa dirección ya estaba cubierta
por un aviso.

La que faltaba es la contraria y es peor. Viniendo de EURUSD (0.00012) a
Bitcoin (12), el costo queda en la cienmilésima parte del real. No dispara
ninguna alarma —el guardia vigila que no sea demasiado CARO— y el resultado no
es un -100% evidente sino un backtest sin costos que se ve espectacular. Un
error que se ve como un éxito es peor que uno que se ve como un error.
"""

from __future__ import annotations

import pytest

from botiquant.data.catalog import CATALOG

POR_CLAVE = {c["key"]: c for c in CATALOG}

#: precio de referencia de cada mercado, para traducir el spread a % del precio
PRECIOS = {"sp500": 7741.69, "eurusd": 1.15561, "xauusd": 4256.82, "btcusd": 64016.5}


def _costo_pct(spread: float, slippage: float, precio: float) -> float:
    return (spread + 2 * slippage) / precio * 100.0


def test_cada_instrumento_del_catalogo_trae_su_spread():
    """Sin esto no hay nada que sugerir y el usuario tiene que adivinar."""
    for clave in PRECIOS:
        entrada = POR_CLAVE[clave]
        assert entrada["spread"] > 0, clave
        assert "slippage" in entrada, clave


def test_los_spreads_del_catalogo_son_razonables_en_su_mercado():
    """Un ida y vuelta sano está muy por debajo del 1% del precio. Si alguno de
    los valores del catálogo no lo cumpliera, la aplicación estaría sugiriendo
    de fábrica un costo que hace perder a cualquier estrategia."""
    for clave, precio in PRECIOS.items():
        e = POR_CLAVE[clave]
        pct = _costo_pct(e["spread"], e.get("slippage", 0.0), precio)
        assert 0 < pct < 0.5, f"{clave}: {pct:.3f}% por operación"


@pytest.mark.parametrize("desde,hasta", [
    ("eurusd", "btcusd"),   # 0.00012 contra 12: el peor de todos
    ("eurusd", "sp500"),
    ("eurusd", "xauusd"),
    ("xauusd", "btcusd"),
    ("sp500", "btcusd"),
])
def test_heredar_el_spread_del_mercado_anterior_cobra_de_menos(desde, hasta):
    """Documenta el agujero que obliga a que los costos sigan al instrumento.

    Estos saltos NO los agarra el aviso de costo imposible, porque el costo
    heredado queda ridículamente barato en vez de ridículamente caro.
    """
    heredado = POR_CLAVE[desde]
    correcto = POR_CLAVE[hasta]
    precio = PRECIOS[hasta]

    pct_heredado = _costo_pct(heredado["spread"], heredado.get("slippage", 0.0), precio)
    pct_correcto = _costo_pct(correcto["spread"], correcto.get("slippage", 0.0), precio)

    # cobra bastante de menos...
    assert pct_heredado < pct_correcto / 2, (
        f"{desde}->{hasta}: heredado {pct_heredado:.6f}% vs correcto {pct_correcto:.6f}%")
    # ...y el aviso de "costo imposible" no lo ve, porque sólo mira hacia arriba
    assert pct_heredado <= 1.0, "si saltara el aviso, este test ya no haría falta"


def test_el_salto_peor_deja_el_costo_cien_mil_veces_mas_barato():
    """El número concreto que justifica el arreglo, para que no se relaje."""
    eur, btc = POR_CLAVE["eurusd"], POR_CLAVE["btcusd"]
    assert btc["spread"] / eur["spread"] > 10_000
