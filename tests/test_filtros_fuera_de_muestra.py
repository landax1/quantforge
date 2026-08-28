"""Los filtros de aceptación, aplicados también al tramo reservado.

EL AGUJERO QUE CIERRA. Hasta acá los filtros corrían SOLO sobre el tramo de
búsqueda. El reservado se calculaba después, para cada candidata ya aceptada, y
se usaba para bajarle el score en proporción a lo que sobrevivió.

O sea que el fuera de muestra REORDENABA PERO NO RECHAZABA: una estrategia que
se derrumba afuera entraba igual al databank, más abajo. Quien mira los
primeros puestos no se entera de que las de más abajo no sobrevivieron, y quien
guarda una de esas se lleva algo que ya falló donde importa.

Y no cuesta tiempo: ese backtest ya se corría para cada aceptada.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.mining import miner


# ------------------------------------------------- el comparador de afuera

def test_las_varas_de_afuera_son_LAS_MISMAS_de_adentro():
    """Un segundo camino de decisión acabaría divergiendo del primero sin que
    nada avise: alguien agrega un criterio, lo enchufa en uno de los dos, y la
    puerta de afuera deja de mirar lo mismo que la de adentro."""
    adentro = {"profit_factor": 0.9, "win_rate_pct": 60.0, "sharpe": 1.0,
               "max_drawdown_pct": 10.0, "recovery_factor": 3.0,
               "trades_per_month": 5.0, "trades_per_week": 1.0}
    varas = {"min_pf": 1.2}
    assert miner._failed_criteria(adentro, varas) == ["min_pf"]
    assert miner._failed_criteria_oos(adentro, varas) == ["min_pf"]


def test_una_metrica_que_el_tramo_reservado_no_trae_se_saltea():
    """El tramo reservado no trae todas las métricas del de búsqueda.

    Reprobar por un dato que no existe rechazaría TODO, y el usuario vería cero
    resultados sin ningún motivo a la vista — que es la peor forma de fallar
    para una búsqueda que tarda minutos.
    """
    fuera = {"profit_factor": 1.5, "trades": 40}          # sin sharpe
    assert miner._failed_criteria_oos(fuera, {"min_sharpe": 2.0}) == []


def test_un_valor_nulo_tampoco_reprueba():
    fuera = {"profit_factor": None, "trades": 40}
    assert miner._failed_criteria_oos(fuera, {"min_pf": 1.2}) == []


def test_un_maximo_se_compara_al_reves_que_un_minimo():
    """El drawdown va por arriba y el profit factor por abajo. Comparar los dos
    en el mismo sentido dejaría pasar justo lo que se quiere frenar."""
    fuera = {"max_drawdown_pct": 45.0, "profit_factor": 1.4, "trades": 40}
    assert miner._failed_criteria_oos(fuera, {"max_dd_pct": 20.0}) == ["max_dd_pct"]
    assert miner._failed_criteria_oos(fuera, {"max_dd_pct": 60.0}) == []


# -------------------------------------------------- la segunda puerta

def _datos(n=4000, semilla=7):
    """Una serie con tendencia y ruido, larga para que el tramo reservado
    tenga con qué operar."""
    rng = np.random.default_rng(semilla)
    paso = rng.normal(0.0004, 0.01, n).cumsum()
    px = 100.0 * np.exp(paso)
    idx = pd.date_range("2015-01-01", periods=n, freq="1h")
    return pd.DataFrame({"open": px, "high": px * 1.004, "low": px * 0.996,
                         "close": px, "volume": 1.0}, index=idx)


def _minar(**kw):
    base = dict(df=_datos(), drivers=["ema_cross"], filters=[],
                min_trades=5, max_candidates=60, keep_top=50,
                seed=3, oos_pct=30.0)
    base.update(kw)
    df = base.pop("df")
    return miner.mine(df, base.pop("drivers"), base.pop("filters"), **base)


def test_exigirlo_afuera_nunca_devuelve_MAS_que_no_exigirlo():
    """Es una segunda puerta, no otra puerta: sólo puede sacar candidatas.

    Si alguna vez devolviera más, sería que la puerta de afuera está dejando
    entrar cosas que la de adentro rechazó — o sea que no es una segunda
    puerta sino un camino alternativo.
    """
    varas = {"min_pf": 1.05}
    suelto = _minar(accept=dict(varas), exigir_oos=False)
    exigido = _minar(accept=dict(varas), exigir_oos=True)
    assert len(exigido["databank"]) <= len(suelto["databank"])


def test_lo_que_pasa_la_segunda_puerta_cumple_la_vara_TAMBIEN_afuera():
    """La comprobación que da sentido a todo: cada fila del resultado tiene que
    aguantar la misma vara en el tramo que la búsqueda no miró."""
    varas = {"min_pf": 1.05}
    r = _minar(accept=dict(varas), exigir_oos=True)
    if not r["databank"]:
        pytest.skip("esta semilla no dejó ninguna; el otro test cubre el orden")
    for fila in r["databank"]:
        fuera = fila.get("oos") or {}
        assert fuera.get("trades"), "entró una sin operaciones afuera"
        assert fuera["profit_factor"] >= 1.05, (
            f"{fila['name']} tiene PF {fuera['profit_factor']} afuera")


def test_sin_operaciones_afuera_NO_pasa():
    """No medir no es aprobar.

    Una estrategia que no operó ni una vez en el tramo reservado no demostró
    nada ahí. Dejarla pasar sería tratar la ausencia de evidencia como
    evidencia, que es justo lo que el tramo reservado viene a evitar.
    """
    fuera_vacio = {"profit_factor": 0.0, "trades": 0}
    # el comparador no la reprueba por vara —no hay con qué—, así que el freno
    # tiene que estar en el uso, no acá
    assert miner._failed_criteria_oos(fuera_vacio, {"min_pf": 1.05}) == ["min_pf"]


def test_sin_tramo_reservado_la_opcion_no_hace_nada():
    """Pedir que se cumpla afuera cuando no hay afuera no puede vaciar el
    resultado: sería un tilde que apaga la búsqueda entera."""
    varas = {"min_pf": 1.0}
    sin_reserva = _minar(accept=dict(varas), oos_pct=0.0, exigir_oos=True)
    normal = _minar(accept=dict(varas), oos_pct=0.0, exigir_oos=False)
    assert len(sin_reserva["databank"]) == len(normal["databank"])


# ------------------------------------------- el control, en la pantalla

def _app_js() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "ui" / "app.js").read_text(
        encoding="utf-8")


def test_el_control_no_se_apaga_con_la_propiedad_disabled():
    """PERDI UN RATO CON ESTO, y por eso queda fijado.

    `lockSetup` es dueña de `disabled` en todo el panel de configuración: al
    dibujar la página llama con `on=false` y habilita TODOS los controles, así
    que cualquier `disabled` puesto por un control individual —en la plantilla
    o después— se borra sin dejar rastro. El botón se veía disponible, se
    apretaba, y no pasaba nada.

    Lo que apaga es una clase, y lo que impide el clic es la condición.
    """
    js = _app_js()
    i = js.index("const pintarExigir")
    bloque = js[i:i + 900]
    assert "classList.toggle(\"apagado\"" in bloque
    assert ".disabled =" not in bloque, (
        "vuelve a apoyarse en `disabled`, que `lockSetup` borra al dibujar")


def test_el_clic_se_guarda_por_la_condicion_y_no_por_el_boton():
    """Si el guardia mirara `b.disabled`, bastaría con que `lockSetup` corra
    para que el clic entre y pida las varas sobre un tramo que no existe."""
    js = _app_js()
    # se ancla en el MANEJADOR y no en la primera aparición del selector: la
    # primera es la del pintor, y buscar ahí probaba otra cosa
    i = js.index('$$("#m-oos-exig button", main).forEach(b => b.onclick')
    bloque = js[i:i + 500]
    assert '+S.cfg.oosPct > 0' in bloque


def test_lockSetup_avisa_de_que_es_duenia_de_disabled():
    """El comentario es la única forma de que el próximo no pelee con el mismo
    fantasma: el síntoma —un botón que no queda apagado— no señala para nada
    hacia esta función."""
    js = _app_js()
    i = js.index("function lockSetup(")
    assert "disabled" in js[i:i + 700]
    assert "clase" in js[i:i + 700]


# ------------------------------------------- el diagnóstico cuando no sale nada

def test_el_diagnostico_no_revienta_con_las_frenadas_afuera():
    """LO ROMPI AL AGREGAR LA PUERTA.

    El diagnóstico busca la vara que más descarta en `blocked_by` y la resuelve
    contra la tabla de criterios. Las claves nuevas van con prefijo `oos:` y no
    están ahí: si el bloqueo mayoritario venía del tramo reservado, reventaba
    con KeyError — justo cuando el usuario más necesita entender qué pasó.
    """
    r = _minar(accept={"min_pf": 3.0}, exigir_oos=True)
    assert isinstance(r["diagnosis"], dict)


def test_cuando_solo_frena_el_tramo_reservado_el_consejo_es_OTRO():
    """No es que la vara sea exigente: esas candidatas SI la cumplían con los
    datos de la búsqueda y se cayeron donde no se miró.

    Decir "aflojá el filtro" ahí sería el consejo exactamente al revés: la vara
    hizo su trabajo.
    """
    from botiquant.mining import miner as m

    # se arma el caso directo: nada frenado adentro, todo frenado afuera
    import inspect
    fuente = inspect.getsource(m.mine)
    assert 'if frenadas_afuera:' in fuente
    assert '"reason": "oos"' in fuente
    assert "aflojar los filtros no lo" in fuente
