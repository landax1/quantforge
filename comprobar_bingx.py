"""Comprueba la conexión con BingX, paso a paso, empezando por lo que no arriesga nada.

    python comprobar_bingx.py

LAS CLAVES NO SE ESCRIBEN ACÁ NI SE PASAN POR LA LÍNEA DE COMANDOS. Salen de
dos variables de entorno, `BINGX_API_KEY` y `BINGX_SECRET`, o del `.env` que ya
está fuera del repositorio. Un secreto escrito en un argumento queda en el
historial de la terminal y en la lista de procesos de la máquina.

APUNTA AL ENTORNO DE PRÁCTICA (VST) Y NO AL REAL. Para tocar el real hay que
pasar `--real` a propósito. Ningún error de configuración puede terminar
operando con plata de verdad por omisión.

QUÉ CLAVE CREAR. En BingX, una clave con permiso de **lectura y trading, SIN
retiro**. Aunque se la roben no pueden sacar fondos. Esta comprobación no
necesita el permiso de trading salvo que se le pase `--orden`.

LOS PASOS VAN DE MENOS A MÁS RIESGO, y se corta en el primero que falle:

    1. ¿responde BingX?                      no necesita clave
    2. ¿existe el contrato y cuáles son sus mínimos?   no necesita clave
    3. ¿llegan las velas?                     no necesita clave
    4. ¿la clave y la firma son correctas?    lee el saldo, no opera
    5. ¿se leen las posiciones?               lee, no opera
    6. una orden mínima, ida y vuelta         SÓLO con --orden

El paso 6 es el único que mueve algo, y está apagado por defecto. Es también el
único que no pude verificar yo: BingX valida la clave ANTES que los parámetros
—comprobado mandando pedidos con credenciales falsas, siempre contesta 100413—
así que la forma exacta del pedido no se puede confirmar sin una clave. Si algo
falla, va a fallar ahí, y el mensaje del exchange dice qué corregir.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

# el .env vive fuera del repositorio; si no está, no pasa nada
try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).with_name(".env"))
except Exception:                                             # noqa: BLE001
    pass

from botiquant.data import bingx
from botiquant.vivo.adaptador import BASE_PRACTICA, BASE_REAL, BingX

OK, MAL, INFO = "  OK  ", " MAL  ", "      "


def _linea(estado: str, texto: str) -> None:
    print(f"[{estado}] {texto}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--simbolo", default="BTC-USDT")
    p.add_argument("--real", action="store_true",
                   help="apunta al entorno REAL en vez del de práctica")
    p.add_argument("--orden", action="store_true",
                   help="manda una orden mínima y la cierra (paso 6)")
    args = p.parse_args()

    base = BASE_REAL if args.real else BASE_PRACTICA
    entorno = "REAL — con plata de verdad" if args.real else "PRÁCTICA (VST)"
    print(f"\nEntorno: {entorno}\n{base}\n")

    bingx.BASE = base

    # ---------------------------------------------------------- 1, 2 y 3
    try:
        c = bingx.contrato(args.simbolo)
        _linea(OK, f"BingX responde y conoce {args.simbolo}")
        _linea(INFO, f"mínimo {c.get('tradeMinQuantity')} · "
                     f"{c.get('quantityPrecision')} decimales · "
                     f"taker {float(c.get('takerFeeRate', 0))*100:.3f}% · "
                     f"maker {float(c.get('makerFeeRate', 0))*100:.3f}%")
    except Exception as exc:                                  # noqa: BLE001
        _linea(MAL, f"no se pudo consultar el contrato: {exc}")
        return 1

    try:
        velas = bingx.velas(args.simbolo, "1h", 5)
        _linea(OK, f"llegan las velas — última {velas.index[-1]} "
                   f"cierre {velas['close'].iloc[-1]:,.1f}")
    except Exception as exc:                                  # noqa: BLE001
        _linea(MAL, f"no llegaron las velas: {exc}")
        return 1

    # ------------------------------------------------------------ la clave
    api_key = os.getenv("BINGX_API_KEY", "").strip()
    secret = os.getenv("BINGX_SECRET", "").strip()
    if not api_key or not secret:
        print()
        _linea(INFO, "Sin credenciales: hasta acá llega la comprobación.")
        _linea(INFO, "Todo lo de arriba anda sin clave, así que el problema "
                     "—si hay— no es de red ni de símbolo.")
        print("\nPara seguir, poné en el .env (que no se versiona):")
        print("    BINGX_API_KEY=...")
        print("    BINGX_SECRET=...")
        print("\nCreá la clave con permiso de lectura y trading, SIN RETIRO.\n")
        return 0

    ex = BingX(api_key, secret, base=base)

    try:
        s = ex.capital()
        _linea(OK, f"la clave y la firma funcionan — disponible {s:,.2f}")
    except Exception as exc:                                  # noqa: BLE001
        _linea(MAL, f"la clave o la firma no pasan: {exc}")
        _linea(INFO, "100413 es clave incorrecta; 100001 es firma incorrecta.")
        _linea(INFO, "Ojo: una clave del entorno real no sirve en el de "
                     "práctica, y al revés tampoco.")
        return 1

    try:
        pos = ex.posicion(args.simbolo)
        _linea(OK, f"posiciones leídas — {'abierta: ' + str(pos.cantidad) + ' ' + ('largo' if pos.lado > 0 else 'corto') if pos.abierta else 'ninguna abierta'}")
    except Exception as exc:                                  # noqa: BLE001
        _linea(MAL, f"no se pudieron leer las posiciones: {exc}")
        return 1

    # ------------------------------------------------------------- la orden
    if not args.orden:
        print()
        _linea(INFO, "Todo lo que se puede comprobar sin operar, anda.")
        _linea(INFO, "Para probar el envío de una orden mínima y su cierre:")
        print(f"\n    python comprobar_bingx.py --orden\n")
        return 0

    if args.real:
        print("\nEsto mandaría una orden con PLATA DE VERDAD.")
        print("No lo hago automáticamente. Probalo primero en práctica, "
              "sin --real.\n")
        return 1

    minimo = float(c.get("tradeMinQuantity") or 0.0)

    # CON STOP Y OBJETIVO PUESTOS, y no una orden pelada. Es la parte más
    # delicada del formato —viajan como JSON adentro de un parámetro, y el
    # precio tiene que ser un NÚMERO y no un texto— así que probar sin ellos
    # deja sin verificar justo lo que más chance tiene de estar mal.
    #
    # Los niveles van lejísimos a propósito: 30% abajo y 50% arriba. No se
    # tocan mientras dura la prueba, y la posición se cierra a los dos
    # segundos igual.
    marca = float(bingx.funding_actual(args.simbolo)["precio_marca"])
    stop = round(marca * 0.70, 1)
    objetivo = round(marca * 1.50, 1)

    print(f"\nPaso 6 — una orden de {minimo} {args.simbolo} en PRÁCTICA, "
          f"con stop en {stop:,.1f} y objetivo en {objetivo:,.1f}, "
          f"y su cierre inmediato.")
    try:
        r = ex.abrir(args.simbolo, 1, minimo, stop, objetivo)
        _linea(OK, f"orden aceptada: {r}")
    except Exception as exc:                                  # noqa: BLE001
        _linea(MAL, f"la orden fue rechazada: {exc}")
        _linea(INFO, "Es el paso que no pude verificar sin una clave. El "
                     "mensaje de arriba dice qué parámetro corregir, y se "
                     "corrige en botiquant/vivo/adaptador.py, método abrir().")
        return 1

    try:
        pos = ex.posicion(args.simbolo)
        r = ex.cerrar(args.simbolo, pos)
        _linea(OK, f"posición cerrada: {r}")
    except Exception as exc:                                  # noqa: BLE001
        _linea(MAL, f"NO SE PUDO CERRAR: {exc}")
        _linea(INFO, "Cerrala a mano desde BingX. Es práctica, así que no hay "
                     "plata en juego, pero conviene dejarlo limpio.")
        return 1

    print("\nEl camino entero funciona: datos, clave, firma, orden y cierre.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
