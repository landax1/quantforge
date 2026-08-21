"""Que lo marcado como oculto no se dibuje.

Salió de un síntoma raro: debajo de los botones de exportar aparecía una caja
verde vacía, con su borde, sin nada adentro. El código la tenía marcada como
oculta —``#insp-guardado`` daba ``hidden: true``— y se veía igual.

La causa es de las que no se ven leyendo el código. El atributo ``hidden`` de
HTML funciona por una regla del navegador que dice ``[hidden] { display: none }``,
y cualquier clase propia que ponga ``display`` le gana por especificidad:
``.guardado { display: flex }`` pesa más. La línea que oculta está ahí, es
correcta, y no hace nada.

Se buscaron todas: ``.barra-sel``, ``.guardado`` y ``.logo-mark`` estaban sin
proteger, mientras que ``.sugerido``, ``.realidad`` y ``.g-destino`` ya tenían
su regla a mano — que es la señal de que el problema venía apareciendo de a uno
y parcheándose de a uno.

Por eso el arreglo es una sola regla global, y por eso esta prueba comprueba que
esa regla siga estando en vez de ir revisando clase por clase.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CSS = (RAIZ / "ui" / "styles.css").read_text(encoding="utf-8")


def test_el_atributo_hidden_le_gana_a_cualquier_clase():
    """Una sola regla, y tiene que ir antes que todo lo demás."""
    m = re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important\s*;?\s*\}", CSS)
    assert m, (
        "falta `[hidden] { display: none !important; }`. Sin eso, cualquier clase "
        "que ponga `display` le gana al atributo y el elemento se sigue dibujando "
        "aunque el código lo marque como oculto — con su borde y su espacio.")


def test_ninguna_clase_que_se_oculta_puede_ganarle_al_atributo():
    """La red de seguridad, por si alguien saca la regla global.

    Recorre las clases que en algún momento se ocultan y comprueba que ninguna
    quede dibujándose. Con la regla global esto pasa siempre; sin ella, vuelve a
    encontrar los tres casos que originaron todo.
    """
    if re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important", CSS):
        return  # la regla global las cubre a todas

    APP = (RAIZ / "ui" / "app.js").read_text(encoding="utf-8")
    INDEX = (RAIZ / "ui" / "index.html").read_text(encoding="utf-8")
    marcado = APP + INDEX

    clases: set[str] = set()
    for patron in (r'<[a-z]+[^>]*class="([^"]+)"[^>]*\bhidden\b',
                   r'<[a-z]+[^>]*\bhidden\b[^>]*class="([^"]+)"'):
        for m in re.finditer(patron, marcado):
            clases.update(m.group(1).split())

    sin_proteger = []
    for cl in sorted(clases):
        pone = re.search(rf"\.{re.escape(cl)}\s*\{{[^}}]*\bdisplay:\s*(?!none)[\w-]+", CSS)
        guarda = re.search(rf"\.{re.escape(cl)}\[hidden\]\s*\{{[^}}]*display:\s*none", CSS)
        if pone and not guarda:
            sin_proteger.append(cl)

    assert not sin_proteger, (
        "estas clases ponen `display` y se usan con el atributo `hidden`, así que "
        f"se siguen dibujando cuando el código las oculta: {sin_proteger}")
