"""Franjas horarias de negociación, en UTC.

El motor de backtest siempre supo respetar un ``TimeFilter`` —filtra las
entradas que caen fuera de horario—, pero nada se lo pasaba: el minero no lo
seteaba y la interfaz no lo ofrecía. Consecuencia: toda estrategia encontrada
operaba las veinticuatro horas, incluidas las madrugadas en las que un índice
cotiza con una décima parte del volumen y un spread varias veces mayor.

Este módulo define el conjunto CERRADO de franjas entre las que se puede
elegir o buscar. Es a propósito una lista corta y no un rango libre de horas:

* con horas arbitrarias, la búsqueda encuentra siempre alguna ventana de tres
  horas en la que el pasado se ve espectacular, y eso es sobreajuste puro;
* una franja con nombre —la sesión de Londres, el solape con Nueva York— es
  una hipótesis que se puede defender antes de mirar los datos, y el resultado
  se puede leer y contar.

Los horarios están en UTC porque los datos lo están (ver ``data/loader.py``,
que convierte todo a UTC y le quita la zona). No siguen el horario de verano:
las sesiones reales se corren una hora dos veces al año, y los bordes de estas
franjas llevan margen suficiente para que eso no cambie de qué sesión se está
hablando.
"""

from __future__ import annotations

from typing import Any

from botiquant.core.models import TimeFilter

LUN_VIE = [0, 1, 2, 3, 4]

#: id -> (hora inicial UTC, hora final UTC, días de la semana, en, es)
#:
#: El final es EXCLUSIVO: (13, 16) son las velas de las 13, 14 y 15.
SESIONES: dict[str, tuple[int, int, list[int], str, str]] = {
    "todo": (0, 24, LUN_VIE, "Around the clock", "Todo el día"),
    "asia": (0, 8, LUN_VIE, "Asian session", "Sesión asiática"),
    "londres": (7, 16, LUN_VIE, "London session", "Sesión de Londres"),
    "apertura_londres": (7, 11, LUN_VIE, "London open", "Apertura de Londres"),
    "nueva_york": (13, 21, LUN_VIE, "New York session", "Sesión de Nueva York"),
    "apertura_ny": (13, 17, LUN_VIE, "New York open", "Apertura de Nueva York"),
    "solape": (13, 16, LUN_VIE, "London–New York overlap", "Solape Londres–Nueva York"),
    "rueda_eeuu": (14, 21, LUN_VIE, "US cash hours", "Rueda de acciones de EE.UU."),
    "sin_lunes_viernes": (0, 24, [1, 2, 3], "Tuesday to Thursday", "De martes a jueves"),
}

#: La franja que no restringe nada. Es el default en todos lados: activar una
#: sesión recorta las operaciones disponibles, y una configuración por defecto
#: que devuelve menos estrategias es una configuración que se siente rota.
SIN_RESTRICCION = "todo"

IDS: tuple[str, ...] = tuple(SESIONES)


def normalizar(ids: list[str] | tuple[str, ...] | None) -> list[str]:
    """Los ids válidos de una lista pedida, sin repetidos y en orden estable.

    Una lista vacía o con basura devuelve la franja sin restricción, para que
    un payload malformado no deje al minero sin ninguna opción de la que
    elegir — que sería una búsqueda que no puede construir ni una candidata.
    """
    if not ids:
        return [SIN_RESTRICCION]
    vistos: list[str] = []
    for x in ids:
        clave = str(x)
        if clave in SESIONES and clave not in vistos:
            vistos.append(clave)
    return vistos or [SIN_RESTRICCION]


def filtro(sesion: str) -> TimeFilter:
    """El ``TimeFilter`` de una franja, listo para meter en un ``StrategySpec``.

    La franja sin restricción devuelve un filtro DESACTIVADO en vez de uno de
    0 a 24 horas de lunes a viernes. No es lo mismo: el segundo descartaría las
    velas de fin de semana que traen las criptomonedas, y una estrategia de
    BTCUSD perdería dos días de cada siete sin que nadie lo haya pedido.
    """
    if sesion not in SESIONES or sesion == SIN_RESTRICCION:
        return TimeFilter()
    inicio, fin, dias, _en, _es = SESIONES[sesion]
    return TimeFilter(enabled=True, days=list(dias),
                      start_hour=inicio, end_hour=fin)


def etiqueta(sesion: str, idioma: str = "es") -> str:
    fila = SESIONES.get(sesion)
    if fila is None:
        return sesion
    return fila[3] if idioma == "en" else fila[4]


def horario(sesion: str) -> str:
    """El rango legible, o cadena vacía cuando no restringe la hora."""
    fila = SESIONES.get(sesion)
    if fila is None or (fila[0], fila[1]) == (0, 24):
        return ""
    return f"{fila[0]:02d}:00–{fila[1]:02d}:00 UTC"


def catalogo() -> list[dict[str, Any]]:
    """Lo que necesita la interfaz para dibujar el selector."""
    return [
        {"id": sid, "en": en, "es": es, "start_hour": ini, "end_hour": fin,
         "days": list(dias), "horario": horario(sid),
         "restringe": sid != SIN_RESTRICCION}
        for sid, (ini, fin, dias, en, es) in SESIONES.items()
    ]


def desde_filtro(tf: TimeFilter | None) -> str:
    """Qué franja conocida describe este filtro, o "" si no es ninguna.

    Sirve para las estrategias archivadas antes de que existieran las franjas
    y para las que se editaron a mano: la pantalla necesita poder nombrar el
    horario de una estrategia que sólo guardó su ``time_filter``.
    """
    if tf is None or not tf.enabled:
        return SIN_RESTRICCION
    for sid, (ini, fin, dias, _en, _es) in SESIONES.items():
        if sid == SIN_RESTRICCION:
            continue
        if (tf.start_hour, tf.end_hour) == (ini, fin) and sorted(tf.days) == sorted(dias):
            return sid
    return ""
