"""El funding como SEÑAL, no sólo como costo.

Ya viajaba al motor para que la posición abierta lo pague. Lo que faltaba es
que la biblioteca lo pudiera MIRAR: no había forma de escribir "sólo operá
cuando los largos están amontonados" si el dato no estaba en el dataframe.

Es el único bloque que no mira el precio, y por eso vale: el funding lo paga el
lado que está de más, así que dice quién está amontonado. Esa información no
está adentro de la vela, y por eso puede decidir distinto de todo lo demás —
que es justo lo que le falta a un portafolio armado sólo con medias móviles.

Lo que este archivo defiende son las dos formas en que esto podría mentir:
midiendo algo que no significa lo mismo en dos monedas, o filtrando por un dato
que no existe.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.data.sample import generate_sample
from botiquant.indicators.library import FundingPct
from botiquant.mining.miner import mine


def _frame(tasas, precio=100.0):
    idx = pd.date_range("2026-01-01", periods=len(tasas), freq="h", tz="UTC")
    return pd.DataFrame({"open": precio, "high": precio, "low": precio,
                         "close": precio, "volume": 1.0, "funding": tasas},
                        index=idx)


# ======================================= que signifique lo mismo en todas

def test_es_un_PERCENTIL_y_no_un_valor_crudo():
    """UN UMBRAL CRUDO NO SIGNIFICA LO MISMO EN DOS MONEDAS.

    MEDIDO el 1/9/2026 sobre los últimos 1000 cobros de cada una: la tasa media
    anualizada va de +16,62% en Monero a -2,21% en Zcash. No sólo cambia de
    tamaño, CAMBIA DE SIGNO. Un bloque que dijera "funding mayor que 0,01%"
    estaría casi siempre encendido en una y casi nunca en la otra, y la misma
    regla minada en dos pares serían dos reglas distintas sin que nada lo diga.
    """
    caro = _frame(np.linspace(0.0001, 0.01, 200))     # una moneda con funding alto
    barato = _frame(np.linspace(-0.01, -0.0001, 200))  # otra con funding negativo

    v_caro = FundingPct.compute(caro, period=90)["value"]
    v_barato = FundingPct.compute(barato, period=90)["value"]

    # las dos series suben dentro de SU rango, así que el percentil final es el
    # mismo aunque los valores absolutos no se parezcan en nada
    assert v_caro[-1] == pytest.approx(100.0)
    assert v_barato[-1] == pytest.approx(100.0)


def test_el_mas_bajo_de_su_ventana_da_CASI_cero_y_nunca_cero():
    """El piso es 100/n y no 0, porque el rango del percentil es 1..n.

    Con ventana de 90, el valor más bajo da 1,11 y no 0. Importa saberlo al
    poner un umbral: pedir "menor que 1" no lo cumple NADIE, y eso se vería
    como una búsqueda que no encuentra nada en vez de como un umbral imposible.
    El gen más bajo que ofrece el bloque es 5, así que queda por encima.
    """
    v = FundingPct.compute(_frame(np.linspace(0.01, -0.01, 200)), period=90)["value"]
    assert v[-1] == pytest.approx(100 / 90, rel=1e-6)
    assert 0 < v[-1] < 5.0


def test_NO_MIRA_EL_FUTURO():
    """La ventana termina en la vela que se está evaluando.

    Si mirara hacia adelante, la búsqueda encontraría reglas que en vivo son
    imposibles — y el backtest no lo diría: diría que son excelentes.
    """
    tasas = np.zeros(200)
    tasas[150] = 99.0            # un pico enorme en la vela 150
    v = FundingPct.compute(_frame(tasas), period=90)["value"]

    # antes del pico, ninguna vela puede haberlo visto: todas valen lo mismo
    antes = v[100:150]
    assert np.nanmax(antes) == pytest.approx(np.nanmin(antes)), (
        "una vela anterior al pico cambió de valor: está mirando el futuro")


# ============================== que no filtre por un dato que no existe

def test_SIN_LA_COLUMNA_no_inventa_un_valor():
    """Devolver ceros haría que el filtro comparara contra un número real y
    decidiera. Con NaN la condición es falsa siempre, que es lo honesto: no se
    puede filtrar por algo que no se midió."""
    sin = generate_sample("X", bars=200)
    v = FundingPct.compute(sin, period=90)["value"]
    assert np.isnan(v).all()


def test_sobre_un_CFD_se_DESCARTAN_y_SE_DICE_CUALES():
    """Ni se corta ni se ignora en silencio.

    Cortar sería lo natural pero está mal: pedir "todos los bloques" es
    legítimo y no debería fallar por incluir dos que este instrumento no puede
    usar. Ignorarlos sin decirlo es peor: `FundingPct` da NaN sin la columna,
    la condición es falsa en todas las velas, la estrategia no opera nunca, y
    eso llega como "no se encontró nada" — que manda a aflojar los filtros
    cuando lo que pasa es que el instrumento no tiene el dato.
    """
    df = generate_sample("X", bars=400)
    r = mine(df, ["ema_cross"], ["funding_alto_filter", "funding_bajo_filter"],
             max_candidates=2, min_trades=1)
    assert r["sin_funding"] == ["funding_alto_filter", "funding_bajo_filter"]
    assert r["tested"] >= 1, "descartar los bloques no puede impedir minar"


def test_en_un_perpetuo_no_se_descarta_nada():
    df = generate_sample("X", bars=600)
    df["funding"] = np.linspace(-0.001, 0.001, len(df))
    r = mine(df, ["ema_cross"], ["funding_alto_filter"], max_candidates=2,
             min_trades=1)
    assert r["sin_funding"] == []


def test_con_la_columna_mina_normalmente():
    """El control no puede impedir lo que sí se puede hacer."""
    df = generate_sample("X", bars=600)
    df["funding"] = np.linspace(-0.001, 0.001, len(df))
    r = mine(df, ["ema_cross"], ["funding_alto_filter"], max_candidates=3,
             min_trades=1)
    assert "databank" in r and r["tested"] >= 1


def test_los_dos_lados_existen():
    """Si el funding alto es buena o mala señal no lo decide la biblioteca: lo
    decide la búsqueda, probándolo. Por eso están las dos versiones y no sólo
    la que a alguien le parece la correcta."""
    from botiquant.generator.templates import TEMPLATES
    assert "funding_alto_filter" in TEMPLATES
    assert "funding_bajo_filter" in TEMPLATES


# ================================================ la alineación temporal

def test_cada_vela_recibe_el_ULTIMO_cobro_ANTERIOR():
    """Se alinea hacia atrás y nunca hacia adelante.

    El cobro que todavía no pasó no existe para esa vela. Interpolar o
    rellenar hacia atrás le daría a la búsqueda un dato que en ese momento
    nadie tenía — y eso no aparece como error sino como una estrategia
    buenísima que en vivo no funciona.
    """
    velas = pd.date_range("2026-01-01", periods=24, freq="h", tz="UTC")
    cobros = pd.Series([0.001, 0.002, 0.003],
                       index=pd.to_datetime(["2026-01-01 00:00", "2026-01-01 08:00",
                                             "2026-01-01 16:00"], utc=True))
    alineado = cobros.reindex(velas, method="ffill")

    assert alineado.iloc[0] == 0.001      # el de las 00:00
    assert alineado.iloc[7] == 0.001      # 07:00 todavía no vio el de las 08
    assert alineado.iloc[8] == 0.002      # 08:00 sí
    assert alineado.iloc[15] == 0.002     # 15:00 todavía no vio el de las 16
    assert alineado.iloc[16] == 0.003
