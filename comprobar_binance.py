"""Comprueba la conexión con Binance, paso a paso, empezando por lo que no arriesga nada.

    python comprobar_binance.py

LAS CLAVES NO SE ESCRIBEN ACA NI SE PASAN POR LA LINEA DE COMANDOS. Salen de
dos variables de entorno, `BINANCE_API_KEY` y `BINANCE_SECRET`, o del `.env`
que ya está fuera del repositorio. Un secreto escrito en un argumento queda en
el historial de la terminal y en la lista de procesos de la máquina.

APUNTA AL TESTNET Y NO A LA CUENTA REAL. Para tocar la real hay que pasar
`--real` a propósito. Ningún error de configuración puede terminar operando con
plata de verdad por omisión.

QUE CLAVE CREAR:

  · Para probar: una cuenta de testnet en https://testnet.binancefuture.com —
    es gratis, tiene dinero falso y su propia clave, y no está conectada a
    ninguna cuenta real. Es el camino recomendado.
  · Para operar en serio: en Binance, una clave con permiso de **lectura y
    futuros, SIN retiro**. Aunque se la roben no pueden sacar fondos.

LOS PASOS VAN DE MENOS A MAS RIESGO, y se corta en el primero que falle:

    1. ¿responde Binance?                     no necesita clave
    2. ¿existe el contrato y cuáles son sus mínimos?   no necesita clave
    3. ¿la clave y la firma son correctas?     lee el saldo, no opera
    4. ¿en qué modo está la cuenta?            decide cómo se cierra
    5. ¿se leen las posiciones?                lee, no opera

NINGUN PASO MANDA UNA ORDEN. Lo que este comprobador NO puede verificar es la
forma exacta del pedido de una orden, y eso queda dicho al final en vez de
darlo por bueno.
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from botiquant.data.binance_trade import (BASE_PRUEBA, BASE_REAL,  # noqa: E402
                                          BinanceError, contrato,
                                          cuenta_minima, modo_posicion, ping,
                                          posicion, saldo)

BIEN, MAL, INFO = "  [ok]", "  [x] ", "  ->  "


def _linea(marca: str, texto: str) -> None:
    print(f"{marca} {texto}", flush=True)


def _clave() -> tuple[str, str]:
    """De las variables de entorno o del .env. Nunca de un argumento."""
    try:
        from dotenv import load_dotenv
        load_dotenv(pathlib.Path(__file__).with_name(".env"))
    except ImportError:
        pass
    return (os.environ.get("BINANCE_API_KEY", "").strip(),
            os.environ.get("BINANCE_SECRET", "").strip())


def main() -> int:
    real = "--real" in sys.argv
    base = BASE_REAL if real else BASE_PRUEBA
    simbolo = "BTCUSDT"

    print()
    print(f"Comprobando Binance · {'CUENTA REAL' if real else 'TESTNET (dinero falso)'}")
    print(f"  {base}")
    print()

    # 1 -----------------------------------------------------------------
    try:
        ping(base)
        _linea(BIEN, "Binance responde")
    except BinanceError as exc:
        _linea(MAL, f"no responde: {exc}")
        _linea(INFO, "Es un problema de red o de la URL, no de la clave.")
        return 1

    # 2 -----------------------------------------------------------------
    try:
        c = contrato(simbolo, base)
    except BinanceError as exc:
        _linea(MAL, str(exc))
        return 1
    _linea(BIEN, f"{simbolo}: mínimo {c['minimo']} · paso {c['paso']} · "
                 f"{c['decimales_cantidad']} decimales · "
                 f"nocional mínimo {c['minimo_nocional']:g} USDT")

    # LOS MINIMOS NO SON LOS MISMOS EN TESTNET Y EN REAL. Medido el 28/8/2026
    # en BTCUSDT: testnet acepta 0,0001 y la cuenta real pide 0,001. Probar en
    # uno y operar en el otro puede dar órdenes rechazadas sin motivo aparente.
    if not real:
        try:
            cr = contrato(simbolo, BASE_REAL)
            if cr["minimo"] != c["minimo"]:
                _linea(INFO, f"OJO: en la cuenta real el mínimo de {simbolo} es "
                             f"{cr['minimo']}, no {c['minimo']}. Una cantidad "
                             f"que entra acá puede rechazarse allá.")
        except BinanceError:
            pass

    clave, secreto = _clave()
    if not clave or not secreto:
        _linea(INFO, "Sin clave no se puede seguir. Poné BINANCE_API_KEY y "
                     "BINANCE_SECRET en el .env y volvé a correr esto.")
        _linea(INFO, "Para probar sin riesgo: creá una cuenta en "
                     "https://testnet.binancefuture.com — es gratis y usa "
                     "dinero falso.")
        return 0

    # 3 -----------------------------------------------------------------
    try:
        disponible = saldo(clave, secreto, base=base)
    except BinanceError as exc:
        _linea(MAL, f"la clave o la firma no pasan: {exc}")
        codigo = getattr(exc, "codigo", None)
        if codigo == -2015:
            _linea(INFO, "-2015 es clave inválida, sin permisos, o una IP no "
                         "autorizada en la lista blanca de la clave.")
        elif codigo == -1022:
            _linea(INFO, "-1022 es la firma: el texto firmado no coincide con "
                         "el que llegó.")
        _linea(INFO, "Y comprobá que la clave sea del MISMO entorno: una del "
                     "testnet no sirve en la cuenta real ni al revés.")
        return 1
    _linea(BIEN, f"clave y firma correctas · disponible {disponible:,.2f} USDT")

    # 4 -----------------------------------------------------------------
    try:
        modo = modo_posicion(clave, secreto, base=base)
    except BinanceError as exc:
        _linea(MAL, f"no se pudo leer el modo de posición: {exc}")
        return 1
    _linea(BIEN, f"modo de posición: {modo}")
    _linea(INFO, "En 'una_via' se cierra con reduceOnly; en 'cobertura' con "
                 "positionSide. Mandar el otro da -4061 o -1106.")

    # 5 -----------------------------------------------------------------
    try:
        p = posicion(simbolo, clave, secreto, base=base)
    except BinanceError as exc:
        _linea(MAL, f"no se pudieron leer las posiciones: {exc}")
        return 1
    _linea(BIEN, "posición abierta: " + (
        f"{'largo' if p['lado'] > 0 else 'corto'} {p['cantidad']:g} "
        f"desde {p['precio_entrada']:,.2f}" if p["lado"] else "ninguna"))

    # cuánta cuenta hace falta, con los mínimos REALES de este entorno
    if disponible > 0:
        try:
            import httpx
            precio = float(httpx.get(f"{base}/fapi/v1/ticker/price",
                                     params={"symbol": simbolo},
                                     timeout=15).json()["price"])
            falta = cuenta_minima(precio, c, stop_pct=2.0, riesgo_pct=1.0)
            print()
            _linea(INFO, f"Con stop del 2% y riesgo del 1%, la orden más chica "
                         f"posible en {simbolo} necesita una cuenta de "
                         f"{falta:,.0f} USDT. En un portafolio eso es POR "
                         f"estrategia, porque cada una maneja su porción.")
            if disponible < falta:
                _linea(MAL, f"con {disponible:,.2f} USDT el bot no va a poder "
                            f"abrir: el tamaño que sale del riesgo pedido queda "
                            f"debajo del mínimo.")
        except Exception:                                     # noqa: BLE001
            pass

    print()
    print("  Lo que esto NO comprobó: mandar una orden. La forma exacta del")
    print("  pedido de orden no se puede verificar sin operar, así que ese paso")
    print("  se prueba en el testnet desde la aplicación y no desde acá.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
