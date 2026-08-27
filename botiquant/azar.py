"""Cuánto del resultado de una estrategia puede ser haberla buscado mucho.

Cuando se prueban 1.500 candidatas y se elige la mejor, el número de esa mejor
está inflado por el simple hecho de haber elegido entre 1.500. No es un error
de cálculo: es estadística. Con suficientes intentos siempre aparece alguna que
se ve espectacular sin tener ninguna ventaja real.

LA CUENTA, de Bailey y López de Prado. El Sharpe más alto que se espera ver por
PURO AZAR después de N intentos independientes, aun cuando el Sharpe verdadero
de todos sea cero:

       100 intentos  ->  2,53
     1.000 intentos  ->  3,26
     1.500 intentos  ->  3,37
    10.000 intentos  ->  3,86

Mil quinientos es lo que el ciclo mina por vuelta, y cada doce horas hay una
vuelta más.

MEDIDO SOBRE LA CORRIDA REAL DE BTCUSDT, y es la razón de que esto exista: el
mejor Sharpe encontrado fue 1,606 y el esperado por azar con esos mismos 1.500
intentos era 1,564. Casi pegados. Eso no dice que la estrategia no sirva —
aguantó 223 operaciones fuera de muestra— pero sí que su Sharpe, solo, casi no
distingue habilidad de suerte.

ESTO NO BLOQUEA NADA, y es deliberado. Es contexto al lado de un número, no una
puerta más: "Sharpe 1,61 · el azar con 1.500 intentos da 1,56" le dice a
alguien mucho más que "Sharpe 1,61", y lo deja decidir. Convertirlo en umbral
sería inventar una vara sobre una estimación que ya sabemos incompleta.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any

#: La constante de Euler-Mascheroni. Aparece en la aproximación del máximo
#: esperado de N normales, que es lo que estamos calculando.
GAMMA = 0.5772156649015329

_N01 = NormalDist()


def max_esperado(media_sr: float, desvio_sr: float, intentos: int) -> float | None:
    """El Sharpe más alto que se espera ver por azar con `intentos` pruebas.

    Devuelve None cuando no se puede calcular en vez de un número dudoso: con
    menos de dos intentos no hay máximo del que hablar, y con dispersión cero
    todas las candidatas dieron lo mismo y la fórmula no aplica.
    """
    if intentos < 2 or desvio_sr <= 0:
        return None
    z = ((1.0 - GAMMA) * _N01.inv_cdf(1.0 - 1.0 / intentos)
         + GAMMA * _N01.inv_cdf(1.0 - math.exp(-1.0) / intentos))
    return media_sr + desvio_sr * z


def contexto(sharpe: float | None, *, media_sr: float, desvio_sr: float,
             intentos: int, muestra: int = 0) -> dict[str, Any]:
    """El Sharpe de una estrategia al lado de lo que da el azar.

    `muestra` es sobre cuántas candidatas se calculó la dispersión. Importa
    decirlo: si es menor que `intentos`, la dispersión está medida sobre las
    que SOBREVIVIERON el filtro, que son las parecidas entre sí. Eso subestima
    la dispersión real y por lo tanto subestima el umbral — o sea que el
    número verdadero es PEOR que el que mostramos, y conviene que se sepa.
    """
    esperado = max_esperado(media_sr, desvio_sr, intentos)
    if sharpe is None or esperado is None:
        return {"medible": False,
                "motivo": "no se puede calcular con los datos de esta corrida"}

    return {
        "medible": True,
        "sharpe": round(float(sharpe), 3),
        "esperado_por_azar": round(esperado, 3),
        "intentos": intentos,
        # Cuánto le saca al azar. Por debajo de cero, el Sharpe de esta
        # estrategia es MENOR que el que salía por probar mucho.
        "ventaja": round(float(sharpe) - esperado, 3),
        "supera_al_azar": float(sharpe) > esperado,
        # La honestidad sobre la propia estimación.
        "dispersion_subestimada": bool(muestra and muestra < intentos),
        "muestra": muestra,
    }


def frase(c: dict[str, Any]) -> str:
    """Una línea para mostrar al lado del Sharpe, sin abrir nada."""
    if not c.get("medible"):
        return ""
    base = (f"Sharpe {c['sharpe']} · el azar con {c['intentos']:,} intentos "
            f"da {c['esperado_por_azar']}")
    if not c["supera_al_azar"]:
        base += " — no le saca ventaja"
    if c.get("dispersion_subestimada"):
        base += " (el umbral real es más alto)"
    return base
