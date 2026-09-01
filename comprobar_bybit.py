"""Comprueba la conexión con Bybit, paso a paso, empezando por lo que no arriesga nada.

    python comprobar_bybit.py --real                 # sólo lecturas
    python comprobar_bybit.py --real --operar        # además, una ida y vuelta

LAS CLAVES NO SE ESCRIBEN ACA NI SE PASAN POR LA LINEA DE COMANDOS. Salen de
dos variables de entorno, `BYBIT_API_KEY` y `BYBIT_SECRET`, o del `.env` que ya
está fuera del repositorio. Un secreto escrito en un argumento queda en el
historial de la terminal y en la lista de procesos de la máquina.

QUE CLAVE CREAR: una con permiso de **contratos —Order y Position— y SIN
retiro**. El permiso de retiro no hace falta para nada de esto, y sin él una
clave robada no puede sacar fondos. Si podés, atala a tu IP.

LOS PASOS VAN DE MENOS A MAS RIESGO, y se corta en el primero que falle:

    1. ¿responde Bybit?                        no necesita clave
    2. ¿existe el contrato y cuáles son sus mínimos?    no necesita clave
    3. ¿la clave y la firma son correctas?      lee los permisos, no opera
    4. ¿cuánto hay en la cuenta?                lee, no opera
    5. ¿en qué modo está la cuenta?             decide cómo se cierra
    6. ¿se leen las posiciones?                 lee, no opera

===========================================================================
EL PASO 7 MANDA ORDENES DE VERDAD, CON PLATA DE VERDAD
===========================================================================

Sólo corre con `--operar` Y `--real`, y antes de cada orden hay que escribir
una palabra a mano. No hay forma de que se dispare solo ni por un error de
tipeo en la línea de comandos.

Es la ida y vuelta más chica que el exchange acepta: abre por el nocional
mínimo del símbolo —5 USDT en la mayoría—, comprueba que el stop haya quedado
REGISTRADO EN BYBIT, y cierra. Lo que cuesta es la comisión de las dos puntas
más el spread; en un símbolo líquido son centavos.

El stop y el objetivo se ponen LEJOS a propósito (5% y 10%): la prueba es que
queden anotados del lado del exchange, no que se disparen.

SE ELIGE EL SIMBOLO MAS BARATO, no BTC. En BTCUSDT la orden más chica son 78
USDT de nocional; en XRP o DOGE son 5. Para comprobar que el camino funciona da
exactamente lo mismo, y expone quince veces menos.
"""

from __future__ import annotations

import os
import pathlib
import sys
from decimal import ROUND_UP, Decimal

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from botiquant.data.bybit_trade import (BASE_PRUEBA, BASE_REAL,  # noqa: E402
                                        BybitError, _pedir, abrir, cerrar,
                                        contrato, cuenta_minima, detalle_orden,
                                        modo_posicion, permisos, ping,
                                        posicion, saldo)

BIEN, MAL, INFO, OJO = "  [ok]", "  [x] ", "  ->  ", "  !!  "

#: El más barato de los líquidos: nocional mínimo 5 USDT. Ver el encabezado.
SIMBOLO = "XRPUSDT"


def _linea(marca: str, texto: str) -> None:
    print(f"{marca} {texto}", flush=True)


def _clave() -> tuple[str, str]:
    """De las variables de entorno o del .env. Nunca de un argumento."""
    try:
        from dotenv import load_dotenv
        load_dotenv(pathlib.Path(__file__).with_name(".env"))
    except ImportError:
        pass
    return (os.environ.get("BYBIT_API_KEY", "").strip(),
            os.environ.get("BYBIT_SECRET", "").strip())


def _precio(simbolo: str, base: str) -> float:
    d = _pedir("/v5/market/tickers", {"category": "linear", "symbol": simbolo},
               base=base)
    return float(d["list"][0]["lastPrice"])


def _cantidad_minima(precio: float, c: dict) -> str:
    """La orden más chica que el exchange acepta, redondeada HACIA ARRIBA.

    Acá se redondea al revés que al operar, y es a propósito: al dimensionar
    por riesgo se redondea hacia abajo para no arriesgar de más, pero acá lo
    que se busca es el mínimo VALIDO, y hacia abajo quedaría justo por debajo y
    la orden se rechazaría.
    """
    paso = Decimal(c["paso_texto"])
    por_cantidad = Decimal(str(c["minimo"]))
    por_nocional = (Decimal(str(c["minimo_nocional"])) / Decimal(str(precio))
                    if c["minimo_nocional"] else Decimal(0))
    n = max(por_cantidad, por_nocional)
    if paso > 0:
        n = (n / paso).to_integral_value(rounding=ROUND_UP) * paso
    return f"{n:.{c['decimales_cantidad']}f}"


def _confirmar(palabra: str, texto: str) -> bool:
    print()
    print(texto)
    try:
        return input(f"  Escribí {palabra} para seguir (cualquier otra cosa "
                     f"cancela): ").strip() == palabra
    except EOFError:
        print("  (sin terminal interactiva: cancelado)")
        return False


def _ida_y_vuelta(simbolo: str, clave: str, secreto: str, modo: str,
                  c: dict, base: str) -> int:
    """El único paso que manda órdenes. Ver el encabezado del archivo."""
    precio = _precio(simbolo, base)
    qty = _cantidad_minima(precio, c)
    nocional = float(qty) * precio
    stop = precio * 0.95
    objetivo = precio * 1.10

    print()
    print("=" * 70)
    print("  ESTO MANDA UNA ORDEN REAL, CON PLATA REAL")
    print("=" * 70)
    print(f"    símbolo   {simbolo}   a {precio:,.4f}")
    print(f"    compra    {qty}  ≈  {nocional:,.2f} USDT de nocional")
    print(f"    stop      {stop:,.4f}   (5% abajo: NO se va a disparar)")
    print(f"    objetivo  {objetivo:,.4f}  (10% arriba: NO se va a disparar)")
    print(f"    costo     la comisión de las dos puntas más el spread")
    print()
    print("    Después de abrir se comprueba que el stop haya quedado")
    print("    registrado en Bybit, y recién ahí se ofrece cerrar.")

    if not _confirmar("OPERAR", "  ¿Mando la orden de apertura?"):
        _linea(INFO, "cancelado, no se mandó nada")
        return 0

    # --- abrir ---------------------------------------------------------
    try:
        r = abrir(simbolo, 1, float(qty), stop=stop, objetivo=objetivo,
                  precio=precio, api_key=clave, secret=secreto, modo=modo,
                  contrato_=c, base=base)
    except BybitError as exc:
        _linea(MAL, f"la apertura falló: {exc}")
        _linea(INFO, "No quedó nada abierto. El código del error dice dónde "
                     "mirar: 110007 es saldo, 110017 es el modo de posición, "
                     "10004 es la firma.")
        return 1
    order_id = str(r.get("orderId") or "")
    _linea(BIEN, f"orden aceptada · id {order_id}")

    # --- a cuánto entró ------------------------------------------------
    try:
        d = detalle_orden(simbolo, order_id, api_key=clave, secret=secreto,
                          base=base)
        _linea(BIEN, f"entró {d['cantidad']:g} a {d['precio']:,.4f} · "
                     f"comisión {d['comision']:,.4f} USDT")
    except BybitError as exc:
        _linea(OJO, f"no se pudo leer el detalle de la orden: {exc}")

    # --- ¿quedó protegida? ---------------------------------------------
    try:
        p = posicion(simbolo, clave, secreto, base=base)
    except BybitError as exc:
        _linea(MAL, f"no se pudo leer la posición: {exc}")
        _linea(OJO, "HAY UNA POSICION ABIERTA Y NO SE PUDO CONFIRMAR. "
                    "Miralo en la aplicación de Bybit antes de seguir.")
        return 1

    if not p["lado"]:
        _linea(MAL, "la orden fue aceptada pero no hay posición abierta")
        return 1
    _linea(BIEN, f"posición abierta: {p['cantidad']:g} desde {p['precio_entrada']:,.4f}")

    if p["stop"] > 0:
        _linea(BIEN, f"EL STOP QUEDO PUESTO EN BYBIT: {p['stop']:,.4f}")
        _linea(INFO, "Esto es lo que hace que apagar la aplicación no "
                     "desproteja la posición.")
    else:
        _linea(MAL, "LA POSICION ESTA ABIERTA Y SIN STOP REGISTRADO.")
        _linea(OJO, "La orden se aceptó igual, así que el parámetro del stop "
                    "no está llegando. Cerrá y no operes hasta arreglarlo.")
    if p["objetivo"] > 0:
        _linea(BIEN, f"objetivo puesto: {p['objetivo']:,.4f}")

    # --- cerrar --------------------------------------------------------
    if not _confirmar("CERRAR", "  ¿Cierro la posición?"):
        _linea(OJO, "QUEDA UNA POSICION ABIERTA. Cerrala vos desde Bybit.")
        return 1
    try:
        r = cerrar(simbolo, p["lado"], p["cantidad"], api_key=clave,
                   secret=secreto, modo=modo, contrato_=c, base=base)
    except BybitError as exc:
        _linea(MAL, f"el cierre falló: {exc}")
        _linea(OJO, "QUEDA UNA POSICION ABIERTA. Cerrala vos desde Bybit.")
        return 1
    _linea(BIEN, f"orden de cierre aceptada · id {r.get('orderId')}")

    # LO QUE IMPORTA NO ES QUE LA ORDEN SE ACEPTE SINO QUE LA POSICION SE HAYA
    # IDO. En BingX la orden de cierre se aceptaba y abría el lado contrario.
    final = posicion(simbolo, clave, secreto, base=base)
    if final["lado"]:
        _linea(MAL, f"SIGUE HABIENDO POSICION: {final['lado']:+d} "
                    f"{final['cantidad']:g}. La orden de cierre no cerró.")
        _linea(OJO, "Si el lado cambió de signo, la orden ABRIO el contrario "
                    "en vez de cerrar: es el error de BingX y significa que "
                    "`reduceOnly` no está llegando.")
        return 1
    _linea(BIEN, "la posición se cerró: la cuenta quedó plana")
    return 0


def main() -> int:
    real = "--real" in sys.argv
    operar = "--operar" in sys.argv
    base = BASE_REAL if real else BASE_PRUEBA
    simbolo = SIMBOLO
    for a in sys.argv[1:]:
        if a.startswith("--simbolo="):
            simbolo = a.split("=", 1)[1].upper()

    print()
    print(f"Comprobando Bybit · {'CUENTA REAL' if real else 'DEMO (dinero falso)'}")
    print(f"  {base}")
    if operar and not real:
        print("  --operar sin --real no hace nada: en demo no hay qué arriesgar.")
    print()

    # 1 -----------------------------------------------------------------
    try:
        ping(base)
        _linea(BIEN, "Bybit responde")
    except BybitError as exc:
        _linea(MAL, f"no responde: {exc}")
        _linea(INFO, "Es un problema de red o de la URL, no de la clave.")
        return 1

    # 2 -----------------------------------------------------------------
    try:
        c = contrato(simbolo, base)
    except BybitError as exc:
        _linea(MAL, str(exc))
        return 1
    _linea(BIEN, f"{simbolo}: mínimo {c['minimo']:g} · paso {c['paso']:g} · "
                 f"{c['decimales_cantidad']} decimales · "
                 f"nocional mínimo {c['minimo_nocional']:g} USDT · "
                 f"tick {c['tick']:g}")

    try:
        precio = _precio(simbolo, base)
        orden_min = max(c["minimo"] * precio, c["minimo_nocional"])
        _linea(INFO, f"a {precio:,.4f}, la orden más chica son "
                     f"{orden_min:,.2f} USDT de nocional "
                     f"({_cantidad_minima(precio, c)} {c['simbolo']})")
    except Exception:                                          # noqa: BLE001
        precio = 0.0

    clave, secreto = _clave()
    if not clave or not secreto:
        _linea(INFO, "Sin clave no se puede seguir. Poné BYBIT_API_KEY y "
                     "BYBIT_SECRET en el .env y volvé a correr esto.")
        return 0

    # 3 -----------------------------------------------------------------
    try:
        perm = permisos(clave, secreto, base=base)
    except BybitError as exc:
        _linea(MAL, f"la clave o la firma no pasan: {exc}")
        codigo = getattr(exc, "codigo", None)
        if codigo == 10003:
            _linea(INFO, "10003 es clave inválida. Comprobá que sea del MISMO "
                         "entorno: una de demo no sirve en la real ni al revés.")
        elif codigo == 10004:
            _linea(INFO, "10004 es la firma: el texto firmado no coincide con "
                         "el que llegó.")
        elif codigo == 10002:
            _linea(INFO, "10002 es el reloj de tu máquina. Bybit acepta hasta "
                         "un segundo ADELANTADO por más que se agrande la "
                         "ventana: lo que hay que arreglar es la hora.")
        return 1
    _linea(BIEN, f"clave y firma correctas · {perm['nota'] or 'sin nota'}")
    if perm["vence"]:
        _linea(INFO, f"la clave vence el {perm['vence']}")
    if not perm["puede_operar"]:
        _linea(OJO, "ESTA CLAVE ES DE SOLO LECTURA. Lee todo pero no puede "
                    "mandar órdenes: el paso 7 va a fallar. Creá otra con "
                    "permiso de contratos —Order y Position— y sin retiro.")
    if perm["ips"] == ["*"]:
        _linea(INFO, "la clave no está atada a ninguna IP; si podés, atala.")

    # 4 -----------------------------------------------------------------
    try:
        disponible = saldo(clave, secreto, base=base)
    except BybitError as exc:
        _linea(MAL, f"no se pudo leer el saldo: {exc}")
        return 1
    _linea(BIEN, f"en la cuenta: {disponible:,.4f} USDT")

    # 5 -----------------------------------------------------------------
    try:
        modo = modo_posicion(clave, secreto, simbolo=simbolo, base=base)
    except BybitError as exc:
        _linea(MAL, f"no se pudo leer el modo de posición: {exc}")
        return 1
    _linea(BIEN, f"modo de posición: {modo}")
    _linea(INFO, "Decide el positionIdx de cada orden: 0 en una vía, 1 y 2 en "
                 "cobertura. El equivocado toca la posición del otro lado.")

    # 6 -----------------------------------------------------------------
    try:
        p = posicion(simbolo, clave, secreto, base=base)
    except BybitError as exc:
        _linea(MAL, f"no se pudieron leer las posiciones: {exc}")
        return 1
    _linea(BIEN, "posición abierta: " + (
        f"{'largo' if p['lado'] > 0 else 'corto'} {p['cantidad']:g} "
        f"desde {p['precio_entrada']:,.4f}" if p["lado"] else "ninguna"))

    # cuánta cuenta hace falta para operar POR RIESGO, que es otra cosa que
    # poder mandar la orden mínima
    if precio:
        falta = cuenta_minima(precio, c, stop_pct=2.0, riesgo_pct=1.0)
        print()
        _linea(INFO, f"Con stop del 2% y riesgo del 1%, para que el bot pueda "
                     f"dimensionar en {simbolo} hace falta una cuenta de "
                     f"{falta:,.0f} USDT. En un portafolio eso es POR "
                     f"estrategia, porque cada una maneja su porción.")
        if 0 < disponible < falta:
            _linea(OJO, f"con {disponible:,.2f} USDT el bot no va a poder abrir "
                        f"en {simbolo}: el tamaño que sale del riesgo pedido "
                        f"queda debajo del mínimo. Sí podés mandar la orden "
                        f"mínima a mano, que es lo que hace el paso 7.")

    # 7 -----------------------------------------------------------------
    if not (operar and real):
        print()
        print("  Lo que esto NO comprobó: mandar una orden. Para probar el")
        print("  camino entero —abrir, que el stop quede puesto, cerrar—:")
        print()
        print("      python comprobar_bybit.py --real --operar")
        print()
        print("  Manda órdenes de verdad por el nocional mínimo, y pide")
        print("  confirmación escrita antes de cada una.")
        print()
        return 0

    return _ida_y_vuelta(simbolo, clave, secreto, modo, c, base)


if __name__ == "__main__":
    raise SystemExit(main())
