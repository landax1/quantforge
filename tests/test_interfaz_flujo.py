"""La interfaz es un camino de tres pasos, y los textos están completos.

Dos cosas se comprueban acá, y las dos nacieron de fallos reales.

La primera es estructural. La aplicación tenía siete secciones en el menú y
tres de ellas —Monte Carlo, Walk-forward, Portafolio— eran la MISMA pantalla
con otro verbo: el mismo selector de estrategias repetido. Como no son lugares
sino cosas que se le hacen a una estrategia, ahora viven dentro de ella. Si
alguien las vuelve a colgar del menú, esto falla y obliga a justificarlo.

La segunda son las claves de traducción. Toda la interfaz pasa por t(), y una
clave que no existe en el diccionario no rompe nada: se dibuja el nombre de la
clave, en crudo, en medio de la pantalla. Pasó con `session.no_limit` y se ve
igual que si la aplicación estuviera a medio traducir.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from botiquant.api.app import UI_DIR

APP = (UI_DIR / "app.js").read_text(encoding="utf-8")
DICC = (UI_DIR / "i18n.js").read_text(encoding="utf-8")
INDEX = (UI_DIR / "index.html").read_text(encoding="utf-8")

#: Las claves que se arman concatenando —t("est." + estado)— no se pueden
#: encontrar leyendo el archivo. Se listan sus familias para no dar falsos
#: positivos, y cada familia se comprueba aparte más abajo.
FAMILIAS = ("s.", "est.", "wf.frase_", "dir.", "ended.", "crit.",
            "cat.", "inst.", "tf.", "ms.")


def _claves_del_diccionario() -> set[str]:
    SALTO, CIERRE = chr(10), chr(10) + "};"
    ini = DICC.index("const STR = {")
    fin = DICC.index("\n};", ini)
    return set(re.findall(r'^\s{2}"([^"]+)":', DICC[ini:fin], re.M))


def _claves_usadas() -> set[str]:
    return (set(re.findall(r'\bt\(\s*"([^"]+)"', APP))
            | set(re.findall(r'data-i18n="([^"]+)"', INDEX)))


def test_no_falta_ninguna_clave_de_texto():
    tiene = _claves_del_diccionario()
    faltan = sorted(k for k in _claves_usadas()
                    if k not in tiene and not k.startswith(FAMILIAS))
    assert not faltan, (
        "estas claves se piden y no están en el diccionario; se van a dibujar "
        f"en crudo en la pantalla: {faltan}")


def test_no_hay_claves_duplicadas():
    """Una clave repetida hace que gane la última, que nunca es la que se editó."""
    SALTO, CIERRE = chr(10), chr(10) + "};"
    ini = DICC.index("const STR = {")
    fin = DICC.index("\n};", ini)
    todas = re.findall(r'^\s{2}"([^"]+)":', DICC[ini:fin], re.M)
    repes = sorted({k for k in todas if todas.count(k) > 1})
    assert not repes, f"claves definidas dos veces: {repes}"


@pytest.mark.parametrize("estado", ["sin_probar", "aprobada", "aceptable", "no_paso"])
def test_los_cuatro_estados_tienen_nombre(estado):
    assert f'"est.{estado}"' in DICC, (
        f"el estado {estado} se muestra en la lista de estrategias y no tiene texto")


@pytest.mark.parametrize("clave", [
    "wf.frase_aprobada", "wf.frase_aceptable_ef", "wf.frase_aceptable_tramos",
    "wf.frase_no_paso_tramos", "wf.frase_no_paso_ef",
])
def test_cada_veredicto_tiene_su_frase(clave):
    """La frase nombra QUÉ limitó a la estrategia.

    Con una sola frase por estado, la pantalla llegó a decir "aguantó a medias:
    ganó en 4 de 4 tramos", que se lee como una contradicción — el límite era la
    eficiencia y no la consistencia."""
    assert f'"{clave}"' in DICC


def test_el_menu_tiene_cuatro_secciones():
    """Datos, Minado, Mis estrategias, Consejos. Nada más.

    El databank dejó de ser una entrada del menú y pasó a ser la segunda vista
    de Minado: uno busca y después mira lo que salió, es la misma tarea."""
    paginas = re.findall(r'data-page="([^"]+)"', INDEX)
    assert paginas == ["data", "mining", "saved", "consejos"], (
        f"el menú cambió sin querer: {paginas}")


def test_el_databank_vive_adentro_de_minado():
    assert "PAGES.banco" not in APP, "el databank volvió a ser una sección del menú"
    assert "const vistaResultados" in APP and "const vistaBuscar" in APP
    assert 'data-vista="resultados"' in APP, "falta el conmutador de vistas"


def test_lo_avanzado_esta_apagado_pero_entero():
    """Walk-forward, Monte Carlo y portafolio no se borraron: se apagaron.

    Un interruptor y no bloques comentados, porque el código comentado se pudre
    y el código con tests corriendo no. Si esta prueba falla porque AVANZADO
    pasó a true, es una decisión de producto — cambiala a propósito."""
    assert "const AVANZADO = false;" in APP, (
        "AVANZADO cambió de valor o de nombre")
    # y lo que el interruptor apaga sigue existiendo, con su backend
    for pieza in ("panelPrueba", "abrirPortafolio", "estadoChip", "probarEstrategia"):
        assert pieza in APP, f"{pieza} se borró en vez de apagarse"
    api = (Path(__file__).resolve().parents[1] / "botiquant" / "api" / "app.py"
           ).read_text(encoding="utf-8")
    for ruta in ("/api/probar", "/api/portfolio", "/api/walkforward"):
        assert ruta in api, f"{ruta} se borró; tenía que quedar para el futuro"


def test_los_consejos_estan_completos():
    """Cada consejo necesita título y cuerpo, en los dos idiomas."""
    consejos = re.findall(r'clave: "tip\.(\w+)"', APP)
    assert len(consejos) >= 5, f"quedaron muy pocos consejos: {consejos}"
    for c in consejos:
        for sufijo in ("", "_cuerpo"):
            assert f'"tip.{c}{sufijo}"' in DICC, f"falta el texto tip.{c}{sufijo}"


def test_los_consejos_no_citan_cifras_de_corridas_anteriores():
    """Un consejo cita la relacion, nunca el resultado de una corrida nuestra.

    "Con todo el historico sobrevive el 94% y con dos anios el 65%" parece mas
    concreto, y es peor: son numeros de UNA busqueda sobre UN instrumento con
    UNA configuracion. Puestos en la pantalla hacen creer que la aplicacion
    reparte estrategias ya calculadas en vez de buscarlas en el momento sobre
    los datos de cada uno — que es exactamente lo que hace.

    Lo que si puede llevar numeros es la configuracion: un spread de referencia
    es un dato del instrumento, no el resultado de haber minado."""
    ini = DICC.index("const STR = {")
    fin = DICC.index(chr(10) + "};", ini)
    cuerpo = DICC[ini:fin]
    culpables = []
    clave = None
    for linea in cuerpo.split(chr(10)):
        m = re.match(r'\s{2}"([^"]+)":', linea)
        if m:
            clave = m.group(1)
        if not (clave or "").startswith("tip."):
            continue
        # porcentajes con decimal: la forma en que se escribe un resultado
        if re.search(r"\d+[.,]\d+\s*%", linea):
            culpables.append(clave)
    assert not culpables, (
        "estos consejos volvieron a citar cifras de corridas anteriores, que "
        f"hacen parecer que las estrategias vienen precalculadas: {sorted(set(culpables))}")


@pytest.mark.parametrize("retirada", ["robustez", "walkforward", "portafolio"])
def test_las_pantallas_duplicadas_no_volvieron(retirada):
    assert f"PAGES.{retirada}" not in APP, (
        f"{retirada} volvió a ser una pantalla del menú. Era el mismo selector "
        "de estrategias por tercera vez: pertenece adentro de una estrategia.")


def test_probar_y_portafolio_se_abren_desde_una_estrategia():
    """Lo que reemplazó a las tres pantallas."""
    assert "panelPrueba" in APP, "falta el veredicto dentro de la ficha"
    assert "abrirPortafolio" in APP, "el portafolio tiene que abrirse como hoja"
    assert "/api/probar" in APP, "falta la acción única que corre las dos pruebas"


def test_comprar_y_mantener_no_volvio():
    """La comparación contra comprar y mantener se retiró, y con razón.

    Sobre CFDs no medía lo que decía medir. La curva se calculaba sin cobrar el
    financiamiento nocturno, que en un índice apalancado ronda el 4–6% anual y
    se come casi toda la subida: lo que se dibujaba era el índice, no lo que le
    habría pasado a la cuenta. Y en un par de divisas es peor todavía, porque
    mantener EURUSD diez años no tiene ninguna deriva esperada contra la que
    medirse.

    Si vuelve, tiene que volver cobrando el swap y sólo donde signifique algo.
    """
    for rastro in ("benchmark", "buy_and_hold", "panelBenchmark"):
        assert rastro not in APP, f"volvió {rastro} a la interfaz"
    api = Path(__file__).resolve().parents[1] / "botiquant" / "api" / "app.py"
    texto = api.read_text(encoding="utf-8")
    assert "buy_and_hold" not in texto and '"benchmark"' not in texto
    assert not (Path(__file__).resolve().parents[1]
                / "botiquant" / "backtesting" / "benchmark.py").exists()


# --------------------------------------------------- el catálogo, en dos idiomas
# Estas familias se arman concatenando —t("inst." + c.key)— así que el examen de
# arriba no las ve. Se comprueban una por una y contra el catálogo real, para que
# agregar un instrumento nuevo sin su texto falle acá y no en la pantalla del
# usuario, donde aparecería como "inst.gbpusd" en crudo.

def test_cada_instrumento_del_catalogo_tiene_su_texto():
    from botiquant.data.catalog import CATALOG
    faltan = [c["key"] for c in CATALOG if f'"inst.{c["key"]}"' not in DICC]
    assert not faltan, f"instrumentos sin descripción traducida: {faltan}"


def test_cada_categoria_del_catalogo_tiene_su_nombre():
    from botiquant.data.catalog import CATALOG
    faltan = sorted({c["category"] for c in CATALOG
                     if f'"cat.{c["category"]}"' not in DICC})
    assert not faltan, f"categorías sin nombre traducido: {faltan}"


@pytest.mark.parametrize("tf", ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "native"])
def test_cada_timeframe_tiene_nombre(tf):
    """Se muestran en las tarjetas de instrumento: "8,035,544 1-minute bars"."""
    assert f'"tf.{tf}"' in DICC


def test_cada_consejo_tiene_su_dibujo():
    """Los seis consejos llevan gráfico, y cada gráfico dibuja SU dato.

    No son adornos: el mapa GRAFICOS se indexa por el id del consejo, así que
    un consejo nuevo sin dibujo se ve como una tarjeta a medias al lado de las
    otras cinco."""
    consejos = re.findall(r'id: "(\w+)",\s*ico:', APP)
    assert consejos, "no se pudo leer la lista de consejos"
    mapa = re.search(r"const GRAFICOS = \{(.*?)\};", APP, re.S)
    assert mapa, "falta el mapa de gráficos"
    dibujados = set(re.findall(r"(\w+):", mapa.group(1)))
    faltan = [c for c in consejos if c not in dibujados]
    assert not faltan, f"consejos sin gráfico: {faltan}"


def test_los_graficos_dibujan_relaciones_y_no_resultados():
    """Los diagramas muestran la FORMA del intercambio, sin cifras de corrida.

    Cuatro de los seis dibujaban barras rotuladas con porcentajes medidos por
    nosotros. Se rehicieron como curvas, siluetas y embudos: afirman la
    direccion — que vale siempre — y no un resultado, que depende del
    instrumento, del periodo y de la configuracion de cada uno."""
    mapa = re.search(r"const GRAFICOS = \{(.*?)\};", APP, re.S)
    assert mapa, "falta el mapa de graficos"
    ini = APP.index("function gHistoria")
    fin = APP.index("const GRAFICOS = {")
    dibujo = APP[ini:fin]
    # un porcentaje con decimal dentro del codigo de los graficos es una cifra
    # de corrida: los que quedan son coordenadas y opacidades, sin el signo
    sospechosos = re.findall(r'"[^"]*\d+\.\d+\s*%[^"]*"', dibujo)
    assert not sospechosos, f"cifras de corrida en los graficos: {sospechosos}"


def test_los_textos_no_atribuyen_los_resultados_a_la_suerte():
    """El intercambio se enuncia como riesgo, no como sospecha.

    Decir "puede que haya sido casualidad" y decir "con menos velas la
    estrategia se mide contra menos condiciones distintas" describen el mismo
    hecho. La segunda forma se puede usar para decidir; la primera sólo deja al
    usuario desconfiando de lo que la aplicación acaba de encontrarle.

    Esto NO alcanza a los avisos que protegen plata —costo imposible, riesgo de
    ruina, drawdown proyectado—: eso es seguridad y tiene que seguir sonando
    incómodo."""
    import re
    prohibidas = re.compile(
        r"(suerte|casualidad|afortunad\w*|punter[íi]a|luck|lucky|by chance|"
        r"coincidence)", re.I)
    SALTO, CIERRE = chr(10), chr(10) + "};"
    ini = DICC.index("const STR = {")
    fin = DICC.index(CIERRE, ini)
    culpables = []
    clave = None
    for linea in DICC[ini:fin].split(SALTO):
        m = re.match(r'\s{2}"([^"]+)":', linea)
        if m:
            clave = m.group(1)
        if prohibidas.search(linea):
            culpables.append(clave)
    assert not culpables, (
        "estos textos vuelven a atribuir el resultado a la suerte, que no le "
        f"sirve a nadie para decidir: {sorted(set(culpables))}")


def test_las_filas_del_setup_tienen_una_sola_altura():
    """Título y resumen APILADOS, no enfrentados a lo ancho.

    Enfrentados no entraban: el título se partía ("Costos del / broker") y el
    resumen también, y como iba alineado a la derecha su segunda línea
    arrancaba dentada. Seis filas de alturas distintas con dos bordes
    irregulares cada una. Medido después del cambio: las seis miden 60 px y
    comparten un único borde izquierdo.
    """
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    assert "flex-direction: column" in css.split(".sect-t {")[1].split("}")[0], (
        "el título y el resumen volvieron a enfrentarse a lo ancho")
    assert "min-height: 58px" in css, "se soltó la altura mínima de la fila"


def test_el_cuerpo_desplegado_cuelga_del_titulo():
    """El contenido de una sección abierta arranca donde arranca su título.

    Arrancaba 28 px más a la izquierda —pegado al borde de la tarjeta— y el
    desplegado no se apoyaba en nada. El padding izquierdo de 42 px es la suma
    de la fila: 10 de su padding + 20 de la columna del número + 12 del gap.
    """
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    import re
    m = re.search(r"\.sect-body \{ padding: [^;]*?(\d+)px; \}", css)
    assert m, "no se encontró el sangrado del cuerpo desplegado"
    assert m.group(1) == "44", (
        f"el cuerpo arranca a {m.group(1)}px y el título a 44: dejaron de estar alineados")


def test_no_quedan_tamanos_de_letra_fuera_de_escala():
    """Nada de 9 px ni de medios puntos.

    Había once tamaños distintos en Minado, incluidos 9 y 9.5. Eso no es una
    decisión de diseño: es el resultado de apretar un texto que no entraba. Lo
    que no entra se acorta, no se achica.
    """
    import re
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    medidas = {float(x) for x in re.findall(r"font-size:\s*([\d.]+)px", css)}
    decimales = sorted(x for x in medidas if x != int(x))
    chicas = sorted(x for x in medidas if x < 10)
    assert not decimales, f"tamaños con decimales: {decimales}"
    assert not chicas, f"tamaños por debajo de 10 px: {chicas}"


@pytest.mark.parametrize("vista", ["is", "oos", "todo"])
def test_las_tres_vistas_de_la_curva_tienen_su_rotulo(vista):
    """Se arman concatenando —t("ms." + v.id)— así que el examen general no las ve."""
    assert f'"ms.{vista}"' in DICC, f"falta el rótulo de la vista {vista}"


def test_el_score_pondera_el_tramo_reservado():
    """Con validación activada, el score no puede mirar sólo donde se buscó.

    Antes el puntaje que elige el campeón y ordena el databank se calculaba
    con el tramo de búsqueda únicamente: la mitad honesta estaba calculada y
    no pesaba. Una estrategia que rendía adentro y se caía afuera quedaba
    arriba de otra que sostenía en las dos.
    """
    miner = (Path(__file__).resolve().parents[1] / "botiquant" / "mining"
             / "miner.py").read_text(encoding="utf-8")
    assert "_ponderar_por_oos" in miner, "se quitó la ponderación por fuera de muestra"
    assert "score_is" in miner, "hay que conservar el score in-sample para poder compararlos"
    # no se premia por encima de 1: que el tramo reservado salga MEJOR es casi
    # siempre ruido de un tramo corto, no una virtud
    assert "min(float(q), 1.0)" in miner, "la ponderación volvió a premiar por encima de 1"


def test_el_capital_inicial_comprueba_algo():
    """El campo existía y no informaba nada.

    Medido: cambiarlo de 500 a 100.000 dólares deja CAGR, drawdown y profit
    factor idénticos — el riesgo porcentual escala todo por igual. Lo que sí
    cambia es el tamaño de la posición, y por debajo del mínimo del bróker el
    mínimo manda: pediste 1% y vas a arriesgar lo que el mínimo imponga.
    """
    assert "m-realidad" in APP, "se quitó el chequeo del capital"
    for clave in ("cap.fits", "cap.too_small", "cap.forced", "cap.check_broker"):
        assert f'"{clave}"' in DICC, f"falta el texto {clave}"
    from botiquant.data.catalog import CATALOG
    faltan = [c["key"] for c in CATALOG
              if not c.get("contract_size") or not c.get("min_lot")]
    assert not faltan, f"instrumentos sin especificación de contrato: {faltan}"


def test_la_cabecera_no_muestra_el_genoma_crudo():
    """Decía "SL=3×ATR · trail=1.5×ATR · máx 12 velas" en la primera línea.

    Es la notación interna del minero. Los valores crudos siguen enteros en
    "Reglas de la estrategia", que es donde alguien los busca a propósito.
    """
    assert "salidasEnCastellano" in APP
    assert "genes_label" not in APP.split('class="sheet-head"')[1].split("</div>")[0], (
        "volvió el genoma crudo a la cabecera")


def test_hay_una_escala_de_espaciado():
    """Veintiún valores distintos no son un sistema, son acumulación.

    Medido antes de tocar nada: 1, 2, 3, 4, 5, 6, 6.5, 7, 8, 9, 10, 11, 12,
    13, 14, 15, 16, 18, 20, 22, 24 px. Dos tarjetas que deberían respirar igual
    respiraban distinto por un píxel y nadie sabía por qué.
    """
    import re
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    valores = {float(x) for x in re.findall(
        r"\b(?:margin|padding|gap|row-gap|column-gap)[a-z-]*:\s*([\d.]+)px", css)}
    # el paso de la escala, más los hairlines de 1 y 2 px
    permitidos = {1, 2, 4, 6, 8, 12, 16, 20, 24, 30, 32, 34, 40, 48}
    fuera = sorted(v for v in valores if v not in permitidos and v < 32)
    assert not fuera, f"espaciados fuera de escala: {fuera}"


def test_el_foco_de_teclado_es_de_la_marca():
    """Era el anillo naranja de Chromium contra una interfaz teal.

    Sólo dos controles de un centenar tenían foco propio. Una sola regla, con
    :focus-visible para que un clic con el mouse no lo dibuje.
    """
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css
    assert "outline: 2px solid var(--accent)" in css, "el foco dejó de usar el color de la marca"


def test_el_anillo_del_minado_se_mueve_en_vez_de_rehacerse():
    """La transición estaba escrita y no podía correr nunca.

    `ringSvg` devuelve marcado nuevo con un id de gradiente aleatorio, así que
    reescribirlo reemplaza el nodo y el navegador no tiene desde dónde animar:
    el anillo saltaba de un valor al siguiente en cada consulta al servidor.
    """
    ch = (Path(__file__).resolve().parents[1] / "ui" / "charts.js").read_text(encoding="utf-8")
    assert "function ringUpdate(" in ch, "se quitó la actualización en sitio del anillo"
    assert "ringUpdate" in ch.split("return {")[-1], "ringUpdate no está exportada"
    assert "Charts.ringUpdate(" in APP, "el minado volvió a rehacer el anillo entero"


def test_las_estrategias_nuevas_se_distinguen_de_las_que_ya_estaban():
    """La tabla se redibuja entera cada pocos segundos.

    Sin marca, una estrategia recién aceptada aparecía indistinguible de las
    anteriores — y es lo único que uno mira mientras espera. Las filas llevan
    la clave del genoma porque el índice no sirve: cambia al reordenar.
    """
    assert 'data-key="${esc(r.id' in APP, "las filas perdieron su clave estable"
    assert "vistasBanco" in APP, "se quitó el registro de lo ya visto"
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    assert "tr.llegando" in css
    assert "prefers-reduced-motion" in css


def test_la_bienvenida_describe_la_aplicacion_que_existe():
    """Es la primera pantalla que ve alguien, y describía otra app.

    Prometía "cada estrategia guardada se puede juzgar sobre datos que nunca
    vio" — una función que está apagada — y cerraba con "los pasos numerados
    del menú son el mismo camino", cuando el menú ya no tiene números.

    El tercer paso real es exportar a MetaTrader, que además es el único que
    termina en algo que opera con plata.
    """
    assert '"wel.s3": ["Take it away"' in DICC, "el paso 3 volvió a prometer lo apagado"
    assert "MetaTrader" in DICC.split('"wel.s3_sub"')[1][:400]
    assert "numbered steps" not in DICC, "el pie vuelve a hablar de pasos numerados"
    assert "pasos numerados" not in DICC


def test_ningun_texto_vivo_promete_una_funcion_apagada():
    """Walk-forward, Monte Carlo y portafolio están construidos y apagados.

    Mientras AVANZADO sea false, ninguna pantalla puede nombrarlos: prometer un
    botón que no está es peor que no tener el botón.
    """
    import re
    ini = DICC.index("const STR = {")
    fin = DICC.index(chr(10) + "};", ini)
    DORMIDAS = ("mc.", "wf.", "pf.", "est.", "nav.montecarlo",
                "nav.walkforward", "nav.portfolio")
    patron = re.compile(r"monte\s*carlo|walk.?forward|portfolio|portafolio", re.I)
    clave, culpables, en_comentario = None, [], False
    for linea in DICC[ini:fin].split(chr(10)):
        # Los comentarios de bloque se saltean ENTEROS, no sólo su primera
        # línea: las de continuación no empiezan con asterisco y arrastraban la
        # última clave leída, marcando textos que no dicen nada de eso.
        crudo = linea.strip()
        if en_comentario:
            if "*/" in crudo:
                en_comentario = False
            continue
        if crudo.startswith("/*"):
            en_comentario = "*/" not in crudo
            continue
        if crudo.startswith("//"):
            continue
        m = re.match(r'\s{2}"([^"]+)":', linea)
        if m:
            clave = m.group(1)
        if not clave or clave.startswith(DORMIDAS):
            continue
        if patron.search(linea) and (f'"{clave}"' in APP or clave.startswith("wel.")):
            culpables.append(clave)
    assert not culpables, f"estos textos vivos prometen funciones apagadas: {culpables}"


def test_la_paleta_no_tiene_tintes_de_familia():
    """Cuatro pastel surtidos son la firma de un tablero genérico.

    Las baldosas de instrumento iban de índigo, celeste, ámbar y un teal que ni
    siquiera era el de la marca; los pasos de la guía, de índigo, teal, rosa y
    ámbar — un orden que además no significaba nada. En los dos casos el color
    era la cuarta vez que se decía algo que el icono, el ticker y la etiqueta
    ya decían, y la única que le costaba foco a la paleta.

    Medido: de 25 colores distintos en pantalla a 16.
    """
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    for tinte in ("--n-indigo", "--n-teal", "--n-pink", "--n-amber",
                  "--n-blue", "--n-violet"):
        assert tinte not in css, f"volvió el tinte {tinte}"
    assert "f-indigo" not in css and "g-pink" not in css
    assert "f-indigo" not in APP and "g-pink" not in APP


def test_las_sombras_salen_de_los_tokens():
    """Una sombra negra fija se ve como suciedad en tema claro.

    Había dos escritas a mano y un token inventado que no existía en ningún
    lado (`--sombra-sm`), así que ese elemento no tenía sombra ninguna.
    """
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    assert "rgba(0, 0, 0, .45)" not in css, "volvió una sombra negra fija"
    assert "--sombra-sm" not in css, "volvió el token de sombra que no existe"
    assert "--sombra-color" in css, "falta el color de sombra por tema"


def test_la_escala_de_radios_esta_cerrada():
    """Cinco escalones y ninguno entre medio: 4, 8, 12, 14 y la pastilla."""
    import re
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    literales = {int(x) for x in re.findall(r"border-radius:\s*(\d+)px", css)}
    permitidos = {1, 4, 8, 12, 14, 20, 999}
    fuera = sorted(literales - permitidos)
    assert not fuera, f"radios fuera de escala: {fuera}"
    tokens = dict(re.findall(r"(--r(?:-\w+)?):\s*(\d+)px", css))
    assert tokens.get("--r") == "12", "el radio de panel volvió a salirse de la escala"


def test_ningun_control_hereda_el_color_del_navegador():
    """Un botón sin `color` propio toma `canvastext`: negro puro en tema claro
    y blanco puro en oscuro. Ninguno de los dos está en la paleta."""
    css = (Path(__file__).resolve().parents[1] / "ui" / "styles.css").read_text(encoding="utf-8")
    bloque = css.split(".franjas button {")[1].split("}")[0]
    assert "color:" in bloque, "los botones de franja volvieron a quedarse sin color propio"


def test_el_estado_de_minado_se_restaura_al_volver_a_la_pantalla():
    """Salir de Minado con una búsqueda en curso y volver mostraba "Iniciar".

    El estado visible se aplicaba de forma imperativa dentro del manejador del
    botón —deshabilitar, mostrar Detener, bloquear la configuración— y al
    volver, `PAGES.mining` redibuja el marcado desde cero: nada de eso se
    reaplicaba.

    La búsqueda seguía corriendo en el servidor y no había forma de detenerla.
    Peor: apretar el botón lanzaba una SEGUNDA búsqueda encima de la primera.

    La corrección es que dibujar la pantalla y arrancar una búsqueda pasen por
    la misma función, así no pueden discrepar.
    """
    assert "function pintarEstadoMinado(" in APP, (
        "se quitó la función que centraliza el estado de los controles")
    # las tres llamadas: al dibujar la pantalla, al arrancar y al terminar
    assert APP.count("pintarEstadoMinado(") >= 4, (
        "falta alguna de las llamadas; si el estado vuelve a aplicarse suelto, "
        "volver a la pantalla lo pierde")
    assert "pintarEstadoMinado(S.mining);" in APP, (
        "la pantalla ya no restaura el estado de la búsqueda en curso")


def test_los_controles_de_minado_no_se_manipulan_sueltos():
    """Si alguien vuelve a tocar los controles fuera de la función, el estado
    se puede volver a desincronizar sin que nada avise."""
    import re
    sueltos = re.findall(r'\$\("#m-run"\)\.disabled\s*=', APP)
    assert not sueltos, (
        "el botón de minar se está habilitando o deshabilitando fuera de "
        "pintarEstadoMinado; eso es lo que causó el bug")
