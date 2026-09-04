"""El resumen de la validación: qué tiene que seguir siendo cierto.

La pantalla junta los veredictos de todas las estrategias validadas y los
dibuja. No hay navegador en la suite, así que lo que se comprueba es que las
reglas que la hacen honesta sigan escritas donde van: que no invente números,
que no aparezca con pocos casos, que su línea de referencia sea la misma que
usa el motor para decidir, y que el veredicto no quede contado sólo con color.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
APP = (RAIZ / "ui" / "app.js").read_text(encoding="utf-8")
CHARTS = (RAIZ / "ui" / "charts.js").read_text(encoding="utf-8")
I18N = (RAIZ / "ui" / "i18n.js").read_text(encoding="utf-8")
WF = (RAIZ / "botiquant" / "analysis" / "walkforward.py").read_text(encoding="utf-8")


def test_el_piso_dibujado_es_el_que_usa_el_motor():
    """La línea de referencia dice "debajo de esto es sobreajustada".

    Ese piso lo decide `_verdict` en el motor. Si allá se mueve y acá no, la
    pantalla dibuja una regla que ya no existe y el usuario ve puntos por
    encima de la línea con veredicto de sobreajustada.
    """
    m_motor = re.search(r"if efficiency < ([0-9.]+):", WF)
    assert m_motor, "el motor dejó de tener un piso de eficiencia"
    m_ui = re.search(r"const RES_PISO_EF = ([0-9.]+);", APP)
    assert m_ui, "la pantalla dejó de declarar el piso que dibuja"
    assert float(m_ui.group(1)) == float(m_motor.group(1)), (
        f"el motor corta en {m_motor.group(1)} y la pantalla dibuja "
        f"{m_ui.group(1)}")


def test_no_se_ofrece_con_pocas_validadas():
    """Con diez validadas, "33% pasaron" habla de tres estrategias.

    Un porcentaje sobre pocos casos se lee como una ley y no lo es. Por eso
    hay un mínimo, y por debajo de él no se dibuja NI se ofrece la solapa:
    ofrecerla y que adentro diga "todavía no" es hacer perder un clic.
    """
    m = re.search(r"const RESUMEN_MINIMO = (\d+);", APP)
    assert m and int(m.group(1)) >= 20, "el mínimo de casos se fue o bajó de 20"
    cuerpo = APP[APP.index("function resumenHTML"):]
    cuerpo = cuerpo[:cuerpo.index("\n}\n")]
    assert "d.puntos.length < RESUMEN_MINIMO" in cuerpo, (
        "resumenHTML tiene que cortar por debajo del mínimo")
    assert "validadas.length >= RESUMEN_MINIMO ? enlace(\"resumen\"" in APP, (
        "la solapa tampoco se ofrece por debajo del mínimo")


def test_el_veredicto_no_se_cuenta_solo_con_color():
    """Verde y ámbar quedan a ΔE 7,2 para un ojo protán.

    Por debajo de 8 el color solo no distingue, así que cada veredicto lleva
    además una forma —círculo, triángulo, cruz— y la leyenda repite forma,
    color y palabra. Un gráfico donde el veredicto es sólo un tono deja afuera
    a quien no separa esos dos.
    """
    assert "function figura(tipo, x, y, r)" in CHARTS, "se fue la forma por veredicto"
    for tag in ("circle", "polygon", "path"):
        assert tag in CHARTS[CHARTS.index("function figura"):][:700], (
            f"la forma {tag} desapareció: quedan menos de tres")
    # y la leyenda usa la MISMA función, no un cuadradito de color
    leyenda = APP[APP.index("const ley = $(\"#res-leyenda\", main);"):]
    leyenda = leyenda[:leyenda.index("Charts.barrasPct")]
    assert "Charts.figura(tipo" in leyenda, "la leyenda dejó de dibujar la forma"
    assert "t(NOMBRE[tipo])" in leyenda, "la leyenda dejó de escribir la palabra"


def test_el_resumen_no_recalcula_nada():
    """Todo sale de lo que ya está guardado.

    Si el resumen pidiera backtests o validaciones nuevas, abrir una solapa
    dispararía minutos de trabajo del servidor sin que nadie lo pida. Sus
    números salen de `validacion` y de `meta`, que la pantalla ya tiene.
    """
    cuerpo = APP[APP.index("function resumenDatos"):APP.index("function resumenHTML")]
    for prohibido in ("api.get", "api.post", "await "):
        assert prohibido not in cuerpo, (
            f"resumenDatos usa {prohibido!r}: dejó de leer sólo lo guardado")


def test_sus_textos_estan_en_los_dos_idiomas():
    """Como cualquier texto vivo: si falta un idioma, la clave sale cruda."""
    claves = sorted(set(re.findall(r't\("(res\.[a-z0-9_]+)"', APP)))
    assert claves, "el resumen deberia tener textos propios"
    for c in claves:
        m = re.search(r'"' + re.escape(c) + r'":\s*\[(.*?)\],\s*\n', I18N, re.S)
        assert m, f"falta {c} en el diccionario"
        assert m.group(1).count('", "') >= 1 or '",\n' in m.group(1), (
            f"{c} no tiene los dos idiomas")
