"""¿Esto que voy a encender se parece a lo que ya tengo corriendo?

Es la pregunta que separa un portafolio de la misma apuesta con cinco nombres.
El error clásico es acumular estrategias con reglas distintas que se mueven
juntas: parecen cinco decisiones y son una sola, y el día que esa una sale mal
salen mal las cinco a la vez.

MEDIDO SOBRE LAS CINCO QUE EL CICLO PUSO EN PRÁCTICA, y es la razón de que
este archivo exista:

    correlación mediana entre pares   -0,057   (excelente)
    S-1249 y S-657                    +0,713   las dos de BTCUSDT
    S-001  y S-002                    +0,640   las dos de S&P

O sea: nombres distintos, reglas distintas, y gemelas. Con dos instrumentos,
cinco estrategias son como tres apuestas.

SE COMPARAN RENDIMIENTOS DIARIOS Y NO CURVAS DE CAPITAL. Dos curvas que suben
correlacionan altísimo por la tendencia común aunque operen en momentos
completamente distintos, y eso no dice nada sobre si se van a caer juntas. Lo
que importa es si ganan y pierden los mismos días.

EL INSTRUMENTO ES EL MEJOR ATAJO. Medido arriba: mismo instrumento da 0,64 a
0,71, distinto instrumento da entre -0,18 y +0,11. No es equivalente —dos
estrategias sobre el mismo mercado PUEDEN ser opuestas, una de tendencia y una
de reversión— pero como filtro barato acierta casi siempre y no cuesta un
backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

#: Desde dónde dos estrategias se consideran gemelas.
#:
#: 0,5 y no 0,8: con 0,8 los dos pares que encontramos —0,71 y 0,64— pasarían
#: como si fueran diversificación, que es exactamente el error que esto viene a
#: evitar. Y no 0,3, porque a ese nivel el ruido de dos meses de datos ya
#: alcanza para marcar cosas que no tienen nada que ver.
GEMELAS_DESDE = 0.5

#: Cuántos días en común hacen falta para que la correlación signifique algo.
#: Con veinte, dos días malos compartidos la mandan a 0,6 sin que haya
#: ninguna relación.
DIAS_MINIMOS = 40


def a_diario(equity: pd.Series) -> pd.Series:
    """La curva de capital como rendimiento diario, lista para correlacionar.

    El índice se lleva a UTC siempre: un dataset con zona horaria y otro sin
    ella no se pueden alinear, y pandas lo dice con un error que no menciona
    la zona horaria por ningún lado.
    """
    idx = equity.index
    if getattr(idx, "tz", None) is None:
        equity = equity.tz_localize("UTC")
    else:
        equity = equity.tz_convert("UTC")
    return equity.resample("1D").last().pct_change().dropna()


@dataclass
class Parecido:
    """Qué tan parecida es una estrategia a las que ya están corriendo."""

    #: La correlación más alta contra cualquiera de las actuales.
    maxima: float = 0.0
    #: Con cuál.
    con: str = ""
    #: Cuántos días se pudieron comparar.
    dias: int = 0
    #: Si alcanza para opinar. Con pocos días en común, la correlación es ruido.
    medible: bool = False

    @property
    def es_gemela(self) -> bool:
        return self.medible and abs(self.maxima) >= GEMELAS_DESDE


def matriz(curvas: dict[str, pd.Series]) -> pd.DataFrame:
    """La correlación de todos contra todos, sobre los días que comparten."""
    if len(curvas) < 2:
        return pd.DataFrame()
    return pd.DataFrame({k: a_diario(v) for k, v in curvas.items()}).dropna().corr()


def gemelas(curvas: dict[str, pd.Series],
            umbral: float = GEMELAS_DESDE) -> list[tuple[str, str, float]]:
    """Los pares que se mueven juntos, del más parecido al menos.

    Es lo que se le muestra a alguien que tiene una cartera armada: no "está
    diversificada" o "no", sino CUÁLES son el problema.
    """
    c = matriz(curvas)
    if c.empty:
        return []
    pares = [(a, b, float(c.loc[a, b]))
             for i, a in enumerate(c) for b in list(c)[i + 1:]]
    return sorted([p for p in pares if abs(p[2]) >= umbral],
                  key=lambda p: -abs(p[2]))


def parecido_a(candidata: pd.Series,
               actuales: dict[str, pd.Series]) -> Parecido:
    """Cuánto se parece una estrategia nueva a las que ya están corriendo.

    Es lo que el ciclo consulta antes de promover. Sin esto promueve por orden
    de llegada, y si un día encuentra tres estrategias buenísimas de Bitcoin
    promueve las tres.
    """
    if not actuales:
        # La primera nunca es gemela de nada, y decir que sí la dejaría
        # afuera para siempre.
        return Parecido(medible=True)

    nueva = a_diario(candidata)
    peor = Parecido()
    for nombre, curva in actuales.items():
        juntas = pd.DataFrame({"n": nueva, "a": a_diario(curva)}).dropna()
        if len(juntas) < DIAS_MINIMOS:
            continue
        r = float(juntas["n"].corr(juntas["a"]))
        if np.isnan(r):
            continue
        if not peor.medible or abs(r) > abs(peor.maxima):
            peor = Parecido(maxima=round(r, 3), con=nombre,
                            dias=len(juntas), medible=True)
    return peor


def por_instrumento(estrategias: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Qué estrategias hay por instrumento. El atajo barato.

    No reemplaza a la correlación —dos sobre el mismo mercado pueden ser
    opuestas— pero contesta gratis la pregunta que más veces acierta.
    """
    salida: dict[str, list[str]] = {}
    for e in estrategias:
        clave = str((e.get("meta") or {}).get("dataset_id")
                    or e.get("dataset_id") or "")
        if clave:
            salida.setdefault(clave, []).append(str(e.get("id") or e.get("name")))
    return salida
