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


def test_la_de_fondeo_mina_donde_algo_existe():
    """Ni muy arriba ni muy abajo, y las dos cotas salen de medir.

    Arriba: a 4 horas la frecuencia no existe — mediana de 0,9 operaciones por
    semana y ninguno de cuarenta genomas llega a cinco, en los cuatro mercados.

    Abajo, y es lo que no esperaba: a 15 MINUTOS es peor todavía. Sobre SP500,
    cuatro años, 900 candidatas, no sale NADA — ni siquiera pidiendo sólo
    rentabilidad y caída, sin frecuencia. Hay tres veces más operaciones y por
    eso se paga el spread tres veces más seguido, que se lleva la ventaja.

    Queda 30 minutos, que es donde algo aparece.
    """
    cfg = _recetas()["fondeo"]
    tf = re.search(r'timeframe: "(\w+)"', cfg).group(1)
    assert tf == "30m", (
        f"la categoría de fondeo mina en {tf}. Medido: a 4h y a 1h no hay "
        "frecuencia, y a 15m los costos se comen todo — no sale nada ni "
        "pidiendo sólo rentabilidad")


def test_la_de_fondeo_no_pide_una_frecuencia_que_no_existe():
    """Pedir cinco por semana devolvía cero, y eso es peor que no tener la categoría.

    Medido sobre SP500 a 30 minutos, cuatro años, 1400 candidatas, aflojando de
    a una exigencia:

        rentable + caída ≤8% + 3 por semana ....... nada
        rentable + 3 por semana (sin caída) ....... nada
        rentable + caída ≤8% (sin frecuencia) .... 5, con 0,62 por semana
        lo mismo pidiendo 2 por semana ........... 1
        lo mismo pidiendo 1 por semana ........... 2, con 2,03 de mediana
        rentable + 3 por semana + caída ≤15% ..... nada

    La que ahoga es la frecuencia y no la caída: aflojar el drawdown al 15%
    sigue sin dar nada. Ser rentable es ser selectivo, y ser selectivo es
    operar poco. Si alguien sube este número, la categoría vuelve a devolver
    cero y la tarjeta vuelve a prometer algo que no existe.
    """
    cfg = _recetas()["fondeo"]
    pedido = float(re.search(r"minTradesWeek: ([\d.]+)", cfg).group(1))
    assert pedido <= 2.0, (
        f"la categoría de fondeo pide {pedido} operaciones por semana. Medido, "
        "por encima de 2 no aparece ninguna que además sea rentable y no se "
        "hunda — la búsqueda corre diez minutos y devuelve una tabla vacía")


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
    #: Segundos por candidata sobre DIEZ años, de la medición de velas por
    #: temporalidad. Una receta que acorta la ventana paga en proporción: la
    #: mitad de velas es la mitad de costo, y por eso acortar es lo que le
    #: permite a la de fondeo probar más candidatas en el mismo rato.
    COSTO_10A = {"15m": 2.08, "30m": 1.04, "1h": 0.51, "4h": 0.13}
    TECHO_MIN = 12
    for nombre, cfg in _recetas().items():
        tope = re.search(r"maxCandidates: (\d+)", cfg)
        assert tope, f"la receta «{nombre}» no fija su tope de candidatas"
        tf = re.search(r'timeframe: "(\w+)"', cfg).group(1)
        anios = re.search(r"anios: (\d+)", cfg)
        escala = (int(anios.group(1)) / 10) if anios else 1.0
        minutos = int(tope.group(1)) * COSTO_10A[tf] * escala / 60
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
    # Las tres que `aplicarReceta` trata aparte y no copia a S.cfg: la
    # temporalidad y la ventana van a S.sel, y critOn se reemplaza entero.
    conocidas |= {"timeframe", "critOn", "anios"}
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
    # Y nadie MÁS la arma por su cuenta. Se saca del texto el cuerpo de la
    # propia función, que es el único lugar que sí tiene que escribirla: sin
    # esa exclusión la prueba se prohibía a sí misma el arreglo que exige.
    resto = APP.replace(cuerpo, "")
    # Sin anclar a la comilla invertida. El primer intento pedía "`1:${S.cfg.rr}"
    # y el lugar que había que atrapar dice "` · 1:${S.cfg.rr}", así que la
    # comprobación no podía fallar nunca: pasaba con la regresión puesta.
    sueltos = re.findall(r"1:\$\{S\.cfg\.rr\}", resto)
    assert not sueltos, (
        "volvió a haber otro lugar que escribe la relación a mano; con una "
        "receta que busca varias, ese lugar va a mostrar una que no se va a usar")
    assert '"rr.varias"' in DICC, "falta el texto para el rango de relaciones"
