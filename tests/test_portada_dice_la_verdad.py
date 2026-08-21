"""Que el número de la portada siga siendo cierto cuando cambie el motor.

La portada dice "busca entre **245 millones** de combinaciones". Ese número no
es decorativo: sale de contar las plantillas del generador, y va a cambiar el
día que se agregue un disparador o un filtro — que está en la lista de cosas
por hacer.

Un número inventado en una portada es una mentira chica que nadie descubre. Un
número que ERA cierto y quedó viejo es la misma mentira, con la diferencia de
que se puede evitar sola. Esto lo evita.

Antes decía "prueba millones de combinaciones", que leído literal tampoco era
cierto: la aplicación prueba hasta veinte mil candidatas por corrida. Lo que
tiene millones es el espacio del que las saca. El verbo importa tanto como el
número.
"""

from __future__ import annotations

import itertools
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PORTADA = RAIZ / "landing" / "index.html"


def _combinaciones(plantilla) -> int:
    """Cuántos juegos de parámetros distintos admite una plantilla."""
    total = 1
    for gen in plantilla.genes:
        paso = gen.step or 1
        total *= max(1, int((gen.max - gen.min) / paso) + 1)
    return total


def espacio_de_busqueda() -> int:
    """Combinaciones de reglas: un disparador y hasta dos filtros."""
    from botiquant.generator.templates import drivers, filters

    disparadores = sum(_combinaciones(t) for t in drivers())
    porfiltro = [_combinaciones(t) for t in filters()]
    # sin filtro, con uno, o con dos distintos
    combinaciones_de_filtros = (
        1 + sum(porfiltro) + sum(a * b for a, b in itertools.combinations(porfiltro, 2)))
    return disparadores * combinaciones_de_filtros


def test_el_numero_de_la_portada_sigue_siendo_cierto():
    """Si esto falla, se agregó un bloque y la portada quedó vieja.

    No es un error: es el recordatorio de actualizar el número, que ahora es
    más grande y por lo tanto una mejor noticia.
    """
    texto = PORTADA.read_text(encoding="utf-8")
    m = re.search(r"busca entre <b>(\d+) millones</b>", texto)
    assert m, "la portada tiene que decir el tamaño del espacio de búsqueda"

    dicho = int(m.group(1)) * 1_000_000
    real = espacio_de_busqueda()

    # se redondea hacia abajo a millones, así que el dicho nunca puede pasarse
    assert dicho <= real, (
        f"la portada dice {dicho:,} y el espacio real es {real:,}: está exagerando")
    # y tampoco puede quedarse tan corto que deje de significar algo
    assert dicho >= real * 0.9, (
        f"la portada dice {dicho:,} y el espacio real ya es {real:,}. Se agregaron "
        f"bloques: actualizá el número a {real // 1_000_000} millones.")


def test_la_portada_no_dice_que_prueba_todas():
    """El verbo importa tanto como el número.

    La aplicación PRUEBA hasta veinte mil candidatas por corrida; lo que tiene
    millones es el espacio del que las saca. "Prueba millones" es una
    exageración chica, y en un producto que se vende por no mentirle al usuario
    sobre sus resultados, la primera línea de la portada no puede ser la que
    exagera.
    """
    texto = PORTADA.read_text(encoding="utf-8")
    assert "prueba millones" not in texto.lower(), (
        "la aplicación no prueba millones de combinaciones: busca entre ellas")
