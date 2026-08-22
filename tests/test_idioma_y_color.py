"""Dos cosas que se ven en pantalla y no se ven leyendo el código.

Las dos salieron de mirar la aplicación corriendo y las dos son de la clase
que vuelve sola si nadie la cuida.

LA PRIMERA es el idioma. La interfaz es bilingüe y arranca en inglés, pero
ocho frases nunca pasaron por ``t(...)``: quedaron escritas a mano en
castellano mientras alguien trabajaba, cuando todavía no había un usuario del
otro lado. No eran frases escondidas — una era la regla de entrada de la
estrategia, que es lo que la DEFINE ("EMA(20) cruza arriba de EMA(60)"), y
otra la etiqueta que encabeza el inspector. Con la aplicación en inglés se
leían igual.

LA SEGUNDA es el color. El drawdown se dibujaba con ``class="neg"`` puesto a
mano en los siete lugares donde aparece, sin mirar el número: una caída del
4,6% y una del 33,8% salían del mismo rojo. Pintar todo de rojo es lo mismo
que no pintar nada, salvo que además gasta la señal para cuando hace falta.

Sobre la forma de estas pruebas: la primera versión barría TODOS los literales
del archivo buscando palabras en castellano, y daba doce falsos positivos —las
comillas invertidas anidadas de una plantilla no se pueden emparejar con una
expresión regular, así que capturaba fragmentos de código—. Un guardarraíl que
se equivoca doce veces lo desactiva el primero que pase. Estas miran lugares
exactos: los avisos, los operadores y los siete sitios de la caída. El barrido
general existe, pero como herramienta que se corre a mano y se lee con
criterio, no como prueba que corre sola en cada cambio.
"""

from __future__ import annotations

import re

from botiquant.api.app import UI_DIR

APP = (UI_DIR / "app.js").read_text(encoding="utf-8")
DICC = (UI_DIR / "i18n.js").read_text(encoding="utf-8")


def test_los_avisos_pasan_por_el_diccionario():
    """Ningún ``toast`` puede llevar texto escrito a mano.

    Es donde estaban seis de las ocho fugas, y se entiende por qué: un aviso se
    escribe en el momento en que se termina la función que lo dispara, y en ese
    momento uno está pensando en la función y no en el idioma.

    Se permite lo que no es texto: un mensaje de error del servidor, una
    variable ya armada, o una expresión que elige entre dos claves.
    """
    permitidos = re.compile(
        r"""^(
              t\(                     # t("clave")
            | e\.message              # el error del servidor, tal cual vino
            | `\$\{t\(                # plantilla que arranca con una clave
            | [a-z]\w*(\.\w+)*\s*[,)?] # una variable o propiedad ya armada
            | \w+\s*\?                # ternario entre dos claves
        )""", re.X)
    culpables = []
    for m in re.finditer(r"\btoast\(", APP):
        resto = APP[m.end():m.end() + 90]
        if permitidos.match(resto):
            continue
        n = APP[:m.start()].count("\n") + 1
        culpables.append(f"  línea {n}: toast({resto.splitlines()[0][:80]}")
    assert not culpables, (
        "estos avisos llevan texto escrito a mano y se van a leer igual con la "
        "aplicación en el otro idioma:\n" + "\n".join(culpables))


def test_los_operadores_de_las_reglas_se_traducen():
    """"EMA(20) cruza arriba de EMA(60)" es la definición de la estrategia.

    El indicador y sus parámetros NO se traducen —EMA(20) se llama igual en las
    dos lenguas y en MetaTrader— pero el operador se lee como parte de una
    frase, así que sí. Estaba escrito a mano en ``condLabel`` y se dibujaba en
    castellano en la sección "Strategy rules" de cada estrategia.
    """
    for clave in ("rule.cross_above", "rule.cross_below", "rule.rising", "rule.falling"):
        assert f't("{clave}")' in APP, f"el operador {clave} volvió a estar escrito a mano"
        assert f'"{clave}"' in DICC, f"falta {clave} en el diccionario"


def test_la_etiqueta_del_inspector_se_traduce():
    """Encabeza la ficha de cualquier estrategia abierta desde el banco.

    Decía "del banco · SP500 · 1h · riesgo 1%" en inglés, que además es el
    primer texto que se lee al abrir la pantalla más importante que tiene la
    aplicación.
    """
    assert 't("bank.from_bank"' in APP, "la etiqueta del inspector volvió a armarse a mano"


def test_la_fecha_de_guardado_no_se_congela_en_un_idioma():
    """Se dibuja en el momento, no se guarda ya traducida.

    "Minada el 20/8/2026" aparecía con la aplicación en inglés: la frase se
    armaba AL GUARDAR, ya traducida, y se escribía en el campo de notas. Ahí se
    quedaba para siempre en el idioma que hubiera ese día — y de paso ocupaba
    el campo donde el usuario escribe SU nota, que tiene su propio panel y su
    propio endpoint.
    """
    assert 'notes: t("saved.mined_on"' not in APP, (
        "la fecha volvió a guardarse ya traducida en el campo de notas")
    assert 'ctx.saved_at ?' in APP and 't("saved.mined_on"' in APP, (
        "la fila dejó de dibujar la fecha desde meta.saved_at")


def test_la_caida_no_se_pinta_siempre_del_mismo_color():
    """Un color que está siempre puesto no distingue nada.

    Medido sobre las 150 estrategias que había en el banco: la mediana cae
    12,3%, tres de cada cuatro se quedan bajo 18,7% y la décima parte más brava
    pasa de 25%. Con los cortes en 15 y 25 el ámbar marca "mirala antes de
    confiar" y el rojo marca ese último décimo, que es lo que un color de
    alarma tiene que hacer.
    """
    assert "function nivelDD(" in APP, "desapareció el graduador de la caída"
    assert "const DD_ATENCION = 15, DD_GRAVE = 25;" in APP, (
        "cambiaron los cortes de la caída. Salieron de medir el banco, no de "
        "una intuición: si se mueven, hay que volver a medir y decir por qué.")

    # ninguno de los siete lugares que la dibujan puede volver a fijar el rojo
    fijos = re.findall(r'class="num neg">\$\{[^}]*max_drawdown', APP)
    fijos += re.findall(r'kind === "dd"[^\n]*cls = "neg"', APP)
    fijos += re.findall(r'<b class="neg">\$\{fmtNum\(\s*\w*\.?\w*\.?max_drawdown', APP)
    assert not fijos, f"la caída volvió a pintarse de rojo a mano: {fijos}"


def test_la_caida_escala_con_el_riesgo_por_operacion():
    """El 3% por operación da el triple de caída que el 1%.

    Está dicho en ``COLS_CON_RIESGO`` y es la razón de que esas columnas no se
    puedan comparar entre corridas. Una banda fija llamaría grave a una
    estrategia que arriesga el triple y cae exactamente lo mismo.
    """
    assert "function riesgoDeCtx(" in APP and "function riesgoActual(" in APP
    cuerpo = APP[APP.index("function nivelDD("):]
    cuerpo = cuerpo[:cuerpo.index("\n}")]
    assert "riesgo" in cuerpo, "nivelDD dejó de mirar el riesgo por operación"


def test_los_tres_niveles_de_caida_tienen_color():
    """Y el de calma NO tiene, que es la decisión y no un olvido.

    Si el 60% de la columna estuviera pintada, el color volvería a no decir
    nada. La ausencia de color ES la señal de "acá no hay nada que mirar".
    """
    css = (UI_DIR / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.dd-calma\s*\{[^}]*color:\s*var\(--text\)", css), (
        "la caída en calma dejó de ser texto normal")
    assert re.search(r"\.dd-atencion\s*\{[^}]*var\(--warn\)", css)
    assert re.search(r"\.dd-grave\s*\{[^}]*var\(--neg\)", css)
