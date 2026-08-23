"""Las categorías configuran la búsqueda entera, no sólo los filtros.

Es LA regla de estas recetas, y sale de una medición: pedir win rate ≥ 60% con
el R:B 1:2 de fábrica no devuelve nada nunca. Medido sobre SP500 a una hora,
treinta estrategias por corrida — con 1:2 ninguna llega a 60% de aciertos, con
0,5 lo pasan quince. El techo no lo pone la búsqueda sino la aritmética de la
relación.

Lo mismo con la frecuencia. Medido con cuarenta genomas al azar por celda, en
los cuatro mercados: a 4 horas la mediana ronda 0,9 operaciones por semana y
NINGUNO de los cuarenta llega a cinco; a 30 minutos la mediana es 7 y lo pasan
veintiséis; a 15 minutos la mediana es 14 y lo pasan treinta. Una categoría
para cuentas de fondeo que no baje la temporalidad pide algo que no existe.

Por eso una receta que sólo toque los filtros está rota aunque parezca
correcta: manda a esperar veinte minutos para no encontrar nada, y quien la
tocó concluye que la aplicación no sirve.
"""

from __future__ import annotations

import re

from botiquant.api.app import UI_DIR

APP = (UI_DIR / "app.js").read_text(encoding="utf-8")
DICC = (UI_DIR / "i18n.js").read_text(encoding="utf-8")


def _recetas() -> dict[str, str]:
    """El id de cada receta y el texto crudo de su configuración."""
    bloque = re.search(r"const RECETAS = \(\) => \[(.*?)\n\];", APP, re.S)
    assert bloque, "no se pudo leer la lista de recetas"
    fuera = {}
    for m in re.finditer(r'id: "(\w+)",.*?cfg: \{(.*?)\n    \},',
                         bloque.group(1), re.S):
        fuera[m.group(1)] = m.group(2)
    assert fuera, "no se pudo leer la configuración de ninguna receta"
    return fuera


def test_cada_receta_toca_mas_que_los_filtros():
    """Temporalidad, complejidad y R:B, no sólo `critOn`.

    Una receta que sólo prende filtros deja la búsqueda mirando donde estaba,
    que es justo donde lo pedido no existe.
    """
    for nombre, cfg in _recetas().items():
        for pieza in ("timeframe:", "maxFilters:", "rrBuscado:"):
            assert pieza in cfg, (
                f"la receta «{nombre}» no fija {pieza.rstrip(':')}. Sin eso "
                "configura los filtros y deja el resto como estaba, que es la "
                "forma de pedir algo que no existe")


def test_la_de_aciertos_baja_el_riesgo_beneficio():
    """La que era imposible hasta que el R:B se pudo buscar.

    Con relaciones de 1 o más, el win rate alto no aparece. Si alguien sube
    estos números, la categoría deja de devolver lo que promete su tarjeta.
    """
    cfg = _recetas()["aciertos"]
    valores = [float(x) for x in
               re.search(r"rrBuscado: \[([^\]]+)\]", cfg).group(1).split(",")]
    assert valores and max(valores) <= 1.0, (
        f"la categoría de aciertos busca R:B {valores}; por encima de 1 el win "
        "rate alto no existe, y la tarjeta estaría prometiendo algo imposible")


def test_la_de_fondeo_no_puede_quedarse_en_temporalidad_alta():
    """A 4 horas, una operación por día no existe en ningún mercado medido."""
    cfg = _recetas()["fondeo"]
    tf = re.search(r'timeframe: "(\w+)"', cfg).group(1)
    assert tf in ("15m", "30m"), (
        f"la categoría de fondeo mina en {tf}. Medido en los cuatro mercados: a "
        "1h la mediana es 3 operaciones por semana y a 4h es 0,9 — hace falta "
        "una por día hábil, que son cinco")


def test_cada_receta_dice_que_cuesta():
    """Todas cuestan algo, y callarlo sería vender lo que la portada no vende."""
    for nombre in _recetas():
        for clave in (f'"rec.{nombre}"', f'"rec.{nombre}_que"', f'"rec.{nombre}_cuesta"'):
            assert clave in DICC, (
                f"falta {clave}: la tarjeta se dibujaría con la clave en crudo")
