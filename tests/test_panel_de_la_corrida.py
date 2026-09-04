"""El panel que queda después de generar, y qué se puede hacer con esas filas.

Sus filas salen del minero, no del repositorio: no traen el `guardada` que
calcula el servidor, así que la pantalla tiene que deducirlo sola. Y en cripto
no tiene sentido generar estrategias que después el robot va a rechazar.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
APP = (RAIZ / "ui" / "app.js").read_text(encoding="utf-8")
API = (RAIZ / "botiquant" / "api" / "app.py").read_text(encoding="utf-8")
GEN = (RAIZ / "botiquant" / "generator" / "generator.py").read_text(encoding="utf-8")


def test_en_cripto_se_genera_sin_trailing():
    """Una candidata con stop dinámico no se puede activar en un exchange.

    El robot deja UNA orden puesta y no la mueve, así que operaría con un stop
    fijo que no es lo que se midió; el servidor la rechaza al activarla. El
    generador sortea el trailing y la mayoría de sus opciones lo activan, de
    modo que sin este pedido más de la mitad de lo generado a mano nacía
    inservible. En MetaTrader sí se queda: el robot exportado lo reproduce.
    """
    pedido = APP[APP.index('runJob("/api/mine"'):]
    pedido = pedido[:pedido.index("}, j => {")]
    assert 'S.mundo === "exchange" ? { sin_trailing: true }' in pedido, (
        "la generación en cripto tiene que pedir sin_trailing")
    # y el servidor tiene que seguir escuchando ese pedido
    assert 'sin_trailing=bool(payload.get("sin_trailing"))' in API, (
        "el endpoint de minado dejó de leer sin_trailing")
    # el sorteo sigue teniendo opciones con trailing: si esto cambiara, la
    # regla de arriba sobraría y habría que revisarla
    m = re.search(r"TRAIL_CHOICES:[^=]*=\s*\(([^)]*)\)", GEN)
    assert m, "se fue TRAIL_CHOICES del generador"
    valores = [float(x) for x in m.group(1).replace(" ", "").split(",") if x]
    assert any(v > 0 for v in valores), "ya no se sortea trailing: revisar esta regla"


def test_el_panel_sabe_cuales_ya_mando():
    """Decía "Enviar las 10 a validación" con las diez ya enviadas.

    Las filas del panel vienen del minero y no traen `guardada`, así que
    mirarlo daba siempre "faltan todas". La pantalla lo deduce de `S.saved`,
    que ya tiene de qué corrida salió cada estrategia guardada.
    """
    cuerpo = APP[APP.index("function renderMining"):]
    cuerpo = cuerpo[:cuerpo.index("\nfunction ")]
    assert "guardadasDeLaCorrida" in cuerpo and "const porMandar" in cuerpo, (
        "el panel dejó de calcular cuáles faltan mandar")
    # `bank` son las filas del minero. Filtrarlas por `guardada` es el error
    # que se vino a sacar; sobre las filas de /api/banco sí es válido, y por eso
    # se busca la expresión exacta y no la palabra suelta.
    assert "bank.filter(f => !f.guardada)" not in cuerpo, (
        "volvió a contar sobre `guardada`, que en las filas del minero no viene")
    # y tanto el botón del encabezado como la barra del pie cuentan lo mismo
    assert cuerpo.count("porMandar.length") >= 2, (
        "el botón y la barra del pie tienen que contar las mismas")


def test_el_nombre_al_guardar_es_el_mismo_de_los_dos_lados():
    """Reconocer una fila entre las guardadas depende de esa regla.

    El servidor le agrega el mercado al nombre al guardar —S-001 pasa a
    S-001-BTC— y la pantalla la repite para saber si una fila ya está. Si allá
    se cambia el sufijo y acá no, el panel vuelve a ofrecer lo ya enviado.
    """
    servidor = API[API.index("def _nombre_con_mercado"):]
    servidor = servidor[:servidor.index("\n    @app.post")]
    cliente = APP[APP.index("function nombreAlGuardar"):]
    cliente = cliente[:cliente.index("\n}")]
    # los dos recortan los sufijos de moneda y se quedan con cinco caracteres
    for pieza in ("USDT", "USD", "BUSD", "USDC"):
        assert pieza in servidor and pieza in cliente, f"{pieza} sólo está de un lado"
    assert "[:5]" in servidor and ".slice(0, 5)" in cliente, (
        "el largo del sufijo dejó de coincidir")


def test_tildar_una_fila_no_abre_su_ficha():
    """El clic en la fila abre el inspector; el clic en la casilla, no.

    Sin esto, elegir tres candidatas abría tres veces la ficha encima de la
    tabla y había que cerrarla cada vez.
    """
    cuerpo = APP[APP.index('$$("[data-row]", bankBox)'):]
    cuerpo = cuerpo[:cuerpo.index("refrescarBoton")]
    assert 'ev.target.closest(".tick")' in cuerpo, (
        "tildar volvió a abrir la ficha de la estrategia")
