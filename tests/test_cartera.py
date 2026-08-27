"""¿Lo que voy a encender se parece a lo que ya tengo corriendo?

Es la pregunta que separa un portafolio de la misma apuesta con cinco nombres.
Los números que motivan este archivo salieron de las cinco que el ciclo puso en
práctica de verdad: correlación mediana -0,057, pero dos pares en +0,71 y +0,64
por operar el mismo instrumento.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.cartera import (DIAS_MINIMOS, GEMELAS_DESDE, a_diario, gemelas,
                               matriz, parecido_a, por_instrumento)


def _curva(n: int = 120, semilla: int = 0, tz: str | None = "UTC") -> pd.Series:
    """Una curva de capital con ruido propio."""
    r = np.random.default_rng(semilla)
    idx = pd.date_range("2026-01-01", periods=n, freq="1D", tz=tz)
    return pd.Series(10_000 * np.cumprod(1 + r.normal(0.001, 0.01, n)), index=idx)


def _gemela_de(base: pd.Series, ruido: float = 0.001, semilla: int = 9) -> pd.Series:
    """Otra curva que se mueve casi igual."""
    r = np.random.default_rng(semilla)
    return base * (1 + r.normal(0, ruido, len(base))).cumprod()


# ------------------------------------------------- rendimientos, no capital

def test_compara_rendimientos_DIARIOS_y_no_curvas_de_capital():
    """Dos curvas que suben correlacionan altísimo por la tendencia común
    aunque operen en momentos completamente distintos.

    Eso no dice nada sobre si se van a caer juntas, que es la pregunta.
    """
    a, b = _curva(200, 1), _curva(200, 2)
    corr_capital = a.corr(b)
    corr_diaria = matriz({"a": a, "b": b}).loc["a", "b"]
    assert abs(corr_diaria) < abs(corr_capital), (
        "la correlación de las curvas infla el parecido")


def test_alinea_zonas_horarias_distintas():
    """Un dataset con zona horaria y otro sin ella no se pueden juntar, y
    pandas lo dice con un error que no menciona la zona horaria."""
    con, sin = _curva(120, 1, tz="UTC"), _curva(120, 2, tz=None)
    c = matriz({"con": con, "sin": sin})
    assert not c.empty


# --------------------------------------------------------------- las gemelas

def test_encuentra_a_las_que_se_mueven_juntas():
    base = _curva(200, 1)
    pares = gemelas({"a": base, "gemela": _gemela_de(base), "otra": _curva(200, 7)})
    assert pares, "no encontró el par obvio"
    assert set(pares[0][:2]) == {"a", "gemela"}
    assert pares[0][2] > GEMELAS_DESDE


def test_dos_independientes_no_son_gemelas():
    assert gemelas({"a": _curva(200, 1), "b": _curva(200, 99)}) == []


def test_el_umbral_deja_pasar_lo_que_encontramos_de_verdad():
    """0,5 y no 0,8.

    Con 0,8 los dos pares reales —0,71 y 0,64— pasarían como si fueran
    diversificación, que es exactamente el error que esto viene a evitar.
    """
    assert GEMELAS_DESDE <= 0.64, "dejaría pasar los gemelos que ya medimos"
    assert GEMELAS_DESDE >= 0.4, "más abajo empieza a marcar ruido"


def test_la_matriz_vacia_no_revienta():
    assert matriz({}).empty
    assert matriz({"sola": _curva()}).empty
    assert gemelas({"sola": _curva()}) == []


# ------------------------------------------------- contra las que ya corren

def test_la_primera_nunca_es_gemela_de_nada():
    """Decir que sí la dejaría afuera para siempre: sin cartera no hay con
    qué compararla."""
    p = parecido_a(_curva(), {})
    assert p.medible
    assert not p.es_gemela


def test_detecta_que_la_candidata_duplica_algo_que_ya_corre():
    base = _curva(200, 1)
    p = parecido_a(_gemela_de(base), {"vieja": base, "otra": _curva(200, 5)})
    assert p.es_gemela
    assert p.con == "vieja"


def test_una_candidata_distinta_pasa():
    p = parecido_a(_curva(200, 42), {"vieja": _curva(200, 1)})
    assert p.medible
    assert not p.es_gemela


def test_se_queda_con_la_PEOR_y_no_con_el_promedio():
    """Basta con parecerse a UNA para no aportar nada.

    Un promedio bajo esconde un par de 0,9 detrás de tres de 0,0, y encender
    la cuarta copia de algo que ya corre no es diversificar.
    """
    base = _curva(200, 1)
    p = parecido_a(_gemela_de(base),
                   {"a": _curva(200, 3), "b": _curva(200, 4), "clon": base})
    assert p.con == "clon"


# ----------------------------------------------- cuando no se puede opinar

def test_con_pocos_dias_en_comun_no_opina():
    """Con veinte días, dos jornadas malas compartidas la mandan a 0,6 sin que
    haya ninguna relación."""
    corta = _curva(DIAS_MINIMOS - 20, 1)
    p = parecido_a(corta, {"vieja": _curva(DIAS_MINIMOS - 20, 2)})
    assert not p.medible
    assert not p.es_gemela


def test_no_medible_no_es_lo_mismo_que_no_gemela():
    """Son dos respuestas distintas y la pantalla tiene que poder
    distinguirlas: "no se parece" y "todavía no sé" llevan a decisiones
    opuestas."""
    p = parecido_a(_curva(10, 1), {"v": _curva(10, 2)})
    assert not p.medible
    assert p.dias == 0


# ------------------------------------------------------------- el atajo

def test_agrupa_por_instrumento():
    """Medido: mismo instrumento da 0,64 a 0,71; distinto da entre -0,18 y
    +0,11. Como filtro barato acierta casi siempre y no cuesta un backtest."""
    g = por_instrumento([
        {"id": "1", "meta": {"dataset_id": "btc"}},
        {"id": "2", "meta": {"dataset_id": "btc"}},
        {"id": "3", "meta": {"dataset_id": "sp500"}},
    ])
    assert g["btc"] == ["1", "2"]
    assert g["sp500"] == ["3"]


def test_las_que_no_dicen_su_instrumento_no_se_agrupan_en_falso():
    """Meterlas todas en una clave vacía las haría parecer gemelas entre sí."""
    g = por_instrumento([{"id": "1", "meta": {}}, {"id": "2"}])
    assert g == {}
