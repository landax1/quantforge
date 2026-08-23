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

    Medido corriendo el minero entero dos veces con la misma semilla, mismo
    filtro de calidad —profit factor ≥ 1,15— sobre SP500 a una hora, diez años,
    tope de 1500 candidatas:

        R:B fijo en 1:2   win rate 32,9 .. 52,1   rango 19,2   con ≥55%: 0 de 30
        R:B como gen      win rate 32,5 .. 69,0   rango 36,5   con ≥55%: 2 de 28

    El abanico casi se duplica y el máximo salta de 52% a 69%. Pero fijarse en
    el 2 de 28: dejar que la búsqueda elija entre las ocho relaciones da
    VARIEDAD, no PUNTERÍA. Para que una categoría de aciertos altos devuelva
    algo en un tiempo razonable hay que además sesgar las relaciones hacia
    abajo, que es lo que hace esta receta. Las dos cosas hacen falta.
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


def test_cada_receta_pone_su_propio_tope():
    """Sin tope propio, una receta puede correr horas antes de rendirse.

    Medido: una candidata cuesta 8,3 microsegundos por vela, así que a 30
    minutos son 1,04 segundos y a 15 son 2,08. El tope de fábrica son veinte
    mil candidatas — a 30 minutos, casi seis horas; a 15, once. Nadie espera
    eso, y el peor caso es justo cuando la búsqueda NO encuentra lo que busca,
    que es cuando el usuario ya está desconfiando.
    """
    #: Segundos por candidata, de la medición de velas por temporalidad.
    COSTO = {"15m": 2.08, "30m": 1.04, "1h": 0.51, "4h": 0.13}
    TECHO_MIN = 12
    for nombre, cfg in _recetas().items():
        tope = re.search(r"maxCandidates: (\d+)", cfg)
        assert tope, f"la receta «{nombre}» no fija su tope de candidatas"
        tf = re.search(r'timeframe: "(\w+)"', cfg).group(1)
        minutos = int(tope.group(1)) * COSTO[tf] / 60
        assert minutos <= TECHO_MIN, (
            f"«{nombre}» puede correr {minutos:.0f} minutos en el peor caso "
            f"({tope.group(1)} candidatas a {tf}); el techo son {TECHO_MIN}")


def test_las_recetas_no_pueden_nombrar_perillas_que_no_existen():
    """Un nombre mal escrito en una receta no rompe nada: no hace nada.

    Es el peor tipo de error para esto. `aplicarReceta` copia lo que encuentre
    dentro de `cfg`, así que `minTradeWeek` en vez de `minTradesWeek` deja la
    categoría prendiendo un criterio inexistente y buscando con la
    configuración de antes — devuelve cualquier cosa y no hay señal de que algo
    ande mal.
    """
    # Todas las claves, no sólo las que arrancan renglón: en DEFAULT_CFG varias
    # comparten línea —`minCagr: 3, minExposure: 5, minRetDd: 1.5, ...`— y con
    # el patrón anclado al margen esta prueba daba por inexistentes perillas que
    # sí están, que es la clase de falso positivo que hace desconfiar del test.
    conocidas = set(re.findall(r"(\w+):",
                               re.search(r"const DEFAULT_CFG = \{(.*?)\n\};",
                                         APP, re.S).group(1)))
    conocidas |= {"timeframe", "critOn"}      # timeframe va a S.sel
    criterios = {a or b for a, b in
                 re.findall(r'(\w+):\s*"min_\w+|(\w+):\s*"max_\w+', APP)}

    for nombre, cfg in _recetas().items():
        for clave in re.findall(r"^\s+(\w+):", cfg, re.M):
            assert clave in conocidas or clave in criterios, (
                f"la receta «{nombre}» toca «{clave}», que no existe ni en la "
                "configuración ni entre los criterios: se aplicaría sin efecto")
        prendidos = re.search(r"critOn: \{([^}]*)\}", cfg)
        for c in re.findall(r"(\w+):", prendidos.group(1) if prendidos else ""):
            assert c in criterios, (
                f"la receta «{nombre}» prende el criterio «{c}», que el minero "
                "no conoce: el filtro no se aplicaría y saldría cualquier cosa")


def test_la_pantalla_no_puede_decir_una_relacion_que_no_va_a_usar():
    """Con una receta que busca varias, decir «1:2» es mentir.

    Encontrado probando: después de aplicar la categoría de aciertos —que busca
    entre 0,5 y 0,75— el resumen del paso de riesgo seguía diciendo «1:2» y el
    panel de arranque prometía «1% per trade at a 1:2 risk/reward». Ninguna
    candidata de esa corrida iba a usar 1:2.

    El panel de arranque es la promesa de lo que la aplicación está por hacer,
    en una aplicación cuyo argumento entero es que los números no mienten. Los
    dos textos pasan por la misma función justamente porque decían lo mismo por
    caminos distintos, que es como terminan diciendo cosas distintas.
    """
    assert "function comoSeDiceElRR()" in APP, (
        "desapareció la función que traduce la relación a texto")
    cuerpo = APP[APP.index("function comoSeDiceElRR()"):]
    cuerpo = cuerpo[:cuerpo.index("\n}")]
    assert "rrBuscado" in cuerpo, (
        "la función dejó de mirar si la búsqueda tiene varias relaciones")
    # y nadie más arma el texto por su cuenta
    sueltos = re.findall(r"`1:\$\{S\.cfg\.rr\}", APP)
    assert not sueltos, (
        "volvió a haber un lugar que escribe la relación a mano; con una receta "
        "que busca varias, ese lugar va a mostrar una que no se va a usar")
    assert '"rr.varias"' in DICC, "falta el texto para el rango de relaciones"
