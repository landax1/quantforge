"""Catalogue of ready-to-mine instruments.

Each entry carries the Dukascopy symbol used to fetch history plus the broker
cost profile that instrument actually trades at, so the mining page can preset
spread and slippage instead of asking the user to guess.

``direction`` es la direccion que conviene buscar en ese instrumento, y sale
de medir, no de razonar. Se razono primero y se razono mal: "solo los indices
tienen deriva al alza". Los numeros dicen otra cosa — 200 candidatas por
instrumento, 1h, diez anios, riesgo 1%, misma vara, contando las que dan
profit factor >= 1:

                  solo largos   ambas
    SP500                 123      40
    XAUUSD                101      33
    BTCUSD                 76      39
    EURUSD                 12      12   (pero ambas llega a +2% y largos no)

El oro y el Bitcoin tambien subieron estos diez anios, asi que shortearlos es
pelear contra la tendencia de fondo. El unico sin deriva es el par de divisas,
y ahi permitir cortos sube el techo de 1.92% a 4.05% anual.

``aliases`` son los nombres con los que uno se puede encontrar este mismo
mercado en la lista de simbolos de un broker. No es cosmetico: al probar
el EA del S&P en el tester, MetaTrader contesto "symbol SP500 not exist"
porque ese servidor lo llama US500. El bot estaba bien y no operaba nunca.

``min_cagr`` es el rendimiento anual que conviene exigir en ese mercado, y
tambien sale de medir. Los techos, sobre 200 candidatas con la misma vara:
S&P 14,95%, oro 20,20%, Bitcoin 21,84% y EURUSD 4,05%. Pedirle 3% a los
cuatro trata como iguales a mercados que no lo son: en EURUSD eso equivale a
exigir casi el maximo posible, y la busqueda se va a decenas de minutos.

``fuente`` dice de donde se baja el historico. Existe porque hay dos tipos de
instrumento con costos que funcionan distinto:

  · ``dukascopy`` son CFD. El costo esta en el SPREAD, en unidades de precio.
  · ``binance`` son perpetuos de exchange. El libro es ajustado, asi que el
    spread es despreciable y el costo real es la COMISION, en % del nocional.
    Ademas cobran o pagan ``funding`` cada ocho horas por tener la posicion
    abierta, que el CFD no tiene.

La diferencia no es menor. Medido, ida y vuelta como % del precio: nuestro
spread de S&P son 0,0072% y la comision taker de un exchange es 0,10% — trece
veces mas. En Bitcoin la brecha se achica a 3,6x con taker y 1,4x con maker,
porque su spread ya es alto. Por eso cripto es el mercado donde el exchange
tiene sentido y los indices no.

``dukascopy_api`` es el codigo con el que ese instrumento se identifica en la
API de Dukascopy —``USD-JPY``, ``DEU.IDX-EUR``— y sirve para preguntarle la
escala de precios. Es OBLIGATORIO en todo instrumento de Dukascopy que no sean
los cuatro originales, y no es burocracia: sin el, el historico se baja con los
precios divididos por cien y NO falla nada. El Dow a 387 en vez de 38.753, el
backtest corre, las metricas salen, y son de un mercado que no existe. Hay una
prueba que lo exige (tests/test_catalogo_escalas.py).

``contract_size`` y ``min_lot`` son REFERENCIAS, igual que el spread: cada
broker define las suyas y la pantalla dice que hay que comprobarlas. Existen
para poder contestar la unica pregunta que el capital inicial deberia contestar
y no contestaba: con esta plata y este riesgo, la posicion que sale, ¿el broker
la acepta? Si no la acepta, el minimo obliga a arriesgar mas de lo pedido y el
usuario se entera recien operando con plata de verdad.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

from botiquant.data.loader import parse_ohlcv_csv
from botiquant.data.dukascopy import descargar as descargar_dukascopy

# Server-time offset applied to Dukascopy UTC data so mined session rules match
# what an MT5 EA sees on a GMT+3 broker (New York + 7).
SERVER_TZ_OFFSET_HOURS = 7

CATALOG: list[dict[str, Any]] = [
    {
        "key": "sp500",
        "label": "SP500",
        "full_name": "S&P 500 index CFD",
        "dukascopy": "usa500idxusd",
        "category": "indices",
        "from": "2013-01-01",
        "spread": 0.36,
        "slippage": 0.1,
        "stop_points": 40.0,
        "target_points": 80.0,
        "contract_size": 100,
        "min_lot": 0.1,
        "min_cagr": 3.0,
        "aliases": ["SP500", "US500", "SPX500", "S&P500", "USA500", "US500Cash"],
        "direction": "long",
        "mejor_rendimiento": True,
    },
    {
        "key": "eurusd",
        "label": "EURUSD",
        "full_name": "Euro / US Dollar",
        "dukascopy": "eurusd",
        "category": "forex",
        "from": "2005-01-01",
        "spread": 0.00012,
        "slippage": 0.00003,
        "stop_points": 0.0060,
        "target_points": 0.0120,
        "contract_size": 100000,
        "min_lot": 0.01,
        "min_cagr": 1.0,
        "aliases": ["EURUSD"],
        "direction": "both",
    },
    {
        "key": "xauusd",
        "label": "XAUUSD",
        "full_name": "Oro / US Dollar",
        "dukascopy": "xauusd",
        "category": "metals",
        "from": "2010-01-01",
        "spread": 0.25,
        "slippage": 0.05,
        "stop_points": 18.0,
        "target_points": 36.0,
        "contract_size": 100,
        "min_lot": 0.01,
        "min_cagr": 3.0,
        "aliases": ["XAUUSD", "GOLD", "XAUUSD.spot"],
        "direction": "long",
    },
    {
        "key": "btcusd",
        "label": "BTCUSD",
        "full_name": "Bitcoin CFD (para MetaTrader)",
        "dukascopy": "btcusd",
        "category": "crypto",
        "from": "2017-01-01",
        "spread": 12.0,
        "slippage": 3.0,
        "stop_points": 900.0,
        "target_points": 1800.0,
        "contract_size": 1,
        "min_lot": 0.01,
        "min_cagr": 3.0,
        # "BTCUSDT" NO es alias de este: es el nombre del perpetuo, que es
        # otro instrumento con otros costos. Estaba de cuando el perpetuo no
        # existia, y buscarlo devolvia el CFD.
        "aliases": ["BTCUSD", "Bitcoin CFD"],
        "direction": "long",
    },
    # ── Los que agregan una apuesta y no un nombre ───────────────────────
    #
    # MEDIDO sobre retornos diarios 2021-2025, correlacion media contra los
    # cuatro de arriba. Los dos primeros son los que menos se parecen a lo que
    # ya habia; los que quedaron afuera estan al final y dicen por que.
    #
    #     Bund      0,092      <- renta fija: el sector que faltaba entero
    #     WTI       0,110
    #     ...
    #     plata     0,391      (0,751 contra el oro: es la misma apuesta)
    #     Nasdaq    0,426      (0,948 contra el S&P)
    #     Dow       0,444      (0,913 contra el S&P)
    #
    # El `spread` de los dos sale de medir BID contra ASK en Dukascopy con
    # botiquant/data/spread.py, no de estimarlo. NO esta calibrado a un broker
    # retail y no se puede: sobre los cuatro instrumentos donde conocemos las
    # dos puntas, la razon fue 4,0x / 0,7x / 0,7x / 0,2x, o sea que no hay
    # recargo estable. En los tres que no son divisas Dukascopy resulto MAS
    # ANCHO que lo que el catalogo asumia, asi que usarlo directo peca de caro
    # y no de barato — que es el lado en el que conviene equivocarse.
    {
        "key": "bund",
        "label": "BUND",
        "full_name": "Euro Bund (bono aleman a 10 anios)",
        "dukascopy": "bundtreur",
        "dukascopy_api": "BUND.TR-EUR",
        "category": "bonos",
        "from": "2016-05-02",
        "spread": 0.053,          # medido: 0,0398% del precio, 2.315 minutos
        "slippage": 0.02,
        "stop_points": 0.67,
        "target_points": 1.34,
        "contract_size": 1000,
        "min_lot": 0.1,
        "min_cagr": 1.0,
        "aliases": ["BUND", "FGBL", "EUROBUND", "GERMANY10Y", "DE10YB"],
        # Un bono no tiene la deriva al alza de un indice: sube cuando bajan
        # las tasas y baja cuando suben, y estos anios hizo las dos cosas. Sin
        # deriva, permitir cortos es lo que da la mitad del espacio de busqueda
        # — el mismo motivo por el que EURUSD esta en "both".
        "direction": "both",
    },
    {
        "key": "gas",
        "label": "GAS",
        "full_name": "Gas natural (Henry Hub)",
        "dukascopy": "gascmdusd",
        "dukascopy_api": "GAS.CMD-USD",
        "category": "energia",
        "from": "2012-09-02",
        # MEDIDO sobre cuatro dias entre 2021 y 2025, leyendo BID y ASK del
        # datafeed: 0,0102 / 0,0105 / 0,0103 / 0,0105. En unidades de precio es
        # casi constante; el porcentaje NO, porque el gas fue de 1,94 a 6,12 y
        # el mismo centavo cuesta 0,17% o 0,53% segun cuando.
        #
        # (Se mide por archivos y no por la API de minutos como los otros dos:
        # este instrumento publica BID y no ASK ahi. Diez fechas probadas.)
        "spread": 0.0104,
        "slippage": 0.004,
        "stop_points": 0.02,
        "target_points": 0.04,
        "contract_size": 1000,
        "min_lot": 0.01,
        "min_cagr": 1.0,
        "aliases": ["GAS", "NATGAS", "NG", "XNGUSD", "NATURALGAS", "GASUSD"],
        # El que menos se parece a todo lo demas: 0,048 de correlacion media
        # contra los cuatro originales, y 0,14 contra el petroleo, que es la
        # otra energia. La EIA fecha el desacople del crudo en junio de 2009,
        # con el shale: al gas lo mueven el clima y el almacenamiento
        # regional, que no mueven nada mas.
        #
        # OJO CON ESE 0,048: esta medido sobre 2022 y 2025 nada mas. Los otros
        # tres anios los rechaza la API de velas diarias de forma permanente
        # —mismo instrumento, anios contiguos, uno contesta y el otro no— asi
        # que apoya en menos datos que el resto de la tabla.
        "direction": "both",
    },
    {
        "key": "wti",
        "label": "WTI",
        "full_name": "Petroleo WTI (Light Sweet Crude)",
        "dukascopy": "lightcmdusd",
        "dukascopy_api": "LIGHT.CMD-USD",
        "category": "energia",
        "from": "2011-09-23",
        "spread": 0.05,           # medido: 0,0571% del precio, 4.059 minutos
        "slippage": 0.02,
        "stop_points": 0.44,
        "target_points": 0.88,
        "contract_size": 1000,
        "min_lot": 0.01,
        "min_cagr": 1.0,
        "aliases": ["WTI", "USOIL", "CL", "CRUDE", "OIL", "USOUSD", "XTIUSD"],
        # El petroleo tampoco tiene deriva: 2020 lo dejo en negativo y 2022 lo
        # llevo a 120. Cortos permitidos por el mismo motivo que el Bund.
        "direction": "both",
    },
    # ── Perpetuos de exchange ────────────────────────────────────────────
    #
    # `oculto` LOS SACA DE LA VITRINA, NO DEL PROGRAMA.
    #
    # El producto apunta hoy a un portafolio de EA para MetaTrader, y en esa
    # vitrina un CFD de Bitcoin y un perpetuo de Bitcoin se leen como el mismo
    # instrumento repetido: se llaman igual salvo una letra y son cosas
    # distintas —uno paga spread y se opera por MetaTrader, el otro paga
    # comisión y funding y se opera en un exchange—. Mostrar los dos obliga a
    # entender esa diferencia antes de poder elegir nada.
    #
    # Se OCULTAN y no se borran, por dos motivos concretos:
    #   · quien ya bajó el perpetuo tiene datos y estrategias sobre él, y
    #     borrarlo de acá le dejaría el instrumento sin sus costos: minaría
    #     con el spread de otro sin que nada fallara.
    #   · el plan es volver a ellos, construyendo sobre Binance primero.
    # Se bajan de Binance y no del exchange donde se opera. Medido: BTCUSDT en
    # Binance y en BingX correlacionan 0,99974 en sus movimientos, con 0,0019%
    # de diferencia media de precio — cien veces menos que la comision de una
    # operacion. Y Binance da siete anios de historia contra los nueve meses de
    # BingX. Se mina con los datos buenos y se ejecuta donde haya cuenta.
    #
    # `spread` en cero NO es un olvido: en un libro de ordenes el costo es la
    # comision, y ponerlo tambien como spread seria cobrarlo dos veces.
    {
        "key": "btcusdt",
        "oculto": True,
        "label": "BTCUSDT",
        "full_name": "Bitcoin perpetuo (para exchange)",
        "fuente": "binance",
        "binance": "BTCUSDT",
        "category": "perpetuos",
        "from": "2019-09-08",
        "spread": 0.0,
        "slippage": 3.0,
        "commission_pct": 0.04,
        "stop_points": 800.0,
        "target_points": 1600.0,
        "contract_size": 1,
        "min_lot": 0.001,
        "min_cagr": 3.0,
        "aliases": ["BTCUSDT", "BTC-USDT", "BTCUSD", "BTCPERP"],
        # Bitcoin subio estos anios, pero a diferencia de los indices el
        # funding le PAGA al lado corto: sobre siete anios la tasa media fue
        # +11,61% anual, cobrada por los vendedores. Se permiten las dos
        # direcciones para que la busqueda pueda encontrar esa familia.
        "direction": "both",
        "mejor_rendimiento": False,
    },
    {
        "key": "ethusdt",
        "oculto": True,
        "label": "ETHUSDT",
        "full_name": "Ethereum perpetuo (para exchange)",
        "fuente": "binance",
        "binance": "ETHUSDT",
        "category": "perpetuos",
        "from": "2019-11-27",
        "spread": 0.0,
        "slippage": 0.2,
        "commission_pct": 0.04,
        "stop_points": 60.0,
        "target_points": 120.0,
        "contract_size": 1,
        "min_lot": 0.001,
        "min_cagr": 3.0,
        "aliases": ["ETHUSDT", "ETH-USDT", "ETHUSD", "ETHPERP"],
        "direction": "both",
        "mejor_rendimiento": False,
    },
]

BY_KEY = {c["key"]: c for c in CATALOG}


def default_stop_points(last_close: float) -> tuple[float, float]:
    """Distancias de SL/TP razonables para un instrumento, en unidades de precio.

    Un stop se expresa en puntos absolutos, así que 200 puntos son medio
    razonables en un índice de 7000 y literalmente imposibles en EURUSD a
    1.15: el precio nunca recorre esa distancia, la estrategia no cierra
    nunca y la búsqueda entera devuelve cero. Escalar al precio (~0.5% para
    el stop, el doble para el target) mantiene el mismo comportamiento en
    cualquier mercado; se redondea a 2 cifras significativas para que el
    número que ve el usuario sea legible.
    """
    price = abs(float(last_close or 0.0))
    if price <= 0:
        return 200.0, 400.0
    stop = price * 0.005
    exp = math.floor(math.log10(stop))
    stop = round(stop, -(exp - 1))          # 2 cifras significativas
    return stop, stop * 2


def to_server_time(df: pd.DataFrame) -> pd.DataFrame:
    """Shift a UTC-indexed frame to broker server time (NY+7)."""
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York")
    shifted = ny + pd.Timedelta(hours=SERVER_TZ_OFFSET_HOURS)
    out = df.copy()
    out.index = pd.DatetimeIndex(shifted.tz_localize(None))
    return out


#: El tamano minimo de orden de cada perpetuo, leido de la ficha de contrato de
#: BingX el 26 de agosto de 2026. Lo usa el exportador de Pine como piso del
#: tamano: sin esto el script hereda el piso de UN contrato, que en Bitcoin son
#: ochenta mil dolares y hace que una cuenta chica no pueda abrir nada.
#:
#: Va aca y no se consulta a la API en cada exportacion porque exportar tiene
#: que funcionar sin internet; y va con el minimo real y no con un valor
#: prudente inventado, porque un piso de mas obliga a arriesgar de mas.
MINIMOS_PERPETUO = {
    "BTCUSDT": 0.0001,
    "ETHUSDT": 0.01,
}


def simbolo_fuente(entry: dict) -> str:
    """El nombre del instrumento en SU fuente.

    Existe porque el catálogo dejó de tener una sola: un CFD se identifica por
    su símbolo de Dukascopy y un perpetuo por el de Binance. Todo lo que antes
    leía `entry["dukascopy"]` directo rompía al aparecer el primer instrumento
    que no viene de ahí.
    """
    return entry.get(entry.get("fuente", "dukascopy"), entry["label"])


def download(key: str, workdir: Path, date_from: str | None = None,
             date_to: str | None = None,
             progress=None) -> pd.DataFrame:
    """Trae el histórico M1 de un instrumento del catálogo desde Dukascopy.

    Antes esto invocaba `npx dukascopy-node`. Funcionaba en una máquina de
    desarrollo y fallaba en la de cualquier usuario: el .exe no lleva Node y
    casi nadie lo tiene instalado, así que la aplicación se descargaba vacía y
    su único modo de conseguir datos daba un error sobre `npx`.

    Ahora se baja en Python. Lo único que sigue necesitando es conexión, y sólo
    cuando el usuario la pide.
    """
    entry = BY_KEY.get(key)
    if entry is None:
        raise ValueError(f"Instrumento desconocido: {key}")

    fuente = entry.get("fuente", "dukascopy")

    def avance(frac: float, msg: str) -> None:
        if progress:
            progress(0.02 + frac * 0.88, f"{entry['label']} · {msg}")

    if fuente == "binance":
        # Un perpetuo de exchange ya viene en UTC y no pasa por el ajuste de
        # hora de servidor: ese ajuste existe para alinear los CFD con el
        # horario del broker, y un mercado que opera 24/7 no tiene sesiones
        # que alinear.
        from botiquant.data.binance import descargar as descargar_binance
        if progress:
            progress(0.02, f"Conectando con Binance para {entry['label']}…")
        return descargar_binance(entry["binance"],
                                 date_from or entry["from"],
                                 date_to or _today(),
                                 intervalo="1m", progreso=avance)

    if progress:
        progress(0.02, f"Conectando con Dukascopy para {entry['label']}…")
    df = descargar_dukascopy(entry["dukascopy"],
                             date_from or entry["from"],
                             date_to or _today(),
                             progreso=avance,
                             codigo_api=entry.get("dukascopy_api", ""))
    if progress:
        progress(0.95, "Convirtiendo a hora del servidor…")
    return to_server_time(df)


def _today() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%d")
