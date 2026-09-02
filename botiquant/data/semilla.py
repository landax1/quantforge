"""Datos que vienen con la aplicación, para que no arranque vacía.

Una aplicación de backtesting que abre sin un solo instrumento no se puede
probar: hay que descargar gigas antes de ver si sirve. Y descargar quince años
de velas de un minuto son miles de pedidos a Dukascopy, varios minutos y un
límite de tasa esperando.

Así que vienen incluidos los cuatro instrumentos en velas de una hora, que es
el timeframe en el que la aplicación mina por defecto. La cuenta cierra:

    los cuatro en M1   1629 MB   imposible de incluir
    los cuatro en H1     28 MB   entra sin despeinarse

Quien necesite timeframes más finos que una hora baja el M1 desde la sección
Datos. Pero eso pasa a ser una decisión y no un peaje de entrada.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from botiquant.rutas import raiz_recursos

CARPETA = "semilla"
MANIFIESTO = "manifiesto.json"


def disponible() -> list[dict[str, Any]]:
    """Qué trae el paquete. Lista vacía si no se incluyó nada."""
    ruta = raiz_recursos() / CARPETA / MANIFIESTO
    if not ruta.is_file():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return datos if isinstance(datos, list) else []


def mundo_de_fuente(source: str | None) -> str | None:
    """A qué sección pertenece un histórico, por su origen.

    Los perpetuos vienen de Binance; lo demás —Dukascopy, MetaTrader, la
    propia semilla— es CFD. Un CSV subido o importado no es de ninguna: no se
    le adivina el mundo, y por eso tampoco cuenta como "ya hay datos" de uno.
    """
    f = str(source or "").strip().lower()
    if f == "binance":
        return "exchange"
    if f in ("upload", "import", "sample", ""):
        return None
    return "metatrader"


def sembrar(store, existentes: list[dict[str, Any]], progreso=None) -> int:
    """Carga los instrumentos incluidos de cada sección que esté vacía.

    Se decide POR SECCIÓN y no por workspace. Antes bastaba con que hubiera
    un instrumento para no sembrar nada, y quien venía de una versión con
    sólo CFDs abría "Cripto" sin un solo perpetuo: el selector volvía a
    SP500 y la sección parecía no hacer nada (pasó el 2 de septiembre).

    Dentro de una sección con datos no se siembra: si corriera siempre,
    volvería a meter los instrumentos que el usuario borró a propósito, y
    duplicaría los que ya bajó en M1 dejándole dos entradas del mismo mercado
    sin saber cuál está usando.

    `BQ_SIN_SEMILLA` lo apaga. Lo usan los tests: casi todos parten de un
    workspace vacío y comprueban qué pasa al agregar el primer instrumento, así
    que arrancar con instrumentos puestos les cambia el punto de partida.
    """
    if os.environ.get("BQ_SIN_SEMILLA", "").strip() not in ("", "0", "false"):
        return 0
    ocupados = {mundo_de_fuente(d.get("source")) for d in existentes or []}
    ocupados.discard(None)

    entradas = disponible()
    if not entradas:
        return 0

    base = raiz_recursos() / CARPETA
    puestos = 0
    for i, e in enumerate(entradas):
        if mundo_de_fuente(e.get("source") or "semilla") in ocupados:
            continue
        origen = base / str(e.get("archivo", ""))
        if not origen.is_file():
            continue
        try:
            df = pd.read_csv(origen, index_col="time", parse_dates=["time"])
        except (ValueError, OSError):
            # Un archivo roto no puede impedir que la aplicación abra: se
            # saltea y el usuario siempre puede descargar el instrumento.
            continue
        if df.empty:
            continue
        puesto = store.add(str(e.get("nombre") or origen.stem), df,
                           source=str(e.get("source") or "semilla"))
        # EL FUNDING VIAJA CON EL PERPETUO. Sin esto, un instrumento sembrado
        # minaria sin costo de funding —numeros mejores que los reales— y los
        # bloques de funding quedarian descartados con aviso. El CFD no trae
        # este campo y no entra aca.
        f_archivo = str(e.get("funding") or "")
        if f_archivo:
            try:
                tasas = pd.read_csv(base / f_archivo, index_col="time",
                                    parse_dates=["time"])["funding"]
                store.guardar_funding(str((puesto or {}).get("id") or ""), tasas)
            except (ValueError, OSError, KeyError):
                # Un funding roto no puede impedir sembrar las velas: la
                # aplicacion abre igual y el aviso de "sin funding" lo dice.
                pass
        puestos += 1
        if progreso:
            progreso((i + 1) / len(entradas), str(e.get("nombre", "")))
    return puestos
