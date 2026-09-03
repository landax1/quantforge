"""Combinar un perpetuo con un CFD: el caso para el que existe el portafolio.

Un perpetuo trae las marcas de tiempo con zona horaria y un CFD no. Combinar
ADA con el S&P 500 reventaba con ``TypeError: Cannot join tz-naive with
tz-aware DatetimeIndex``, crudo en pantalla, encontrado el 3 de septiembre de
2026 por una usuaria de prueba que verificaba números.

Duele más de lo que parece: mezclar mercados que no se mueven juntos es
exactamente lo que un portafolio tiene que poder hacer, y era justo lo que
fallaba. Dos estrategias de cripto andaban; dos mundos distintos, no.
"""

from __future__ import annotations

import datetime as dt

from botiquant.portfolio.portfolio import build_portfolio


def _curva(n: int, *, con_zona: bool, paso: float = 3.0) -> dict:
    inicio = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc if con_zona else None)
    return {
        "name": "perpetuo" if con_zona else "cfd",
        "equity": [10_000 + i * paso for i in range(n)],
        "timestamps": [(inicio + dt.timedelta(hours=i)).isoformat() for i in range(n)],
        "initial_capital": 10_000,
    }


def test_un_perpetuo_y_un_cfd_se_combinan():
    r = build_portfolio([_curva(2000, con_zona=True), _curva(2000, con_zona=False)])
    assert len(r["combined_equity"]) > 10
    assert r["metrics"]["avg_correlation"] is not None


def test_el_orden_de_los_dos_no_importa():
    """Que el primero sea el que trae zona horaria no puede cambiar nada."""
    a = build_portfolio([_curva(2000, con_zona=True), _curva(2000, con_zona=False)])
    b = build_portfolio([_curva(2000, con_zona=False), _curva(2000, con_zona=True)])
    assert len(a["combined_equity"]) == len(b["combined_equity"])


def test_dos_con_zona_horaria_siguen_andando():
    r = build_portfolio([_curva(2000, con_zona=True),
                         _curva(2000, con_zona=True, paso=1.5)])
    assert len(r["combined_equity"]) > 10


def test_dos_sin_zona_horaria_siguen_andando():
    r = build_portfolio([_curva(2000, con_zona=False),
                         _curva(2000, con_zona=False, paso=1.5)])
    assert len(r["combined_equity"]) > 10


def test_la_que_no_tiene_historia_en_comun_queda_nombrada():
    """Sin días compartidos la curva se arma igual —una de las dos queda
    planchada por el relleno hacia adelante— y eso no se puede mostrar como
    si fuera un conjunto que funcionó. El portafolio la nombra en
    `sin_datos` y la pantalla la pone en un cartel de aviso.

    No se levanta un error a propósito: con tres estrategias, que una no
    solape no tiene por qué tirar abajo a las otras dos.
    """
    lejos = _curva(2000, con_zona=False)
    lejos["name"] = "la de 2030"
    lejos["timestamps"] = [(dt.datetime(2030, 1, 1) + dt.timedelta(hours=i)).isoformat()
                           for i in range(2000)]
    r = build_portfolio([_curva(2000, con_zona=True), lejos])
    assert r["sin_datos"], (
        "nadie avisa que una de las dos no tiene un solo día en común con la "
        "otra: la curva sale igual y se lee como un conjunto que funcionó")
