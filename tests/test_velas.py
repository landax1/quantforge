"""Leer la vela entera y no sólo el cierre.

Un backtest de cierres no puede ver lo que pasó adentro de la vela, y ahí está
la mitad de la información: una vela que subió, tocó un techo y volvió es
IDENTICA a una que nunca subió si sólo se mira dónde cerró.

Lo que este archivo defiende es que los tres indicadores midan cosas
DISTINTAS entre sí —si midieran lo mismo con otro nombre, agrandarían el
espacio de búsqueda sin agregar información, que es la peor combinación— y que
sigan normalizados por el rango de la propia vela, para que el mismo umbral
signifique lo mismo en Bitcoin y en Cardano.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.indicators.library import (ClosePosition, Cuerpo, Mecha,
                                          VelaAdentro)


def _velas(filas):
    """filas: (open, high, low, close)."""
    idx = pd.date_range("2026-01-01", periods=len(filas), freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": [f[0] for f in filas], "high": [f[1] for f in filas],
         "low": [f[2] for f in filas], "close": [f[3] for f in filas],
         "volume": 1.0}, index=idx)


# ===================================== cada uno mide algo distinto

def test_cuerpo_y_ClosePosition_NO_miden_lo_mismo():
    """LA RAZON DE QUE `Cuerpo` EXISTA.

    `ClosePosition` dice QUIEN ganó el pulso; `Cuerpo` dice CUANTO se peleó.
    Estas dos velas cierran las dos arriba del todo —ClosePosition idéntico—
    pero una abrió abajo y subió sin dudar, y la otra recorrió el rango entero
    y volvió. Operarlas igual es operar dos cosas distintas con una regla.
    """
    df = _velas([
        (100, 110, 100, 110),      # abrió abajo, cerró arriba: cuerpo entero
        (109, 110, 100, 110),      # bajó hasta 100 y volvió: cuerpo mínimo
    ])
    cp = ClosePosition.compute(df)["value"]
    cu = Cuerpo.compute(df)["value"]

    assert cp[0] == pytest.approx(cp[1]), (
        "las dos cierran en el máximo: ClosePosition no las distingue")
    assert cu[0] > 90 and cu[1] < 20, (
        "y Cuerpo sí: ahí está la información que el cierre borra")


def test_la_mecha_ve_lo_que_el_cierre_borra():
    """Una vela que subió y volvió contra una que nunca subió.

    Cierran en el mismo lugar y con el mismo cuerpo. Lo único que las separa
    es la mecha, o sea el precio que ESTUVO y no se aguantó.
    """
    df = _velas([
        (100, 100.5, 99.5, 100.2),   # nunca subió
        (100, 110.0, 99.5, 100.2),   # subió a 110 y volvió
    ])
    m = Mecha.compute(df)
    assert m["arriba"][1] > 80, "la mecha superior tiene que dominar la vela"
    assert m["arriba"][0] < 40, "la primera casi no tiene mecha arriba"


def test_las_dos_mechas_se_reparten_lo_que_no_es_cuerpo():
    """Cuerpo + mecha de arriba + mecha de abajo son la vela entera.

    Si no cerrara, alguno estaría contando dos veces la misma parte del rango
    y los umbrales significarían cosas distintas de las que dicen.
    """
    df = _velas([(103, 110, 100, 105), (108, 112, 101, 102)])
    cu = Cuerpo.compute(df)["value"]
    m = Mecha.compute(df)
    for i in range(len(df)):
        total = cu[i] + m["arriba"][i] + m["abajo"][i]
        assert total == pytest.approx(100.0), f"la vela {i} no cierra en 100"


def test_la_vela_interior_se_reconoce_contra_la_ANTERIOR():
    """Contra la anterior y no contra sí misma: contra sí misma la condición
    sería cierta siempre, por construcción."""
    df = _velas([
        (100, 110, 90, 105),         # la de referencia
        (101, 108, 95, 103),         # entera adentro
        (101, 115, 95, 103),         # se sale por arriba
        (101, 108, 85, 103),         # se sale por abajo
    ])
    v = VelaAdentro.compute(df)["value"]
    assert v[1] == 100.0
    assert v[2] == 0.0 and v[3] == 0.0


# ===================================== normalizados, como el resto

def test_significan_LO_MISMO_en_dos_instrumentos_de_otra_escala():
    """La regla que ya cumplen los demás filtros de contexto.

    La misma vela en escala de Bitcoin y en escala de Cardano tiene que dar el
    mismo número: si no, el mismo umbral sería dos filtros distintos y una
    estrategia minada en un par no significaría nada en otro.
    """
    grande = _velas([(70000, 71000, 69500, 70800)])
    chico = _velas([(0.70, 0.71, 0.695, 0.708)])
    assert Cuerpo.compute(grande)["value"][0] == pytest.approx(
        Cuerpo.compute(chico)["value"][0], rel=1e-6)
    assert Mecha.compute(grande)["arriba"][0] == pytest.approx(
        Mecha.compute(chico)["arriba"][0], rel=1e-6)


def test_una_vela_sin_rango_no_rompe_la_condicion():
    """Posible en horas muertas. Devolver NaN cortaría la condición entera y
    la estrategia dejaría de operar sin que nada lo diga — el mismo criterio
    que ya usa ClosePosition."""
    df = _velas([(100, 100, 100, 100)])
    assert np.isfinite(Cuerpo.compute(df)["value"][0])
    m = Mecha.compute(df)
    assert np.isfinite(m["arriba"][0]) and np.isfinite(m["abajo"][0])


def test_no_miran_el_futuro():
    """La vela interior compara contra la anterior; nada mira hacia adelante.

    Un indicador que mirara adelante encontraría reglas imposibles en vivo, y
    el backtest no lo diría: diría que son excelentes.
    """
    df = _velas([(100, 110, 90, 105)] * 6)
    entero = VelaAdentro.compute(df)["value"]
    # recortar el final no puede cambiar lo que ya estaba calculado
    corto = VelaAdentro.compute(df.iloc[:4])["value"]
    assert list(corto) == list(entero[:4])
