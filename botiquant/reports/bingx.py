"""El archivo que enlaza una estrategia con un exchange.

QUÉ ES Y QUÉ NO ES. Los otros dos exportadores generan CÓDIGO: un .mq5 que se
compila en MetaEditor, un .pine que se pega en TradingView. Éste no genera
código, genera una DESCRIPCIÓN — porque del otro lado no hay una plataforma que
sepa leer estrategias, hay una API que recibe órdenes. Quien ejecuta es un
programa nuestro, y este archivo es lo que le dice qué ejecutar.

Eso lo hace más simple y más peligroso a la vez. Más simple porque no hay que
traducir la lógica a otro lenguaje —el mismo motor que corrió el backtest es el
que va a evaluar las reglas en vivo, así que no puede haber discrepancia de
traducción, que es de donde salen la mitad de los problemas del .mq5. Más
peligroso porque un .pine mal exportado te muestra un gráfico raro y este
archivo mal exportado manda órdenes con plata.

LO QUE NUNCA VA ADENTRO. La clave de API del usuario. Este archivo describe una
estrategia y se puede mandar por mail sin consecuencias; la clave vive cifrada
en la máquina de quien opera y no toca esto ni de lejos. Si algún día alguien
propone "meter la clave para que sea un solo archivo", la respuesta es no.

POR QUÉ VIAJAN LOS DOS SÍMBOLOS. Se mina con datos de Binance y se opera en
BingX, y NO son el mismo instrumento. Medido: correlacionan 0,99974 con 0,0019%
de diferencia media de precio —cien veces menos que la comisión de una
operación, o sea irrelevante para decidir— pero irrelevante no es idéntico. El
archivo dice de dónde salieron los datos y dónde se va a operar, separados, para
que nadie tenga que adivinarlo después.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from botiquant.core.models import StrategySpec

#: La versión del formato. Un runner viejo con un archivo nuevo tiene que
#: negarse a operar, no interpretar lo que entienda: ejecutar la mitad de una
#: estrategia es peor que no ejecutarla.
VERSION = 1

FORMATO = "botiquant-bot"

#: Binance escribe BTCUSDT y BingX escribe BTC-USDT. La cuenta base/cotización
#: no se puede partir por longitud fija: hay cotizaciones de tres letras (USD)
#: y de cuatro (USDT, USDC), y BTCUSDC partido a lo bruto da "BTCU" + "SDC".
COTIZACIONES = ("USDT", "USDC", "BUSD", "USD")


def a_simbolo_bingx(simbolo: str) -> str:
    """BTCUSDT -> BTC-USDT. Devuelve el original si no lo reconoce.

    No adivina: si el símbolo no termina en una cotización conocida se devuelve
    tal cual y que falle del lado del exchange con su propio mensaje. Inventar
    un guion en el lugar equivocado daría un símbolo que existe pero es otro.
    """
    s = simbolo.upper().replace("-", "")
    for cot in COTIZACIONES:
        if s.endswith(cot) and len(s) > len(cot):
            return f"{s[:-len(cot)]}-{cot}"
    return simbolo


def export_bingx(spec: StrategySpec, *, name: str = "BQ Bot",
                 symbol_source: str = "", timeframe: str = "1h",
                 metrics: dict[str, Any] | None = None,
                 costs: dict[str, Any] | None = None,
                 measured_from: str = "", measured_to: str = "") -> str:
    """El archivo de enlace, como JSON con sangría.

    Con sangría a propósito: es un archivo que alguien va a abrir para
    entender qué está corriendo, y un JSON en una sola línea de cuatro mil
    caracteres no se puede leer. Pesa unos kilobytes; el espacio no importa.
    """
    origen = (symbol_source or "").upper()
    doc: dict[str, Any] = {
        "formato": FORMATO,
        "version": VERSION,
        "creado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "nombre": name,

        # DÓNDE SE VA A OPERAR
        "ejecucion": {
            "exchange": "bingx",
            "simbolo": a_simbolo_bingx(origen),
            "timeframe": timeframe,
            "tipo_orden": "market",
            # Sin apalancamiento por defecto. El backtest midió con el tamaño
            # que dice `risk`, y multiplicarlo del lado del exchange haría que
            # lo que opera no sea lo que se midió.
            "apalancamiento": 1,
        },

        # DE DÓNDE SALIERON LOS DATOS. No es lo mismo y por eso va aparte.
        "medido_en": {
            "fuente": "binance",
            "simbolo": origen,
            "desde": measured_from,
            "hasta": measured_to,
        },

        # QUÉ EJECUTAR. Es el mismo diccionario que come el motor.
        "estrategia": spec.to_dict(),

        # CON QUÉ COSTOS SE MIDIÓ. Va para poder comparar después lo que
        # rindió de verdad contra lo que decía el backtest: si difieren mucho,
        # el primer sospechoso son los costos.
        "costos": dict(costs or {}),

        # QUÉ DIO EN EL BACKTEST. Viaja para que quien arranque el bot vea
        # sobre qué se está parando sin tener que abrir la aplicación.
        "respaldo": dict(metrics or {}),
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def leer_bingx(texto: str) -> dict[str, Any]:
    """Valida un archivo de enlace y lo devuelve, o explica por qué no sirve.

    Lo usa el runner antes de conectarse a ningún lado. Todo lo que puede
    fallar acá es gratis; lo que falle después ya cuesta plata.
    """
    try:
        doc = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ValueError(f"El archivo no es un JSON válido: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("formato") != FORMATO:
        raise ValueError("Ese archivo no lo exportó Botiquant.")
    v = doc.get("version")
    if not isinstance(v, int) or v > VERSION:
        raise ValueError(
            f"El archivo es de una versión más nueva ({v}) que este programa "
            f"(entiende hasta la {VERSION}). Actualizá antes de operarlo.")
    if not doc.get("estrategia"):
        raise ValueError("El archivo no trae ninguna estrategia adentro.")
    simbolo = ((doc.get("ejecucion") or {}).get("simbolo") or "").strip()
    if not simbolo:
        raise ValueError("El archivo no dice en qué símbolo operar.")
    # Que el spec se pueda reconstruir es parte de la validacion: un JSON bien
    # formado con reglas incoherentes adentro pasaria las comprobaciones de
    # arriba y reventaria recien al evaluar la primera vela.
    try:
        StrategySpec.from_dict(doc["estrategia"])
    except Exception as exc:
        raise ValueError(f"La estrategia del archivo no se pudo leer: {exc}") from exc
    return doc
