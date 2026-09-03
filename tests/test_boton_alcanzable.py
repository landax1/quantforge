"""Que el botón de arrancar la búsqueda sea alcanzable en cualquier ventana.

Esta prueba existe por un error que dejaba la aplicación inutilizable en la
resolución de laptop más común del mundo. Medido a 1366x768:

    el panel de configuración arrancaba en y=186 y medía 640  →  terminaba en 826
    la ventana medía 768
    el botón "Iniciar minado" quedaba en y=765

Tres píxeles visibles. Y no se arreglaba scrolleando: el panel es
``position: sticky`` con ``top: 0``, así que se detiene y el botón se queda
donde está. Comprobado en cuatro posiciones de scroll, la máxima incluida:
nunca visible.

La causa era un número fijo. El CSS limitaba el panel con
``calc(100vh - 60px)``, y ese 60 asumía que empezaba pegado al borde; empieza a
186, porque arriba tiene el título de la pantalla y la pastilla de contexto.
Sobraban 126 píxeles que nadie restaba.

No se puede medir el navegador desde acá, así que lo que se comprueba es que la
forma de calcularlo siga siendo *medida* y no *supuesta*: el día que alguien
vuelva a poner un número fijo, esto lo encuentra.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CSS = (RAIZ / "ui" / "styles.css").read_text(encoding="utf-8")
APP = (RAIZ / "ui" / "app.js").read_text(encoding="utf-8")


def test_el_panel_se_limita_con_el_hueco_medido():
    """Nada de números fijos: el hueco lo mide la aplicación.

    Se mira la regla base —la de la columna al costado—, no la de pantallas
    angostas: ahí el panel pasa al flujo normal y el tope se levanta a
    propósito (ver la prueba de más abajo).
    """
    base = CSS.split("@media (max-width: 1180px)")[0]
    m = re.search(r"\.setup\s*\{[^}]*?max-height:\s*([^;]+);", base, re.S)
    assert m, "el panel de configuración tiene que tener un límite de altura"
    regla = m.group(1)
    assert "--setup-hueco" in regla, (
        f"el límite del panel es '{regla.strip()}'. Tiene que salir de la variable "
        "que mide la aplicación: un número fijo asume dónde empieza el panel, y "
        "cuando cambia el encabezado el botón de arrancar se sale de la ventana.")


def test_la_medicion_existe_y_se_llama_al_dibujar():
    assert "function medirHuecoDelPanel" in APP, (
        "sin la medición, el panel usa el valor de respaldo y en pantallas bajas "
        "el botón de arrancar queda fuera")
    # se llama al dibujar la pantalla, no sólo al definirla
    llamadas = len(re.findall(r"\bmedirHuecoDelPanel\(\)", APP))
    assert llamadas >= 2, (
        f"medirHuecoDelPanel se nombra {llamadas} vez/veces: hace falta definirla "
        "Y llamarla cuando el panel ya está en pantalla")


def test_se_recalcula_al_cambiar_el_tamano():
    """Alguien que achica la ventana no puede quedarse sin botón."""
    assert re.search(r'addEventListener\(\s*"resize"', APP), (
        "el hueco tiene que recalcularse al cambiar el tamaño de la ventana")


def test_en_angosto_el_boton_queda_pegado_abajo():
    """En angosto el panel crece, pero el botón de arrancar no se va con él.

    Durante un tiempo el panel conservó el tope de alto de la columna también
    cuando pasaba al flujo normal. Medido el 3 de septiembre de 2026: a 1.024
    px de ancho eso dejaba 205 px de ventana para 4.319 px de panel, o sea un
    buzón con scroll propio. Levantar el tope sin más devolvía el problema
    original —el botón al final de un panel larguísimo—, así que el botón se
    queda pegado al borde de abajo y siempre está a un clic.
    """
    bloque = CSS.split("@media (max-width: 1180px) {", 1)[1].split(chr(10) + "}", 1)[0]
    assert "#m-run" in bloque and "position: sticky" in bloque, (
        "en pantallas angostas el botón de arrancar tiene que quedar pegado "
        "abajo: sin eso queda al final de un panel de cuatro mil píxeles")
