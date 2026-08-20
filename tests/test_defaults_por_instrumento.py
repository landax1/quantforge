"""Cada instrumento trae los valores que le corresponden, no uno para todos.

El caso que lo motivó: minar EURUSD pidiendo 5% anual y profit factor 1 no
devolvía casi nada. Medido — 400 candidatas, 1h, diez años, riesgo 1%:

    con 30+ operaciones                354
    profit factor >= 1                  19  (5.4%)
    retorno anual >= 5%                  0  (0.0%)
    techo del percentil 100           1.76%

No es que la vara fuera exigente: al 1% de riesgo, en EURUSD y en ese período,
5% anual NO EXISTE. La mejor de cuatrocientas hace 1.76%.

La causa principal resultó ser la dirección. Con la misma vara y las mismas
220 candidatas:

    sólo largos      13 rentables · techo  1.76%
    ambas            18 rentables · techo  4.52%

Permitir cortos no aflojó nada y encontró MÁS rentables, con el techo dos veces
y media más arriba. Un par de divisas no sube: buscar sólo largos tira la mitad
del espacio. Un índice sí sube, y ahí "sólo largos" es una hipótesis con
fundamento.
"""

from __future__ import annotations

import pytest

from botiquant.data.catalog import CATALOG


def test_cada_instrumento_declara_su_direccion():
    faltan = [c["key"] for c in CATALOG if not c.get("direction")]
    assert not faltan, f"instrumentos sin dirección sugerida: {faltan}"


#: Rentables de 200 candidatas, 1h, diez años, riesgo 1%, misma vara (PF >= 1).
#: Es la medición que decide la dirección de cada instrumento — y que corrigió
#: el razonamiento equivocado de que "sólo los índices tienen deriva al alza".
MEDIDO = {
    "sp500":  {"long": 123, "both": 40},
    "xauusd": {"long": 101, "both": 33},
    "btcusd": {"long":  76, "both": 39},
    # empatados en cantidad, pero sólo "ambas" llega a superar el 2% anual
    "eurusd": {"long":  12, "both": 12},
}


@pytest.mark.parametrize("clave", sorted(MEDIDO))
def test_la_direccion_es_la_que_midio_mejor(clave):
    """La dirección sale de medir, no de razonar.

    Se razonó primero —"sólo los índices tienen deriva al alza"— y se razonó
    mal: el oro y el Bitcoin también subieron estos diez años, así que
    shortearlos pelea contra la tendencia de fondo. Poner XAUUSD y BTCUSD en
    ambas direcciones los habría bajado de 101 a 33 y de 76 a 39 rentables.
    """
    c = next(x for x in CATALOG if x["key"] == clave)
    m = MEDIDO[clave]
    if m["long"] > m["both"]:
        assert c["direction"] == "long", (
            f"{clave} rinde más en largos ({m['long']} contra {m['both']} "
            "rentables) y está configurado al revés")
    elif m["both"] > m["long"]:
        assert c["direction"] == "both"
    else:
        # empate en cantidad: gana el que llega más arriba
        assert c["direction"] == "both", (
            f"{clave} empata en cantidad, pero sólo permitiendo cortos supera "
            "el 2% anual")


def test_hay_exactamente_un_instrumento_recomendado():
    """El distintivo pierde sentido si lo llevan varios, y con ninguno la
    aplicación arranca en el primero de la lista, que es arbitrario."""
    marcados = [c["key"] for c in CATALOG if c.get("mejor_rendimiento")]
    assert len(marcados) == 1, f"instrumentos marcados: {marcados}"


def test_el_distintivo_esta_en_el_que_mas_rinde():
    """El cartel dice "más estrategias" y tiene que ser cierto.

    Rentables de 200 candidatas, cada instrumento en la dirección que le toca:

        SP500    123 de 178   69%
        XAUUSD   101 de 174   58%
        BTCUSD    76 de 175   43%
        EURUSD    12 de 176    7%

    Un cartel que promete lo que no cumple es peor que no tener cartel: es la
    primera afirmación comprobable que la aplicación hace, y el usuario la va a
    comprobar en su primera búsqueda.
    """
    marcado = next(c for c in CATALOG if c.get("mejor_rendimiento"))
    mejor = max(MEDIDO, key=lambda k: MEDIDO[k][
        next(c["direction"] for c in CATALOG if c["key"] == k)])
    assert marcado["key"] == mejor, (
        f"el distintivo está en {marcado['key']} pero el que más rinde es "
        f"{mejor}; volvé a medir antes de moverlo")


@pytest.mark.parametrize("campo", ["spread", "slippage", "stop_points",
                                   "contract_size", "min_lot", "direction"])
def test_el_catalogo_esta_completo(campo):
    faltan = [c["key"] for c in CATALOG if c.get(campo) in (None, "")]
    assert not faltan, f"a estos les falta {campo}: {faltan}"
