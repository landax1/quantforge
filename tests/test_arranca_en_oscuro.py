"""La aplicación abre SIEMPRE en oscuro (3 de septiembre de 2026).

El claro sigue existiendo, pero dura la sesión: no se guarda como
preferencia. El usuario lo pidió con todas las letras después de que una
preferencia "claro" guardada en el navegador dejara la aplicación en blanco
al abrir.
"""

from __future__ import annotations

import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
INDEX = (RAIZ / "ui" / "index.html").read_text(encoding="utf-8")
APP = (RAIZ / "ui" / "app.js").read_text(encoding="utf-8")


def test_el_arranque_pone_oscuro_y_borra_lo_guardado():
    assert 'localStorage.removeItem("qf.theme")' in INDEX
    assert 'setAttribute("data-theme", "dark")' in INDEX
    assert 'applyTheme("dark", false)' in APP


def test_el_claro_no_se_guarda():
    assert 'localStorage.setItem("qf.theme"' not in APP
