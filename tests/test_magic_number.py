"""El número que separa un bot de otro en la misma cuenta de MetaTrader.

Es el bloqueante de todo lo que sea operar varias estrategias a la vez, y era
un valor fijo: TODOS los EA exportados salían con 770001.

MetaTrader no tiene otra forma de saber de quién es una posición. Cada EA marca
sus órdenes con su Magic Number y después filtra por él. Dos con el mismo
número creen cada uno que las posiciones del otro son suyas: uno cierra lo que
el otro abrió, y ninguno de los dos da error. La forma de enterarse era ver
operaciones cerrándose solas.
"""

from __future__ import annotations

import pytest

from botiquant.core.models import StrategySpec
from botiquant.reports.mql5 import export_mql5, magic_de


def _spec() -> StrategySpec:
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return StrategySpec.from_dict({
        "name": "x", "direction": "long",
        "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
        "risk": {"stop_type": "atr", "stop_value": 2.0,
                 "target_type": "atr", "target_value": 4.0},
    })


def test_dos_estrategias_distintas_no_comparten_numero():
    """La prueba que justifica todo el cambio.

    Con el número compartido, poner dos bots de Botiquant en una cuenta no
    funcionaba — y fallaba operando, no al exportar.
    """
    assert magic_de("BQ_S_657") != magic_de("BQ_S_1249")


def test_la_misma_estrategia_da_siempre_el_mismo_numero():
    """Determinista a propósito.

    Si cambiara al reexportar, el EA nuevo no reconocería la posición que dejó
    abierta el viejo: la trataría como ajena y quedaría huérfana, sin nadie que
    la gestione ni la cierre.
    """
    assert magic_de("BQ_S_657") == magic_de("BQ_S_657")


def test_no_quedan_dos_iguales_en_un_lote_grande():
    """Veinticuatro bits alcanzan para dieciséis millones sin repetir; esto
    comprueba que la mezcla no los amontone en un rincón."""
    nombres = [f"BQ_S_{i}" for i in range(2000)]
    assert len({magic_de(n) for n in nombres}) == 2000


def test_el_numero_no_choca_con_los_de_otros_programas():
    """Muchos EA comerciales usan 1, 100, 12345 y otros valores redondos.

    Un choque con uno de esos tiene el mismo efecto que un choque entre dos
    nuestros, y es más difícil de sospechar porque el otro programa no es
    nuestro.
    """
    for n in ("BQ_S_1", "BQ_S_999", "otra"):
        m = magic_de(n)
        assert m > 770_000_000
        assert m not in (1, 100, 12345, 770001)


def test_ya_no_sale_el_numero_fijo_de_antes():
    """770001 estaba en TODOS los exportados. Si vuelve, vuelve el problema."""
    code = export_mql5(_spec(), ea_name="BQ_S_657")
    assert "InpMagic       = 770001;" not in code
    assert f"InpMagic       = {magic_de('BQ_S_657')};" in code


def test_dos_exportaciones_distintas_traen_numeros_distintos():
    a = export_mql5(_spec(), ea_name="BQ_S_657")
    b = export_mql5(_spec(), ea_name="BQ_S_1249")
    linea = lambda c: [l for l in c.splitlines() if "InpMagic" in l][0]
    assert linea(a) != linea(b)


def test_sigue_siendo_editable_por_el_usuario():
    """Va como `input`, no como constante.

    Alguien puede tener ya una cuenta con Magic Numbers asignados a mano y
    necesitar encajar el nuestro en su esquema. Clavarlo le rompería eso.
    """
    assert "input long   InpMagic" in export_mql5(_spec(), ea_name="BQ_S_657")
