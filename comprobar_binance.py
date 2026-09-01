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

LOS PASOS 1 A 5 NO MANDAN NINGUNA ORDEN.

===========================================================================
EL PASO 6 SI: ABRE, PROTEGE Y CIERRA
===========================================================================

Corre con `--operar`, y POR OMISION CONTRA EL TESTNET, donde el dinero es falso
y equivocarse no cuesta nada. Para hacerlo en la cuenta real hay que agregar
`--real` a propósito, y ademas escribir una palabra a mano antes de cada orden.

Es la ida y vuelta mas chica que el exchange acepta, y comprueba las tres cosas
que no se pueden comprobar sin operar:

  · que la orden entre, y a cuanto entro;
  · QUE EL STOP QUEDE REGISTRADO EN BINANCE, preguntando por las ordenes
    abiertas. Que `proteger` no falle solo dice que el pedido se acepto;
  · que la orden de cierre CIERRE, y no abra el lado contrario — que es lo que
    pasaba en BingX cuando faltaba `reduceOnly`.

El stop va 5% abajo y el objetivo 10% arriba: la prueba es que queden anotados,
no que se disparen.
"""

from __future__ import annotations

import os
import pathlib
import sys
from decimal import ROUND_UP, Decimal

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from botiquant.data.binance_trade import (BASE_PRUEBA, BASE_REAL,  # noqa: E402
                                          BinanceError, _pedir, abrir,
                                          cancelar_todo, cerrar,
                                          condicionales_abiertas, contrato,
                                          cuenta_minima, detalle_orden,
                                          modo_posicion, ordenes_abiertas,
                                          ping, posicion, proteger, saldo)

BIEN, MAL, INFO, OJO = "  [ok]", "  [x] ", "  ->  ", "  !!  "


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


def _precio(simbolo: str, base: str) -> float:
    return float(_pedir("/fapi/v1/ticker/price", {"symbol": simbolo},
                        base=base)["price"])


def _cantidad_minima(precio: float, c: dict) -> float:
    """La orden mas chica que el exchange acepta, redondeada HACIA ARRIBA.

    Al reves que al operar, y a proposito: dimensionando por riesgo se redondea
    hacia abajo para no arriesgar de mas, pero aca se busca el minimo VALIDO y
    hacia abajo quedaria justo por debajo.

    Se miran LOS DOS minimos —cantidad y nocional— porque son limites distintos
    y pasar uno no dice nada del otro.
    """
    paso = Decimal(str(c["paso"] or 0))
    por_cantidad = Decimal(str(c["minimo"]))
    por_nocional = (Decimal(str(c["minimo_nocional"])) / Decimal(str(precio))
                    if c.get("minimo_nocional") else Decimal(0))
    n = max(por_cantidad, por_nocional)
    if paso > 0:
        n = (n / paso).to_integral_value(rounding=ROUND_UP) * paso
    return float(n)


def _confirmar(palabra: str, texto: str) -> bool:
    print()
    print(texto)
    try:
        return input(f"  Escribi {palabra} para seguir (cualquier otra cosa "
                     f"cancela): ").strip() == palabra
    except EOFError:
        print("  (sin terminal interactiva: cancelado)")
        return False


def _ida_y_vuelta(simbolo: str, clave: str, secreto: str, modo: str,
                  c: dict, base: str, real: bool) -> int:
    """El unico paso que manda ordenes. Ver el encabezado del archivo."""
    precio = _precio(simbolo, base)
    qty = _cantidad_minima(precio, c)
    stop, objetivo = precio * 0.95, precio * 1.10

    print()
    print("=" * 70)
    print("  ESTO MANDA ORDENES " + ("REALES, CON PLATA REAL" if real
                                     else "en el TESTNET (dinero falso)"))
    print("=" * 70)
    print(f"    simbolo   {simbolo}   a {precio:,.2f}")
    print(f"    compra    {qty:g}  =  {qty * precio:,.2f} USDT de nocional")
    print(f"    stop      {stop:,.2f}   (5% abajo: NO se va a disparar)")
    print(f"    objetivo  {objetivo:,.2f}  (10% arriba: NO se va a disparar)")

    if not _confirmar("OPERAR", "  Mando la orden de apertura?"):
        _linea(INFO, "cancelado, no se mando nada")
        return 0

    try:
        r = abrir(simbolo, 1, qty, precio=precio, api_key=clave,
                  secret=secreto, modo=modo, contrato_=c, base=base)
    except BinanceError as exc:
        _linea(MAL, f"la apertura fallo: {exc}")
        _linea(INFO, "No quedo nada abierto. -2019 es margen, -4164 es el "
                     "nocional minimo, -4061 es el modo de posicion.")
        return 1
    # LA RESPUESTA NO TRAE EL PRECIO: medido, `avgPrice` viene en None aunque
    # la orden se haya llenado entera. Se pregunta aparte.
    orden_id = r.get("orderId")
    entrada = float(r.get("avgPrice") or 0.0)
    if not entrada:
        try:
            d = detalle_orden(simbolo, orden_id, api_key=clave, secret=secreto,
                              base=base)
            entrada = d["precio"]
        except BinanceError as exc:
            _linea(OJO, f"no se pudo leer a cuanto entro: {exc}")
    _linea(BIEN, f"orden ejecutada · id {orden_id} · entro "
                 f"{r.get('executedQty')} a {entrada:,.2f}")

    # EN BINANCE PROTEGER ES UNA SEGUNDA LLAMADA, y entre la de arriba y esta
    # la posicion esta abierta y sin stop. Es la ventana que en Bybit no
    # existe, porque alla la proteccion viaja adentro de la entrada.
    try:
        proteger(simbolo, 1, stop=stop, objetivo=objetivo, api_key=clave,
                 secret=secreto, modo=modo, base=base)
        _linea(BIEN, "pedido de stop y objetivo aceptado")
    except BinanceError as exc:
        _linea(MAL, f"NO SE PUDO PROTEGER: {exc}")
        _linea(OJO, "HAY UNA POSICION ABIERTA Y SIN STOP. Se ofrece cerrarla "
                    "abajo; si algo falla, cerrala desde Binance.")

    # SE PREGUNTA EN openAlgoOrders Y NO EN openOrders. Las condicionales se
    # mudaron al Algo Service y el endpoint viejo devuelve una lista VACIA
    # aunque el stop este puesto: preguntar ahi seria una alarma falsa
    # permanente. Medido el 31/8/2026.
    try:
        cond = condicionales_abiertas(simbolo, clave, secreto, base=base)
    except BinanceError as exc:
        cond = []
        _linea(OJO, f"no se pudieron leer las condicionales: {exc}")
    disparos = {o["tipo"]: o["disparo"] for o in cond}
    if "STOP_MARKET" in disparos:
        _linea(BIEN, f"EL STOP QUEDO REGISTRADO EN BINANCE: "
                     f"{disparos['STOP_MARKET']:,.2f}")
        _linea(INFO, "Esto es lo que hace que apagar la aplicacion no "
                     "desproteja la posicion.")
    else:
        _linea(MAL, "LA POSICION ESTA ABIERTA Y SIN STOP REGISTRADO.")
        _linea(OJO, "El pedido puede haberse aceptado igual. No operes hasta "
                    "entender por que la orden no esta.")
    if "TAKE_PROFIT_MARKET" in disparos:
        _linea(BIEN, f"objetivo registrado: {disparos['TAKE_PROFIT_MARKET']:,.2f}")

    p = posicion(simbolo, clave, secreto, base=base)
    _linea(BIEN, f"posicion: {p['cantidad']:g} desde {p['precio_entrada']:,.2f}")

    if not _confirmar("CERRAR", "  Cierro la posicion?"):
        _linea(OJO, "QUEDA UNA POSICION ABIERTA. Cerrala vos desde Binance.")
        return 1
    try:
        cerrar(simbolo, p["lado"] or 1, p["cantidad"] or qty, api_key=clave,
               secret=secreto, modo=modo, contrato_=c, base=base)
    except BinanceError as exc:
        _linea(MAL, f"el cierre fallo: {exc}")
        _linea(OJO, "QUEDA UNA POSICION ABIERTA. Cerrala vos desde Binance.")
        return 1

    # LO QUE IMPORTA NO ES QUE LA ORDEN SE ACEPTE SINO QUE LA POSICION SE HAYA
    # IDO. En BingX la orden de cierre se aceptaba y abria el lado contrario.
    final = posicion(simbolo, clave, secreto, base=base)
    if final["lado"]:
        _linea(MAL, f"SIGUE HABIENDO POSICION: {final['lado']:+d} "
                    f"{final['cantidad']:g}. La orden de cierre no cerro.")
        _linea(OJO, "Si el lado cambio de signo, la orden ABRIO el contrario "
                    "en vez de cerrar: significa que `reduceOnly` no llego.")
        return 1
    _linea(BIEN, "la posicion se cerro: la cuenta quedo plana")

    # DESPUES de cerrar y nunca antes: cancelar con la posicion abierta la
    # dejaria desprotegida.
    try:
        cancelar_todo(simbolo, clave, secreto, base=base)
        quedan = (ordenes_abiertas(simbolo, clave, secreto, base=base)
                  + condicionales_abiertas(simbolo, clave, secreto, base=base))
        _linea(BIEN, "ordenes pendientes canceladas" if not quedan else
                     f"OJO: quedan {len(quedan)} ordenes vivas")
    except BinanceError as exc:
        _linea(OJO, f"no se pudo limpiar las ordenes pendientes: {exc}")
    return 0


def main() -> int:
    real = "--real" in sys.argv
    operar = "--operar" in sys.argv
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

    if operar:
        return _ida_y_vuelta(simbolo, clave, secreto, modo, c, base, real)

    print()
    print("  Lo que esto NO comprobo: mandar una orden. Para probar el camino")
    print("  entero —abrir, que el stop quede puesto, cerrar— en el testnet,")
    print("  donde el dinero es falso y no cuesta nada:")
    print()
    print("      python comprobar_binance.py --operar")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
