"""Tres lugares donde la pantalla decía una cosa y hacía otra (3 de septiembre).

Se prueban sobre el código de la interfaz porque no hay navegador en la
suite; lo que se comprueba es que las tres reglas sigan escritas donde van.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "ui"
APP = (RAIZ / "app.js").read_text(encoding="utf-8")
I18N = (RAIZ / "i18n.js").read_text(encoding="utf-8")


def test_el_numero_se_escribe_antes_de_animarlo():
    """`requestAnimationFrame` no corre en una pestaña oculta ni en una
    ventana en segundo plano: la cifra quedaba en el "0" del marcador para
    siempre —"Saldo 0 · Resultado neto 0", "Arriesga ≈ 0.00 USDT"— con la
    frase de al lado diciendo los valores reales."""
    cuerpo = APP[APP.index("function animarCifras"):]
    cuerpo = cuerpo[:cuerpo.index("\n}\n")]
    escribe = cuerpo.index("el.textContent = fmt(fin);")
    anima = cuerpo.index("requestAnimationFrame(paso)")
    assert escribe < anima, (
        "el valor final tiene que escribirse ANTES de arrancar la animación: "
        "si el cuadro nunca llega, el número queda en cero")


def test_en_pausa_el_panel_lo_dice():
    """El botón cambiaba a "Seguir" y el panel seguía titulando "Buscando
    estrategias" con el contador congelado."""
    assert '"run.pausada"' in I18N
    assert re.search(r'S\.minePaused \? t\("run\.pausada"\)', APP), (
        "el título del panel tiene que mirar si la búsqueda está en pausa")
    # y se repinta al pausar, porque en pausa nadie vuelve a dibujar el panel
    pintar = APP[APP.index("function pintarPausa"):]
    pintar = pintar[:pintar.index("\n}\n")]
    assert "run.pausada" in pintar


def test_la_receta_puesta_vuelve_tras_recargar():
    """Los valores de la receta volvían pero la marca de cuál era sólo se
    restituía al cambiar de mercado: recargar dejaba el plan con los números
    de "dormir tranquilo" y ninguna tarjeta encendida."""
    i = APP.index("aplicarVentanaPorDefecto(curDs);")
    antes = APP[max(0, i - 1200):i]
    assert "qf.cfg_mercado" in antes and "S.recetaPuesta = g.receta" in antes, (
        "al dibujar Buscar hay que recuperar qué receta estaba puesta en este mercado")


def test_databank_se_llama_encontradas_en_castellano():
    m = re.search(r'"nav\.bank":\s*\["([^"]+)",\s*"([^"]+)"\]', I18N)
    assert m and m.group(2) == "Encontradas", (
        "la solapa se llama Encontradas y el rótulo decía Databank en castellano")


def test_la_relacion_riesgo_beneficio_cabe_en_su_frase():
    """Va dentro de 'a <b>{rr}</b> risk/reward': "anywhere from 1:0.5 to
    1:0.75" dejaba la frase en "a anywhere from…"."""
    m = re.search(r'"rr\.varias":\s*\["([^"]+)"', I18N)
    assert m and not m.group(1).lower().startswith(("anywhere", "a ", "an ")), m.group(1)


def test_mandar_a_probar_no_arranca_ninguna_prueba():
    """"Cuando minan las estrategias, después se pasan el test solas y se
    rompe la plataforma" (el usuario, 3 de septiembre de 2026). Guardar
    encolaba el walk-forward de cada una; ahora sólo las deja en Probar y
    probar es un botón."""
    cuerpo = APP[APP.index("function encolarPruebas"):]
    cuerpo = cuerpo[:cuerpo.index(chr(10) + "}" + chr(10))]
    assert "probarVarias(" not in cuerpo and "COLA_PENDIENTE" not in cuerpo, (
        "mandar a Probar volvió a arrancar pruebas por su cuenta")
