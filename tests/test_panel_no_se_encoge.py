"""Que el panel de configuración no se convierta en una ranura al scrollear.

EL SÍNTOMA, reportado por un usuario: minó veinticinco estrategias, bajó a
mirarlas, y el panel de configuración quedó de 148px con una caja usable de
DOCE píxeles adentro. "No puedo verlo correctamente, sólo scrollear en él,
pero se ve como muy chiquito."

LA CAUSA. El panel es pegajoso y tiene un `max-height: calc(100vh - hueco)`
para que el botón de arrancar no quede fuera de la ventana. Ese hueco lo mide
la aplicación. La medición sumaba `getBoundingClientRect().top` —que YA viene
con el scroll descontado— MÁS el `scrollTop` del contenedor, contándolo dos
veces; y como al pegarse el borde superior se clava en cero, la suma pasaba a
ser el scroll entero. Cuanto más bajabas, más se encogía.

LO QUE HACE ESTA PRUEBA DISTINTA. El primer arreglo cambió el rectángulo por
`offsetTop` creyéndolo geometría de maquetado. NO LO ES en un elemento
pegajoso: Chrome devuelve la posición desplazada —192 sin scroll, 730 con el
contenedor bajado 698— así que el bug seguía igual y sólo lo tapaba el tope de
seguridad. Por eso acá no alcanza con prohibir `scrollTop`: hay que exigir que
se mida un ancestro NO pegajoso, que es lo único estable.

Medido después del arreglo, minando 25 sobre SP500 a 1576x900: el panel queda
en 578px con 398px de caja, idéntico a cualquier altura de scroll, en 1576x900,
1366x768 y 1280x720.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
APP = (RAIZ / "ui" / "app.js").read_text(encoding="utf-8")


def _cuerpo() -> str:
    i = APP.index("function medirHuecoDelPanel()")
    return APP[i:APP.index("\n}", i)]


def test_la_medicion_no_puede_depender_de_lo_scrolleado_que_este():
    """Ni `offsetTop` ni el rectángulo del panel: los dos se mueven con el scroll.

    El panel es pegajoso, así que su propia posición deja de describir dónde
    empieza en el maquetado en cuanto se pega. Lo que hay que medir es un
    ancestro que no sea pegajoso.
    """
    cuerpo = _cuerpo()
    assert 'position) === "sticky"' in cuerpo or "position === \"sticky\"" in cuerpo, (
        "la medición ya no busca un ancestro no pegajoso; sin eso vuelve a medir "
        "un elemento cuya posición se desplaza al pegarse")
    assert not re.search(r"panel\.offsetTop|panel\.getBoundingClientRect\(\)\.top", cuerpo), (
        "volvió a medir el panel mismo: siendo pegajoso, tanto su rectángulo "
        "como su offsetTop devuelven la posición desplazada, no la de maquetado")


def test_el_scroll_no_se_puede_sumar_dos_veces():
    """El error original, en una línea.

    `getBoundingClientRect().top` ya viene con el scroll descontado. Sumarle
    `scrollTop` lo cuenta dos veces. Sólo es válido cuando se resta antes la
    posición del contenedor, que es lo que convierte la coordenada de ventana
    en coordenada de contenido.
    """
    cuerpo = _cuerpo()
    if "scrollTop" not in cuerpo:
        return
    assert "cont.getBoundingClientRect().top" in cuerpo, (
        "se suma scrollTop sin restar la posición del contenedor: eso cuenta "
        "el scroll dos veces, que es exactamente el bug que dejó el panel en "
        "doce píxeles de alto")


def test_un_error_de_medicion_no_puede_romper_la_pantalla():
    """La red de seguridad, que es lo que faltaba.

    Ya salvó una vez: con el segundo intento todavía roto, el tope evitó que
    el panel volviera a 148px y lo dejó en 450. Una medición equivocada tiene
    que degradar el ajuste, no dejar la configuración inutilizable.
    """
    cuerpo = _cuerpo()
    assert "Math.min" in cuerpo and "innerHeight" in cuerpo, (
        "desapareció el tope contra la altura de la ventana; sin él, cualquier "
        "medición equivocada vuelve a poder encoger el panel hasta romperlo")


def test_el_limite_de_altura_sigue_estando():
    """Y el motivo por el que el hueco existe.

    Sin `max-height` el panel crece entero y el botón de arrancar se va abajo
    de la ventana: medido a 1366x768 caía en y=765 y no se alcanzaba ni
    scrolleando, porque el panel es pegajoso y se detiene.
    """
    css = (RAIZ / "ui" / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.setup\s*\{[^}]*max-height:\s*calc\(100vh\s*-\s*var\(--setup-hueco",
                     css, re.S), (
        "se fue el max-height del panel: sin él el botón de arrancar vuelve a "
        "quedar fuera de la ventana en pantallas de laptop")
