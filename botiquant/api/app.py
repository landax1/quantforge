"""FastAPI application: JSON API + static UI, all local, all offline.

Fast operations (single backtest, Monte Carlo, portfolio) run synchronously;
search operations (generate / evolve / optimize / walk-forward) run as
background jobs polled via ``/api/jobs/{id}``.
"""

from __future__ import annotations

import dataclasses
import hmac
import html as html_lib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response,
)
from fastapi.staticfiles import StaticFiles

from botiquant import __version__
from botiquant.auth import SessionError, clear_cookie, read_cookie, set_cookie, sign, verify
from botiquant.auth.google import (
    GoogleConfig, authorize_url, exchange_code, fetch_profile, new_state,
)
from botiquant.analysis.montecarlo import monte_carlo
from botiquant.analysis.walkforward import walk_forward
from botiquant.backtesting.engine import run_backtest
from botiquant.backtesting.metrics import SCORE_PARTS, bq_score, score_breakdown
from botiquant.core import sesiones
from botiquant.core.jobs import DemasiadoTrabajo, JobManager
from botiquant.core.models import (
    OPERATORS, PRICE_FIELDS, BacktestSettings, RiskConfig, StrategySpec, TimeFilter,
)
from botiquant.data.catalog import (BY_KEY, CATALOG, MINIMOS_PERPETUO,
                                    default_stop_points,
                                    simbolo_fuente)
from botiquant.data.catalog import download as catalog_download
from botiquant.data.loader import parse_ohlcv_csv
from botiquant.data.sample import generate_sample
from botiquant.data.semilla import sembrar
from botiquant.data.store import DataStore
from botiquant.database.db import Database
from botiquant.licencia import firmar
from botiquant.licencia import local as licencia_en_disco
from botiquant.generator.generator import generate_strategies
from botiquant.generator.templates import template_catalog
from botiquant.genetic.evolution import evolve
from botiquant.mining.miner import mine
from botiquant.indicators import indicator_catalog
from botiquant.optimizer.optimizer import discover_dimensions, optimize
from botiquant.portfolio.portfolio import build_portfolio
from botiquant.reports.mql5 import export_mql5
from botiquant.reports.bingx import export_bingx
from botiquant.reports.pine import export_pine
from botiquant.reports.report import excel_report, html_report, metrics_csv, trades_csv
from botiquant.data.catalog import mundo_de_entrada, mundo_de_nombre
from botiquant.metatrader import experts_de, terminales
from botiquant.rutas import (
    carpeta_de_estrategias, carpeta_de_trabajo, raiz_recursos,
)

#: Los recursos vienen con el programa; el workspace es del usuario y tiene que
#: sobrevivir a cerrar la aplicación. Empaquetados son carpetas distintas —ver
#: botiquant/rutas.py—, y confundirlas borraba la base en cada cierre.
ROOT = raiz_recursos()
UI_DIR = ROOT / "ui"
LANDING_DIR = ROOT / "landing"
WORK_DIR = carpeta_de_trabajo()

#: En una máquina propia el usuario ya puede leer sus archivos, así que la
#: importación por ruta es una comodidad. Servido a terceros, ese mismo
#: endpoint lee cualquier archivo del servidor: se apaga con BQ_MULTIUSER=1.
MULTIUSER = os.environ.get("BQ_MULTIUSER", "").strip() not in ("", "0", "false")

#: Prefijo interno de nginx para entregar el instalador sin pasar por Python.
#:
#: El ZIP son cincuenta megas. Servirlo desde acá ata el proceso a esa conexión
#: mientras dura la bajada, y el servicio corre con UN worker a propósito —el
#: estado de los logins de Google vive en memoria del proceso, con dos falla
#: uno de cada dos—. O sea que las descargas compiten con los logins.
#:
#: Con esto, Python decide si tenés cuenta y contesta con una cabecera; nginx
#: lee esa cabecera y manda el archivo él. El control queda donde tiene que
#: estar y el trabajo pesado donde corresponde.
#:
#: Vacío fuera del servidor: en el escritorio y en desarrollo no hay ningún
#: nginx que interprete la cabecera, y la respuesta llegaría vacía.
XACCEL = os.environ.get("BQ_XACCEL", "").strip()

#: Dónde queda el instalador que produce el empaquetado. No está en el
#: repositorio: son cientos de megabytes que no tienen por qué versionarse. Vive
#: junto al proyecto y no dentro de él, por la misma razón.
#:
#: A nivel de módulo y no adentro de la función que arma la aplicación porque
#: es una constante, y porque ahí adentro no había forma de probar la entrega
#: del archivo sin levantar el servidor entero.
BUILD_DIR = Path(__file__).resolve().parent.parent.parent / "dist"

#: Un ZIP y no un instalador todavía. Se descomprime y se ejecuta; cuando haya
#: un instalador de verdad cambia sólo este nombre.
INSTALADOR = "Botiquant-Windows.zip"

#: El servidor público sirve portada, cuentas, licencias y descarga. Nada más.
#:
#: Sin esto, el mismo proceso sigue exponiendo /app y los endpoints de cálculo:
#: cualquiera con cuenta entra a botiquant.com/app y mina EN EL SERVIDOR, que es
#: exactamente lo que el modelo de escritorio existe para evitar. No es una
#: cuestión de orden — es la diferencia entre un VPS de cinco dólares y una
#: factura que crece con cada usuario.
SOLO_WEB = os.environ.get("BQ_SOLO_WEB", "").strip() not in ("", "0", "false")

#: Lo que deja de existir cuando el servidor es sólo la web. Se comparan por
#: prefijo porque varios llevan parámetros en la ruta.
CALCULO = (
    "/api/mine", "/api/backtest", "/api/generate", "/api/evolve",
    "/api/optimize", "/api/walkforward", "/api/montecarlo", "/api/portfolio",
    "/api/jobs", "/api/export", "/api/validar", "/api/robustez",
    # el banco es la salida del minado: si el servidor público lo sirviera,
    # bastaría con minar una vez para que la web quedara de repositorio
    "/api/banco", "/api/corridas", "/api/probar",
)


#: Los mensajes de error del servidor, en ingles.
#:
#: La clave es el texto en espanol tal como se escribe en el `raise`. Los que
#: llevan datos adentro se listan por su comienzo y se traduce solo esa parte:
#: el resto —fechas, rutas, cantidades— son numeros y nombres propios, que
#: no se traducen.
ERRORES_EN: dict[str, str] = {
    # --- rango de fechas y datos
    "La fecha 'desde' tiene que ser anterior a la de 'hasta'":
        "The 'from' date has to come before the 'to' date",
    "dataset_id is required": "dataset_id is required",
    # --- estrategias y validacion
    "No sabemos con qu\u00e9 instrumento se encontr\u00f3.":
        "We do not know which instrument this was found on.",
    "Esa estrategia ya no est\u00e1 en el banco.":
        "That strategy is no longer in the databank.",
    "Esas estrategias ya no est\u00e1n en el banco.":
        "Those strategies are no longer in the databank.",
    "Esa estrategia no existe.": "That strategy does not exist.",
    "El histórico con el que se encontró esta estrategia ya no está: se "
    "borró desde Datos. La estrategia sigue guardada; volvé a bajar ese "
    "instrumento y se puede probar y exportar de nuevo.":
        "The history this strategy was found on is gone: it was deleted from "
        "Data. The strategy is still saved; download that instrument again and "
        "it can be tested and exported.",
    "Hace falta el per\u00edodo sobre el que validar.":
        "A period to validate over is required.",
    "Eleg\u00ed al menos una estrategia.": "Pick at least one strategy.",
    "Falta la estrategia.": "The strategy is missing.",
    # --- trabajos
    "Ese trabajo ya no est\u00e1 corriendo.": "That job is no longer running.",
    "No est\u00e1.": "Not found.",
    # --- cuentas y licencias
    "Entr\u00e1 con tu cuenta para descargar la estrategia.":
        "Sign in to download the strategy.",
    "Entr\u00e1 con tu cuenta para obtener tu licencia.":
        "Sign in to get your licence.",
    "El inicio de sesi\u00f3n no est\u00e1 configurado en este servidor.":
        "Sign-in is not configured on this server.",
    "Este servidor todav\u00eda no tiene configurada la firma de licencias.":
        "This server has no licence signing configured yet.",
    "La aplicaci\u00f3n de escritorio todav\u00eda no est\u00e1 publicada.":
        "The desktop application has not been published yet.",
    # --- archivos
    "Nombre de archivo inv\u00e1lido.": "Invalid file name.",
    "Ruta inv\u00e1lida.": "Invalid path.",
    "S\u00f3lo se abren estrategias exportadas.":
        "Only exported strategies can be opened.",
    "Ese archivo no lo export\u00f3 Botiquant.": "Botiquant did not export that file.",
    "El archivo ya no est\u00e1 ah\u00ed.": "The file is no longer there.",
    "Esa carpeta no es de Botiquant.": "That folder does not belong to Botiquant.",
    "Ese MetaTrader ya no est\u00e1 en esta m\u00e1quina.":
        "That MetaTrader is no longer on this machine.",
    "No disponible.": "Not available.",
    "Formato desconocido.": "Unknown format.",
    # --- instrumentos
    "Este instrumento es compartido y no se puede borrar. ":
        "This instrument is shared and cannot be deleted. ",
}

#: Los que llevan datos adentro: se compara el comienzo y se cambia solo eso.
ERRORES_EN_PREFIJO: tuple[tuple[str, str], ...] = (
    ("Fecha inv\u00e1lida:", "Invalid date:"),
    ("No existe el archivo:", "No such file:"),
    ("No se pudo escribir en", "Could not write to"),
    ("No se pudo abrir la carpeta:", "Could not open the folder:"),
    ("No se pudo abrir:", "Could not open:"),
)


def traducir_error(detalle: str, idioma: str) -> str:
    """El mismo mensaje en el idioma pedido, o tal cual si no esta en la tabla.

    Nunca falla ni oculta el original: un mensaje sin traduccion se ve en
    espanol, que es peor que en ingles pero infinitamente mejor que un error
    generico o que ninguno.
    """
    if idioma != "en" or not detalle:
        return detalle
    exacto = ERRORES_EN.get(detalle)
    if exacto:
        return exacto
    for es, en in ERRORES_EN_PREFIJO:
        if detalle.startswith(es):
            return en + detalle[len(es):]
    return detalle


#: Por que una licencia no sirve, en las palabras del usuario y no en las de
#: la biblioteca. "la firma no corresponde" es cierto y no le dice nada a nadie.
_POR_QUE_NO_SIRVE = {
    "vencida": "Esa licencia venció. Entrá a tu cuenta en botiquant.com y bajate la nueva.",
    "invalida": "Ese texto no es una licencia de Botiquant. Copialo de nuevo desde tu cuenta, entero.",
    "sin_licencia": "No pegaste nada.",
}


def _epoch_de(valor: Any) -> int:
    """La fecha de alta de la base, en segundos.

    La columna `created` viene como texto ISO en unas filas y como numero en
    otras segun quien la escribio. Devolver 0 ante algo que no se entiende es
    preferible a romper la emision de la licencia por una fecha rara: el alta
    es un dato lindo de mostrar, no un requisito.
    """
    if isinstance(valor, (int, float)):
        return int(valor)
    if isinstance(valor, str) and valor.strip():
        try:
            return int(datetime.fromisoformat(
                valor.strip().replace("Z", "+00:00")).timestamp())
        except ValueError:
            return 0
    return 0


def _entero(nombre: str) -> int | None:
    """Lee un entero del entorno. Devuelve None si no está o no sirve, para que
    quien lo use aplique su propio default en vez de recibir un cero."""
    crudo = os.environ.get(nombre, "").strip()
    if not crudo:
        return None
    try:
        valor = int(crudo)
    except ValueError:
        return None
    return valor if valor > 0 else None


def _base_de_datos(workdir: Path) -> Path:
    """Al renombrar QuantForge → Botiquant cambió el nombre del archivo. Si
    existe el viejo y todavía no el nuevo, se renombra: si no, el usuario
    arrancaría con una base vacía y creería que perdió sus instrumentos y sus
    estrategias guardadas.

    Si el rename no se puede hacer —en Windows basta con que otra instancia
    tenga el archivo abierto— se sigue usando el viejo. Una migración de
    conveniencia no puede impedir que la aplicación arranque.
    """
    nueva = workdir / "botiquant.sqlite"
    vieja = workdir / "quantforge.sqlite"
    if nueva.exists() or not vieja.exists():
        return nueva
    try:
        vieja.rename(nueva)
    except OSError:
        return vieja
    return nueva


def create_app(workdir: Path | None = None) -> FastAPI:
    workdir = Path(workdir or WORK_DIR)
    workdir.mkdir(parents=True, exist_ok=True)

    db = Database(_base_de_datos(workdir))
    store = DataStore(workdir / "datasets", db)
    # Primer arranque: se cargan los instrumentos que vienen con el programa.
    # Una aplicación de backtesting que abre sin un solo instrumento no se
    # puede ni probar. Sólo las secciones vacías — ver semilla.sembrar.
    sembrar(store, db.list_datasets(None))
    # Los topes se configuran por entorno porque dependen de la máquina: en un
    # servidor con más núcleos conviene subirlos, y en la propia no hace falta
    # racionar nada. Sin variables, el default deja un núcleo libre para atender
    # pedidos mientras se mina.
    jobs = JobManager(
        max_running=_entero("BQ_MAX_BUSQUEDAS"),
        max_por_usuario=_entero("BQ_MAX_POR_USUARIO") or 1,
    )

    app = FastAPI(title="Botiquant", version=__version__, docs_url="/api/docs")

    #: por debajo de esto no hay con qué: las plantillas usan períodos de hasta
    #: 350 velas, así que un rango corto dejaría los indicadores en NaN
    MIN_BARS = 500

    def _slice_dates(df, payload: dict[str, Any]):
        """Recorta el frame al rango pedido. Sin fechas, devuelve todo.

        Es lo que permite minar sobre un tramo y validar sobre otro: el
        rango viaja en el payload, así que la misma estrategia se puede
        re-evaluar fuera de la muestra sin tocar nada más.
        """
        raw_from, raw_to = payload.get("date_from"), payload.get("date_to")
        if not raw_from and not raw_to:
            return df
        try:
            lo = pd.Timestamp(raw_from) if raw_from else None
            hi = pd.Timestamp(raw_to) if raw_to else None
        except ValueError as exc:
            raise HTTPException(400, f"Fecha inválida: {exc}") from exc
        if lo is not None and hi is not None and lo >= hi:
            raise HTTPException(400, "La fecha 'desde' tiene que ser anterior a la de 'hasta'")
        # una fecha sin hora significa el día entero, no su primer segundo
        if hi is not None and hi == hi.normalize():
            hi = hi + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        # EL RANGO SE ESCRIBE EN EL RELOJ DEL HISTÓRICO. Los perpetuos de
        # Binance vienen con zona horaria (UTC) y los CFD sin ella; una fecha
        # pelada contra un índice con zona reventaba con "Cannot compare
        # tz-naive and tz-aware" —un 500— al minar cualquier cripto con una
        # receta que acorta la ventana. Pasó en la primera búsqueda de un
        # usuario nuevo.
        tz = getattr(df.index, "tz", None)
        if tz is not None:
            lo = lo.tz_localize(tz) if lo is not None and lo.tzinfo is None else lo
            hi = hi.tz_localize(tz) if hi is not None and hi.tzinfo is None else hi
        else:
            lo = lo.tz_localize(None) if lo is not None and lo.tzinfo is not None else lo
            hi = hi.tz_localize(None) if hi is not None and hi.tzinfo is not None else hi
        out = df.loc[lo:hi]
        if len(out) < MIN_BARS:
            span = f"{raw_from or 'inicio'} → {raw_to or 'fin'}"
            raise HTTPException(
                400, f"El rango {span} deja sólo {len(out):,} velas en este timeframe. "
                     f"Hacen falta al menos {MIN_BARS:,} para que los indicadores "
                     f"tengan historia suficiente.")
        return out

    def _load_df(payload: dict[str, Any]):
        ds_id = payload.get("dataset_id")
        if not ds_id:
            raise HTTPException(400, "dataset_id is required")
        try:
            df = store.load(ds_id, payload.get("timeframe") or None)
        except (FileNotFoundError, KeyError) as exc:
            # UNA ESTRATEGIA GUARDADA PUEDE QUEDAR SIN SU HISTORICO, y no es un
            # caso raro: alcanza con borrar el instrumento desde Datos. Pasó
            # probando la aplicación.
            #
            # "Dataset 983be757d3d9 not found on disk" es cierto y no le sirve
            # a nadie: no dice qué pasó, ni que la estrategia sigue guardada, ni
            # qué hacer. El identificador no se puede buscar en ningún lado.
            raise HTTPException(
                404,
                "El histórico con el que se encontró esta estrategia ya no "
                "está: se borró desde Datos. La estrategia sigue guardada; "
                "volvé a bajar ese instrumento y se puede probar y exportar "
                "de nuevo.") from exc
        except ValueError as exc:
            # pedir un timeframe más fino que el del dataset: 400 y no 500,
            # porque es una elección corregible y el texto explica cómo
            raise HTTPException(400, str(exc)) from exc
        df = _slice_dates(df, payload)

        # EL FUNDING TAMBIEN COMO COLUMNA, no sólo como costo.
        #
        # Ya viajaba al motor adentro de `settings` para que la posición
        # abierta lo pague. Pero ahí es un costo, y la biblioteca no lo puede
        # MIRAR: no hay forma de escribir "sólo operá cuando los largos están
        # amontonados" si el dato no está en el dataframe.
        #
        # SE ALINEA HACIA ATRAS Y NUNCA HACIA ADELANTE. Cada vela recibe la
        # tasa del último cobro anterior o igual a ella; la del cobro que
        # todavía no pasó no existe para esa vela. Un `ffill` es exactamente
        # eso, y cualquier otra cosa —interpolar, rellenar hacia atrás— le
        # daría a la búsqueda un dato que en ese momento nadie tenía.
        #
        # Un CFD no tiene archivo de funding y la columna no aparece. Eso es
        # deliberado: `mine` corta con un mensaje si le piden un bloque de
        # funding sobre un histórico que no lo trae, en vez de minar con una
        # condición que nunca es cierta.
        try:
            tasas = store.funding(ds_id)
            if tasas is not None and len(tasas):
                df = df.copy()
                df["funding"] = tasas.reindex(df.index, method="ffill")
        except Exception:                                      # noqa: BLE001
            # Que falte o esté ilegible el archivo de funding NO puede impedir
            # minar por precio, que es lo que hace la mayoría.
            pass
        return df

    def _spec(payload: dict[str, Any]) -> StrategySpec:
        raw = payload.get("spec")
        if not raw:
            raise HTTPException(400, "spec is required")
        return StrategySpec.from_dict(raw)

    def _settings(payload: dict[str, Any]) -> BacktestSettings:
        """Los costos del pedido, más el funding si el instrumento lo tiene.

        La serie NO viaja desde el navegador: la pone el servidor a partir del
        dataset. Son miles de valores que el cliente no tiene motivo de conocer
        —ni de poder falsear— y mandarlos en cada pedido sería absurdo.

        Un CFD no tiene archivo de funding, así que `funding()` devuelve None y
        el motor se comporta exactamente como antes.
        """
        ajustes = BacktestSettings.from_dict(payload.get("settings") or {})
        ds_id = payload.get("dataset_id")
        if ds_id:
            try:
                ajustes.funding = store.funding(ds_id)
            except (OSError, ValueError, KeyError):
                # una serie ilegible no puede tumbar una búsqueda: se mina sin
                # ella, que es exactamente como se minaba antes de que existiera
                ajustes.funding = None
        return ajustes

    def _risk(payload: dict[str, Any]) -> RiskConfig:
        risk = RiskConfig.from_dict(payload.get("risk") or {})
        problem = risk.coherence_error()
        if problem:
            raise HTTPException(400, problem)
        return risk

    # ------------------------------------------------------------------ meta
    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        return {
            "version": __version__,
            "indicators": indicator_catalog(),
            "templates": template_catalog(),
            "operators": list(OPERATORS),
            "price_fields": list(PRICE_FIELDS),
            "timeframes": ["native", "15m", "30m", "1h", "4h", "1d"],
            # las franjas horarias las define el servidor para que la pantalla
            # no pueda ofrecer una que el minero después rechace
            "sessions": sesiones.catalogo(),
            # la UI lo necesita para no ofrecer botones que van a dar 403
            "multiuser": MULTIUSER,
            # el desglose del QF Score se define en un solo lugar
            "score_parts": [{"key": k, "label": l, "weight": w}
                            for k, l, w in SCORE_PARTS],
        }

    # -------------------------------------------------------------- datasets
    def _catalog_entry_for(name: str) -> dict[str, Any] | None:
        low = name.lower()
        for entry in CATALOG:
            if (entry["label"].lower() in low
                    or simbolo_fuente(entry).lower() in low):
                return entry
        return None

    @app.get("/api/datasets")
    def list_datasets(request: Request) -> list[dict[str, Any]]:
        """Datasets plus the exit distances that make sense for each one.

        A stop is an absolute price distance, so the UI cannot carry a single
        default: 40 points is a normal stop on the S&P and unreachable on
        EURUSD. Every dataset ships with its own suggestion so the mining page
        can never propose a stop the market will not travel.
        """
        out = []
        for d in store.list(duenio(request)):
            entry = _catalog_entry_for(d.get("name", ""))
            if entry and entry.get("stop_points"):
                stop, target = entry["stop_points"], entry["target_points"]
            else:
                stop, target = default_stop_points(d.get("last_close") or 0.0)
            out.append({**d, "suggested_stop": stop, "suggested_target": target,
                        "suggested_spread": entry["spread"] if entry else None,
                        "suggested_slippage": entry["slippage"] if entry else None,
                        # LA COMISIÓN, para los instrumentos que cobran así.
                        #
                        # Un CFD cobra en el spread y no manda nada acá; un
                        # perpetuo de exchange cobra en % del nocional y ES todo
                        # su costo de transacción. Sin esto la pantalla heredaba
                        # la comisión en cero del instrumento anterior y se
                        # minaba SIN costo de operar, que es la forma más fácil
                        # de encontrar estrategias que no existen.
                        "suggested_commission": (entry.get("commission_pct")
                                                 if entry else None),
                        # Con qué unidad opera el bróker este instrumento. Sin
                        # esto la pantalla no puede contestar si la posición que
                        # sale del capital y el riesgo es siquiera operable: en
                        # un índice 1 lote son 100 unidades y en divisas 100.000,
                        # así que el mismo número de unidades es un volumen
                        # aceptable o cien veces menos que el mínimo.
                        "contract_size": entry.get("contract_size") if entry else None,
                        "min_lot": entry.get("min_lot") if entry else None,
                        # qué dirección conviene buscar acá: un índice sube solo
                        # y un par de divisas no va a ninguna parte
                        "suggested_direction": (entry.get("direction") if entry
                                                else None) or "both",
                        # como lo puede llamar el broker: hace falta al
                        # exportar, para enganchar el bot al grafico correcto
                        "aliases": (entry.get("aliases") if entry else None) or [],
                        # que rendimiento anual tiene sentido pedirle a ESTE
                        # mercado: el techo del S&P y el de EURUSD no se parecen
                        "min_cagr": entry.get("min_cagr") if entry else None})
        return out

    @app.post("/api/datasets/upload")
    async def upload_dataset(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        try:
            df = parse_ohlcv_csv(content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        name = (file.filename or "upload.csv").rsplit(".", 1)[0]
        return store.add(name, df, source="upload", user_id=duenio(request))

    @app.post("/api/datasets/sample")
    def create_sample(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload.get("symbol", "DEMO"))[:20] or "DEMO"
        bars = int(min(max(int(payload.get("bars", 20_000)), 500), 200_000))
        tf = int(payload.get("timeframe_minutes", 60))
        df = generate_sample(symbol=symbol, bars=bars, timeframe_minutes=tf,
                             start_price=float(payload.get("start_price", 100.0)),
                             start=str(payload.get("start", "2021-01-01")))
        return store.add(f"{symbol} (sample)", df, source="sample", user_id=duenio(request))

    @app.get("/api/catalog")
    def instrument_catalog(request: Request) -> list[dict[str, Any]]:
        """Popular instruments with their broker cost profile."""
        # only real market data counts as "ready" — a synthetic sample named
        # EURUSD must never be mistaken for downloaded history
        owned = [d for d in store.list(duenio(request)) if d["source"] != "sample"]

        # EL EMPAREJAMIENTO MIRA EL PRIMER TOKEN Y NO LA SUBCADENA.
        #
        # Buscar por subcadena parece inofensivo y no lo es: "btcusd" está
        # adentro de "btcusdt", así que el CFD de Bitcoin se quedaba con el
        # dataset del PERPETUO —otro instrumento, otra historia, otros costos—
        # y la pantalla mostraba las velas del perpetuo en la tarjeta del CFD.
        # Apretar «buscar en éste» minaba sobre los datos equivocados sin que
        # fallara nada.
        #
        # Los datasets se llaman "BTCUSD M1 (Dukascopy)" o "BTCUSDT M1": el
        # instrumento es la primera palabra. Se compara ESA, entera.
        def _token(nombre: str) -> str:
            return (nombre.strip().split() or [""])[0].lower()

        # La subcadena sigue existiendo como último recurso, para los CSV que
        # trae el usuario con nombres libres. Pero no puede robarle el dataset
        # a otro instrumento del catálogo: los que son de alguien por nombre
        # exacto quedan reservados.
        reservados = {_token(x["label"]) for x in CATALOG}

        out = []
        for entry in CATALOG:
            names = (entry["label"].lower(), simbolo_fuente(entry).lower())
            have = next((d for d in owned if _token(d["name"]) in names), None)
            if have is None:
                have = next((d for d in owned
                             if _token(d["name"]) not in reservados
                             and any(n in d["name"].lower() for n in names)),
                            None)
            out.append({**entry,
                        "dataset_id": have["id"] if have else None,
                        "rows": have["rows"] if have else 0,
                        # La tarjeta anunciaba "velas M1" siempre, y el número
                        # que mostraba al lado era el del dataset que hay
                        # cargado — que en los que trae el instalador son
                        # horarias. Decía "78.310 velas M1" sobre 78.310 velas
                        # de una hora: no es un detalle de redacción, cambia
                        # qué temporalidades se pueden minar con eso.
                        "timeframe": have["timeframe"] if have else None,
                        "start": have["start"] if have else None,
                        "end": have["end"] if have else None,
                        # DE DONDE SALIO Y EN QUE RELOJ QUEDO.
                        #
                        # Desde que hay dos fuentes, el mismo instrumento puede
                        # tener catorce años o ninguno según de dónde se bajó,
                        # y las velas pueden estar en un reloj o en otro. Sin
                        # decirlo, el usuario no tiene forma de entender por
                        # qué su S&P tiene 62.722 velas de una hora y el de
                        # otro tiene millones de un minuto.
                        "bajado_de": have["source"] if have else None,
                        "utc_offset": have.get("utc_offset") if have else None,
                        # En qué sección vive: CFD (MetaTrader) o cripto
                        # (exchange). No es una preferencia sino una propiedad
                        # del instrumento — determina cómo se paga, dónde se
                        # opera y cómo se exporta. Ver catalog.mundo_de_entrada.
                        "mundo": mundo_de_entrada(entry)})
        return out

    @app.post("/api/datasets/download")
    def download_dataset(payload: dict[str, Any]) -> dict[str, str]:
        """Fetch a catalogue instrument from Dukascopy (needs node + network).

        En modo multiusuario no se expone: los instrumentos del catálogo ya
        vienen cargados y son compartidos. Dejarlo abierto permitiría que
        cualquiera dispare descargas de cientos de MB desde el servidor.
        """
        if MULTIUSER:
            raise HTTPException(
                403, "Los instrumentos del catálogo ya vienen cargados y son "
                     "compartidos. Para usar tus propios datos, subí un CSV.")
        key = str(payload.get("key", ""))
        if key not in BY_KEY:
            raise HTTPException(400, f"Instrumento desconocido: {key}")
        entry = BY_KEY[key]

        def work(progress):
            from botiquant.data.catalog import bajar as bajar_instrumento

            df, origen = bajar_instrumento(key, workdir, progress=progress)
            progress(0.96, "Guardando…")
            fuente = origen["fuente"]

            # EL NOMBRE DICE LA TEMPORALIDAD REAL, y eso no es cosmético: antes
            # todos los datasets se llamaban "M1" porque todos venían de
            # Dukascopy. Un histórico de una hora llamado "M1" hace creer que
            # se puede minar en quince minutos, y la respuesta —correcta— llega
            # recién al intentarlo.
            etiqueta = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
                        "1h": "H1", "4h": "H4", "1d": "D1"}.get(
                            origen.get("timeframe", "1m"), "M1")
            comoSeLlama = {"metatrader": "MetaTrader",
                           "binance": "Binance"}.get(fuente, "Dukascopy")
            ds = store.add(f"{entry['label']} {etiqueta} ({comoSeLlama})", df,
                           source=fuente, utc_offset=origen.get("utc_offset"))

            # EL FUNDING SE BAJA CON LAS VELAS, no después ni aparte.
            #
            # Si no se guardara acá, el instrumento quedaría minable pero sin
            # su costo de mantener la posición, y el motor —que no tiene forma
            # de saber que falta— minaría en silencio con números que no son.
            # Es la peor manera de fallar: resultados que parecen correctos.
            #
            # Un fallo bajando las tasas NO tira abajo la descarga: las velas
            # ya están guardadas y son lo caro. Se avisa y el instrumento queda
            # utilizable, aunque sin funding.
            if fuente == "binance":
                progress(0.97, "Bajando el funding…")
                try:
                    from botiquant.data.binance import funding as bajar_funding
                    tasas = bajar_funding(entry["binance"], entry["from"])
                    store.guardar_funding(ds["id"], tasas)
                    progress(0.99, f"{len(tasas):,} tasas de funding")
                except Exception as exc:                    # noqa: BLE001
                    progress(0.99, f"Sin funding ({exc}); las velas están bien")
            return ds
        return {"job_id": jobs.submit("download", work)}

    @app.post("/api/datasets/import-path")
    def import_dataset_path(payload: dict[str, Any]) -> dict[str, str]:
        """Import a CSV that already lives on this machine (no upload copy).

        The right path for big files: reading 400 MB from disk beats pushing
        it through the browser.

        Only available in single-user mode. Reading an arbitrary server path is
        a comfort when the machine is yours and an arbitrary-file-read hole the
        moment anyone else can reach the API, so a shared deployment must set
        ``BQ_MULTIUSER=1`` and let users upload instead.
        """
        if MULTIUSER:
            raise HTTPException(
                403, "La importación por ruta está deshabilitada en modo multiusuario. "
                     "Subí el archivo con el selector de archivos.")
        raw = str(payload.get("path", "")).strip().strip('"')
        if not raw:
            raise HTTPException(400, "path is required")
        src = Path(raw)
        if not src.is_file():
            raise HTTPException(400, f"No existe el archivo: {src}")
        name = str(payload.get("name") or src.stem)[:80]

        def work(progress):
            progress(0.05, "Leyendo archivo…")
            content = src.read_bytes()
            progress(0.25, "Parseando velas…")
            df = parse_ohlcv_csv(content)
            progress(0.70, f"{len(df):,} velas — guardando en el workspace…")
            meta = store.add(name, df, source="import")
            progress(1.0, "Listo")
            return meta
        return {"job_id": jobs.submit("import", work)}

    #: lo que un usuario puede borrar: sólo lo que él mismo subió. Todo lo
    #: demás es infraestructura compartida — los instrumentos del catálogo
    #: existen una sola vez y los minan todos.
    BORRABLE = {"upload"}

    @app.delete("/api/datasets/{ds_id}")
    def delete_dataset(request: Request, ds_id: str) -> dict[str, str]:
        """Los instrumentos compartidos no se borran.

        Sin esto, un clic en "Borrar" de cualquier usuario deja al resto sin
        el S&P 500 hasta que alguien lo reponga a mano: 4,6 millones de velas
        que hay que volver a descargar de Dukascopy.
        """
        yo = duenio(request)
        try:
            fila = db.get_dataset(ds_id, yo)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        # Con cuentas activas, lo compartido queda con dueño vacío. Se responde
        # 403 y no un "borrado" silencioso: el DELETE no habría tocado nada y el
        # usuario se quedaría esperando que desapareciera de la lista.
        if yo is not None and str(fila.get("user_id") or "") != yo:
            raise HTTPException(
                403, "Este instrumento es compartido y no se puede borrar. "
                     "Sólo podés borrar los CSV que subiste vos.")
        if MULTIUSER and fila.get("source", "") not in BORRABLE:
            raise HTTPException(
                403, "Este instrumento es compartido y no se puede borrar. "
                     "Sólo podés borrar los CSV que subiste vos.")
        store.delete(ds_id, yo)
        return {"status": "deleted"}

    # -------------------------------------------------------------- backtest
    @app.post("/api/backtest")
    def backtest(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        df = _load_df(payload)
        spec = _spec(payload)
        # an explicit risk block overrides whatever the spec carries, so the
        # inspector can re-run a mined strategy under different exit settings
        if payload.get("risk"):
            spec.risk = _risk(payload)
        ajustes = _settings(payload)
        result = run_backtest(df, spec, ajustes).to_dict()
        result["score"] = bq_score(result["metrics"])
        result["score_parts"] = {k: round(v, 3)
                                 for k, v in score_breakdown(result["metrics"]).items()}
        out: dict[str, Any] = {"result": result}
        if payload.get("save"):
            yo = duenio(request)
            ds = db.get_dataset(payload["dataset_id"], yo)
            rid = db.save_result(spec.name, ds["id"], ds["name"], result,
                                 kind="backtest", strategy_id=payload.get("strategy_id"),
                                 user_id=yo)
            out["result_id"] = rid
        return out

    # ------------------------------------------------------------------ auth
    gcfg = GoogleConfig.from_env()
    SECRET = os.environ.get("SESSION_SECRET", "").strip()
    #: en localhost la cookie viaja por http, así que no puede pedir `secure`
    COOKIE_SECURE = gcfg.redirect_uri.startswith("https://")

    def _auth_listo() -> bool:
        return gcfg.enabled and bool(SECRET)

    def usuario_actual(request: Request) -> dict[str, Any] | None:
        """Quién está del otro lado, o None si nadie inició sesión."""
        if not SECRET:
            return None
        try:
            datos = verify(read_cookie(request), SECRET)
            return db.get_user(str(datos.get("uid", "")))
        except (SessionError, KeyError):
            return None

    def _exigir_para_descargar(request: Request) -> dict[str, Any] | None:
        """Sin login configurado —una instalación local— no se le pide cuenta a
        nadie. Con login configurado, hay que estar dentro."""
        if not _auth_listo():
            return None
        u = usuario_actual(request)
        if u is None:
            raise HTTPException(401, "Entrá con tu cuenta para descargar la estrategia.")
        return u

    #: Lo único que se puede tocar sin cuenta. Es una lista de lo PERMITIDO y no
    #: de lo prohibido a propósito: si mañana se agrega un endpoint y nadie se
    #: acuerda de protegerlo, queda cerrado en vez de quedar abierto.
    #: `/api/meta` entra porque la interfaz lo pide antes de saber quién sos, y
    #: no dice nada privado; el resto son las piezas del propio login.
    SIN_CUENTA = {
        "/api/meta",
        "/api/auth/me",
        "/api/auth/google/start",
        "/api/auth/google/callback",
        "/api/auth/logout",
        # la portada lo consulta antes de que nadie inicie sesión, para saber si
        # el botón dice "Descargar" o "Muy pronto". No revela nada privado.
        "/api/descarga",
    }

    def duenio(request: Request) -> str | None:
        """De quién es lo que se está por leer o guardar.

        `None` significa "sin dueños" y es la instalación local: ahí no hay
        cuentas y todo es del que está sentado adelante, así que las consultas
        salen sin filtrar y nada cambia respecto de antes.
        """
        if not _auth_listo():
            return None
        u = usuario_actual(request)
        return str(u["id"]) if u else None

    @app.middleware("http")
    async def exigir_cuenta(request: Request, call_next):
        """La aplicación entera pide cuenta.

        Va como middleware y no como dependencia en cada ruta porque son más de
        treinta: olvidarse de una sola dejaría un agujero, y acá el olvido falla
        del lado seguro.

        Proteger sólo la pantalla no serviría de nada: quien quiera saltearse el
        registro no abre el navegador, llama a la API directamente. Por eso el
        candado está en `/api/`, que es donde de verdad se hace el trabajo.
        """
        ruta = request.url.path
        # En el servidor público estos endpoints no existen. Se corta antes de
        # mirar la sesión: tener cuenta no habilita a minar acá, ni siquiera a
        # la del dueño. Lo que se hace en la web es registrarse y descargar.
        if SOLO_WEB and ruta.startswith(CALCULO):
            return JSONResponse(
                {"detail": "El minado y el backtesting corren en la aplicación de "
                           "escritorio. Descargala desde tu cuenta."},
                status_code=404)
        # COMPARTIR NO PIDE CUENTA, ni para publicar ni para abrir: el enlace
        # existe para quien no tiene BotiQuant, y publicar viene de la
        # aplicación de escritorio, que no tiene sesión en el sitio.
        publica = ruta.startswith("/api/s/") or ruta.startswith("/api/compartir")
        if (_auth_listo() and ruta.startswith("/api/") and ruta not in SIN_CUENTA
                and not publica and usuario_actual(request) is None):
            return JSONResponse(
                {"detail": "Entrá con tu cuenta para usar Botiquant."},
                status_code=401)
        return await call_next(request)

    @app.get("/api/auth/me")
    def auth_me(request: Request) -> dict[str, Any]:
        u = usuario_actual(request)
        return {
            "configurado": _auth_listo(),
            "usuario": None if u is None else {
                "email": u["email"], "name": u["name"], "picture": u["picture"],
            },
        }

    #: A dónde puede volver el usuario después de entrar. Lista blanca y no
    #: validación: aceptar un destino cualquiera convierte el login en un
    #: redirector abierto, que es la pieza que hace creíble un phishing —
    #: el enlace sale del dominio real y termina en otro.
    DESTINOS = {"/", "/app"}

    @app.get("/api/auth/google/start", include_in_schema=False)
    def auth_start(next: str = "/") -> Response:
        if not _auth_listo():
            raise HTTPException(503, "El inicio de sesión no está configurado en este servidor.")
        estado = new_state()
        destino = next if next in DESTINOS else "/"
        r = RedirectResponse(authorize_url(gcfg, estado), status_code=307)
        # el state viaja firmado en una cookie propia y corta: es lo que
        # permite comprobar en el callback que la vuelta corresponde a una ida
        # que salió de acá y no de otro sitio. El destino viaja con él, dentro
        # de la firma, para que no se pueda cambiar por el camino.
        r.set_cookie("bq_oauth_state", sign({"s": estado, "d": destino}, SECRET, max_age=600),
                     max_age=600, httponly=True, samesite="lax",
                     secure=COOKIE_SECURE, path="/")
        return r

    @app.get("/api/auth/google/callback", include_in_schema=False)
    def auth_callback(request: Request, code: str = "", state: str = "",
                      error: str = "") -> Response:
        if error:
            return RedirectResponse(f"/?login=error&motivo={error}", status_code=303)
        if not _auth_listo() or not code:
            return RedirectResponse("/?login=error", status_code=303)
        try:
            guardado = verify(request.cookies.get("bq_oauth_state", ""), SECRET)
        except SessionError:
            return RedirectResponse("/?login=expirado", status_code=303)
        if not state or not hmac.compare_digest(str(guardado.get("s", "")), state):
            return RedirectResponse("/?login=error", status_code=303)

        try:
            token = exchange_code(gcfg, code)
            perfil = fetch_profile(token["access_token"])
        except Exception:                       # red caída, code vencido, etc.
            return RedirectResponse("/?login=error", status_code=303)

        u = db.upsert_user(perfil["sub"], perfil["email"], perfil["name"],
                           perfil["picture"])
        # Lo guardado antes de que existieran las cuentas no tiene dueño y, con
        # el filtro puesto, quedaría invisible para siempre.
        #
        # La condición es "hay UNA sola cuenta", no "es la primera vez que
        # alguien entra". No es lo mismo: en esta misma máquina la cuenta ya
        # existía desde antes de que el scoping existiera, así que un "primer
        # login" no iba a repetirse nunca y las estrategias viejas se perdían
        # de vista. Con una sola cuenta no hay ambigüedad posible sobre de
        # quién es lo que había. Con dos ya no se adopta nada.
        if db.count_users() == 1:
            db.adoptar_huerfanos(u["id"])
        # el destino salió firmado; aun así se vuelve a filtrar por la lista
        # blanca, porque una firma vieja podría traer algo que ya no aceptamos
        destino = str(guardado.get("d", "/"))
        if destino not in DESTINOS:
            destino = "/"
        r = RedirectResponse(f"{destino}?login=ok", status_code=303)
        set_cookie(r, sign({"uid": u["id"]}, SECRET), secure=COOKIE_SECURE)
        r.delete_cookie("bq_oauth_state", path="/")
        return r

    @app.post("/api/auth/logout")
    def auth_logout() -> Response:
        r = JSONResponse({"status": "ok"})
        clear_cookie(r)
        return r

    # ------------------------------------------------------------------ jobs
    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return job.to_dict()

    @app.post("/api/jobs/{job_id}/stop")
    def stop_job(job_id: str) -> dict[str, str]:
        if not jobs.cancel(job_id):
            raise HTTPException(404, "Job not found")
        return {"status": "stopping"}

    @app.post("/api/jobs/{job_id}/pause")
    def pause_job(job_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Frena el hilo sin perder la búsqueda.

        Detener descarta la población, los genomas ya probados y el punto de la
        semilla: volver a arrancar re-explora lo mismo. Pausar los conserva.
        """
        on = True if payload is None else bool(payload.get("paused", True))
        if not jobs.pause(job_id, on):
            raise HTTPException(404, "Ese trabajo ya no está corriendo.")
        return {"paused": on}

    #: un ida y vuelta que supere este % del precio no es un costo de broker,
    #: es una configuración heredada de otro instrumento
    _MAX_COST_PCT = 2.0

    def _check_cost_scale(df, settings: BacktestSettings) -> None:
        """Frena una corrida cuyos costos no corresponden a este mercado.

        Dejar el spread de 0.36 del S&P y minar EURUSD a 1.15 significa pagar
        31% de costo por operación: absolutamente todas las candidatas dan
        -100% y la búsqueda parece rota. Es preferible un error explícito.
        """
        price = float(df["close"].iloc[-1]) if len(df) else 0.0
        if price <= 0:
            return
        round_trip = settings.spread + 2 * settings.slippage
        pct = round_trip / price * 100.0
        if pct > _MAX_COST_PCT:
            raise HTTPException(400,
                f"Los costos no corresponden a este instrumento: spread "
                f"{settings.spread:g} + slippage sobre un precio de {price:g} "
                f"es {pct:.1f}% por operación. Corregí spread y slippage "
                f"(sección Costos del broker) antes de minar.")

    @app.post("/api/mine")
    def start_mine(request: Request, payload: dict[str, Any]) -> dict[str, str]:
        df = _load_df(payload)
        risk = _risk(payload)
        settings = _settings(payload)
        _check_cost_scale(df, settings)
        from botiquant.generator.templates import drivers as all_drivers, filters as all_filters
        drv = payload.get("drivers") or [d.id for d in all_drivers()]
        flt = payload.get("filters")
        if flt is None:
            flt = [f.id for f in all_filters()]
        ses = sesiones.normalizar(payload.get("sessions"))
        raw_seed = payload.get("seed")
        seed = int(raw_seed) if raw_seed not in (None, "") else None

        def _crit(key):
            v = payload.get(key)
            return float(v) if v not in (None, "") else None
        def _rr_choices(p: dict[str, Any]) -> list[float] | None:
            """Los R:B entre los que puede elegir cada candidata.

            Sin lista, cada una usa el configurado y todo funciona como antes.
            Con lista, la relación pasa a ser un gen — que es lo único que
            permite encontrar familias de win rate alto: medido sobre SP500 a
            una hora, con 1:2 fijo ninguna de treinta llega a 60% de aciertos,
            y con 0,5 lo pasan quince.

            Se acota a un rango con sentido: por debajo de 0,2 el objetivo cae
            adentro del spread en casi cualquier instrumento, y por encima de
            10 casi ninguna operación llega a tocarlo.
            """
            crudo = p.get("rr_choices")
            if not isinstance(crudo, (list, tuple)) or not crudo:
                return None
            vistos: list[float] = []
            for x in crudo[:24]:
                try:
                    v = round(float(x), 4)
                except (TypeError, ValueError):
                    continue
                if 0.2 <= v <= 10.0 and v not in vistos:
                    vistos.append(v)
            return vistos or None

        # SE ARMA DESDE LA TABLA DE CRITERIOS Y NO A MANO.
        #
        # Estaban enumerados uno por uno, y esa lista es un lugar donde un
        # filtro desaparece sin ruido: se agrega un criterio a `_CRITERIA`, se
        # dibuja en la pantalla, el usuario lo tilda... y si nadie se acordó de
        # sumarlo también acá, el número viaja y nadie lo mira. No pasa un
        # error: pasa que la búsqueda no filtra por algo que se le pidió.
        #
        # Derivándolo, agregar un criterio lo conecta de punta a punta o no
        # existe en ningún lado. Las dos mitades del bug quedan cerradas: acá
        # no se puede olvidar una clave, y `mine` rechaza una que no conozca.
        from botiquant.mining.miner import _CRIT_BY_KEY
        accept = {k: _crit(k) for k in _CRIT_BY_KEY}

        # the goal is a number of ACCEPTED strategies; max_candidates only caps
        # how long the search may hunt for them
        raw_target = payload.get("target_keep")
        target_keep = (int(min(max(int(raw_target), 1), 1000))
                       if raw_target not in (None, "") else None)

        # el tramo realmente usado viaja con el resultado: sin esto no se sabe
        # sobre qué período se minó una estrategia, que es el dato que separa
        # una validación out-of-sample honesta de una que se engaña sola
        used_range = {"from": str(df.index[0]), "to": str(df.index[-1]),
                      "bars": int(len(df))}

        dueno = duenio(request)
        try:
            ds_nombre = db.get_dataset(payload["dataset_id"], dueno)["name"]
        except KeyError:
            ds_nombre = ""

        def archivar(out: dict[str, Any]) -> str | None:
            """Guarda la corrida terminada con su databank entero.

            Antes de esto el databank vivía en la memoria del trabajo: arrancar
            otra búsqueda lo borraba y no había forma de comparar dos corridas
            ni de rescatar una estrategia dos días después.

            Se archiva del lado del servidor y no de la pantalla a propósito.
            Una búsqueda larga se deja corriendo y uno se va; si el guardado
            dependiera del navegador abierto, cerrarlo tiraría el trabajo.

            El contexto va completo porque una fila del banco sin él es un
            número sin unidad: 40% anual al 1% de riesgo y 40% al 3% no son
            comparables, y sin el instrumento ni los costos la estrategia
            tampoco se puede volver a exportar.

            Una corrida que no encontró NADA se archiva igual, sin filas. Es el
            experimento que más conviene tener anotado: dice que con esa vara,
            sobre ese instrumento, se probaron novecientas candidatas y no pasó
            ninguna. Sin ese registro se vuelve a intentar lo mismo dentro de
            un mes. Ocupa una fila y no cuenta contra el tope del banco.
            """
            ended = ("detenida" if out.get("stopped")
                     else "completa" if out.get("reached_goal") else "sin llegar")
            contexto = {
                "direction": payload.get("direction", "both"),
                "method": out.get("method"), "fitness": payload.get("fitness", "composite"),
                "min_trades": out.get("min_trades"), "accept": out.get("accept") or {},
                "target_keep": out.get("target_keep"),
                "sessions": out.get("sessions") or [],
                "risk": dataclasses.asdict(risk),
                # to_dict() y NO asdict(): el segundo arrastra la serie de
                # funding entera y revienta al archivar la corrida, despues de
                # haber corrido todas las candidatas.
                "settings": settings.to_dict(),
                "measured_range": out.get("measured_range"), "range": out.get("range"),
                "split": out.get("split"), "exhausted": out.get("exhausted"),
                "hit_cap": out.get("hit_cap"),
            }
            try:
                guardado = db.guardar_corrida(
                    dataset_id=payload["dataset_id"], dataset_name=ds_nombre,
                    timeframe=payload.get("timeframe") or "native",
                    seed=out.get("seed"), tested=out.get("tested", 0),
                    elapsed=out.get("elapsed_s", 0.0), ended=ended, contexto=contexto,
                    filas=out.get("databank") or [], user_id=dueno)
            except sqlite3.Error:
                # que falle el archivado no puede tirar la corrida: el usuario
                # esperó los minutos y el resultado ya está en pantalla
                traceback.print_exc()
                return None
            out["podadas"] = guardado["podadas"]
            return guardado["id"]

        def work(handle):
            out = mine(
                df, drv, flt,
                max_filters=int(min(max(int(payload.get("max_filters", 2)), 0), 4)),
                direction=payload.get("direction", "both"),
                risk=risk, settings=settings,
                fitness_mode=payload.get("fitness", "composite"),
                min_trades=int(payload.get("min_trades", 30)),
                accept=accept,
                max_candidates=int(min(max(int(payload.get("max_candidates", 2000)), 10), 500_000)),
                target_keep=target_keep,
                keep_top=int(min(max(int(payload.get("keep_top", 100)), 10), 1000)),
                oos_pct=float(min(max(float(payload.get("oos_pct") or 0.0), 0.0), 80.0)),
                # Que las varas se cumplan TAMBIEN en el tramo reservado. Sin
                # esto, el fuera de muestra reordena pero no rechaza: una
                # estrategia que se derrumba afuera entra igual al databank,
                # sólo que con el score castigado.
                exigir_oos=bool(payload.get("exigir_oos")),
                sessions=ses,
                rr_choices=_rr_choices(payload),
                method="evolution" if payload.get("method") == "evolution" else "random",
                population=int(min(max(int(payload.get("population", 40)), 8), 200)),
                seed=seed,
                # SOLO LO QUE EL BOT PUEDE ENCENDER, cuando quien mina lo pide.
                # El ciclo lo pedía y esto no lo pasaba: minaba con trailing
                # igual y descubría al promover que no podía usarlas.
                sin_trailing=bool(payload.get("sin_trailing")),
                handle=handle,
            )
            out["range"] = used_range
            out["corrida_id"] = archivar(out)
            # EL CICLO PIDE QUE LO ENCONTRADO QUEDE EN MIS ESTRATEGIAS, como
            # nuevas, para validarlas y promoverlas en las vueltas siguientes.
            # Sin esto minaba para el banco y nada más. Un fallo al guardar no
            # tira abajo el minado: la corrida ya está archivada.
            if payload.get("guardar_al_terminar") and out["corrida_id"]:
                try:
                    filas = db.get_banco(db.ids_banco_de(out["corrida_id"], dueno), dueno)
                    out["guardadas"] = _guardar_filas_del_banco(filas, dueno)
                except Exception:                           # noqa: BLE001
                    traceback.print_exc()
            return out
        return {"job_id": jobs.submit_streaming("mine", work, dueno)}

    @app.post("/api/generate")
    def start_generate(request: Request, payload: dict[str, Any]) -> dict[str, str]:
        df = _load_df(payload)
        risk = _risk(payload)
        settings = _settings(payload)

        def work(progress):
            return generate_strategies(
                df,
                allowed_drivers=payload.get("drivers") or None,
                allowed_filters=payload.get("filters") or None,
                max_filters=int(payload.get("max_filters", 1)),
                direction=payload.get("direction", "both"),
                risk=risk, settings=settings,
                fitness_mode=payload.get("fitness", "composite"),
                min_trades=int(payload.get("min_trades", 20)),
                top_n=int(payload.get("top_n", 20)),
                progress=progress,
            )
        return {"job_id": jobs.submit("generate", work, duenio(request))}

    @app.post("/api/evolve")
    def start_evolve(request: Request, payload: dict[str, Any]) -> dict[str, str]:
        df = _load_df(payload)
        risk = _risk(payload)
        settings = _settings(payload)
        from botiquant.generator.templates import drivers as all_drivers, filters as all_filters
        drv = payload.get("drivers") or [d.id for d in all_drivers()]
        flt = payload.get("filters") or [f.id for f in all_filters()]

        def work(progress):
            return evolve(
                df, drivers=drv, filters=flt,
                max_filters=int(payload.get("max_filters", 2)),
                direction=payload.get("direction", "both"),
                risk=risk, settings=settings,
                population=int(min(max(int(payload.get("population", 30)), 10), 120)),
                generations=int(min(max(int(payload.get("generations", 10)), 2), 60)),
                mutation_rate=float(payload.get("mutation_rate", 0.3)),
                fitness_mode=payload.get("fitness", "composite"),
                min_trades=int(payload.get("min_trades", 20)),
                seed=int(payload.get("seed", 42)),
                progress=progress,
            )
        return {"job_id": jobs.submit("evolve", work, duenio(request))}

    @app.post("/api/optimize/dimensions")
    def optimize_dimensions(payload: dict[str, Any]) -> dict[str, Any]:
        spec = _spec(payload)
        return {"dimensions": [d.to_dict() for d in discover_dimensions(spec)]}

    @app.post("/api/optimize")
    def start_optimize(request: Request, payload: dict[str, Any]) -> dict[str, str]:
        df = _load_df(payload)
        spec = _spec(payload)
        settings = _settings(payload)

        def work(progress):
            return optimize(
                df, spec, mode=payload.get("mode", "quick"),
                settings=settings,
                fitness_mode=payload.get("fitness", "composite"),
                min_trades=int(payload.get("min_trades", 10)),
                seed=int(payload.get("seed", 42)),
                progress=progress,
            )
        return {"job_id": jobs.submit("optimize", work, duenio(request))}

    @app.post("/api/walkforward")
    def start_walkforward(request: Request, payload: dict[str, Any]) -> dict[str, str]:
        """Walk-forward sobre una estrategia ya encontrada.

        Acepta las dos formas de decir cuál. Un ``spec`` suelto con su dataset
        —que es como nació este endpoint— o una referencia a algo del banco o
        de Mis estrategias, que es como lo usa la pantalla: ahí el instrumento,
        el timeframe y los costos salen de la propia estrategia y no de lo que
        esté configurado en Mining, que puede ser otro mercado por completo.
        """
        etiqueta = ""
        if payload.get("estrategia"):
            p = payload["estrategia"]
            e = _para_validar(str(p.get("origen") or "banco"), str(p.get("id") or ""),
                              duenio(request))
            if not e["dataset_id"]:
                raise HTTPException(400, "No sabemos con qué instrumento se encontró.")
            spec = StrategySpec.from_dict(e["spec"])
            settings = BacktestSettings.from_dict(
                {k: v for k, v in e["settings"].items() if v is not None})
            # El período: el que se pida, y si no, TODO el histórico del
            # instrumento. A propósito no se limita al tramo medido — el sentido
            # del walk-forward es tener tramos consecutivos, y cuanto más
            # histórico haya, más honesto es el corte.
            df = _load_df({"dataset_id": e["dataset_id"], "timeframe": e["timeframe"],
                           "date_from": payload.get("date_from"),
                           "date_to": payload.get("date_to")})
            etiqueta = f"{e['nombre']} · {e['dataset_name']} {e['timeframe']}".strip()
        else:
            df = _load_df(payload)
            spec = _spec(payload)
            settings = _settings(payload)

        rango = {"from": str(df.index[0])[:10], "to": str(df.index[-1])[:10],
                 "bars": int(len(df))}

        def work(progress):
            try:
                out = walk_forward(
                    df, spec,
                    folds=int(payload.get("folds", 4)),
                    train_pct=float(payload.get("train_pct", 70.0)),
                    optimize_budget=int(payload.get("budget", 40)),
                    settings=settings,
                    fitness_mode=payload.get("fitness", "composite"),
                    seed=int(payload.get("seed", 42)),
                    progress=progress,
                )
            except ValueError as exc:
                # "no alcanza el histórico para tantos tramos" es una elección
                # corregible del usuario, no una falla: viaja como resultado
                # para que la pantalla pueda explicar qué cambiar
                return {"error": str(exc), "rango": rango, "etiqueta": etiqueta}
            out["rango"] = rango
            out["etiqueta"] = etiqueta
            return out
        return {"job_id": jobs.submit("walkforward", work, duenio(request))}

    # ----------------------------------------------------------- monte carlo
    @app.post("/api/montecarlo")
    def run_montecarlo(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        rid = payload.get("result_id")
        initial = float(payload.get("initial_capital", 10_000.0))
        if payload.get("estrategia"):
            # Una estrategia del banco o de las guardadas: hay que correrle el
            # backtest para tener sus operaciones. El Monte Carlo no simula
            # precios, rebaraja las operaciones REALES que dio la estrategia.
            p = payload["estrategia"]
            e = _para_validar(str(p.get("origen") or "banco"), str(p.get("id") or ""),
                              duenio(request))
            if not e["dataset_id"]:
                raise HTTPException(400, "No sabemos con qué instrumento se encontró.")
            medido = e["medido"] or {}
            ajustes = {k: v for k, v in e["settings"].items() if v is not None}
            df = _load_df({"dataset_id": e["dataset_id"], "timeframe": e["timeframe"],
                           **({"date_from": medido["from"], "date_to": medido["to"]}
                              if medido.get("from") else {})})
            res = run_backtest(df, StrategySpec.from_dict(e["spec"]),
                               BacktestSettings.from_dict(ajustes))
            pnls = [t["pnl"] for t in res.to_dict().get("trades", [])]
            if ajustes.get("initial_capital"):
                initial = float(ajustes["initial_capital"])
        elif rid:
            row = db.get_result(rid, duenio(request))
            pnls = [t["pnl"] for t in row["payload"].get("trades", [])]
        else:
            pnls = [float(x) for x in payload.get("trade_pnls", [])]
        try:
            return monte_carlo(
                pnls, initial_capital=initial,
                simulations=int(payload.get("simulations", 1000)),
                ruin_threshold_pct=float(payload.get("ruin_threshold_pct", 30.0)),
                seed=int(payload.get("seed", 42)),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ------------------------------------------------------------ validación
    def _para_validar(origen: str, ident: str, dueno: str | None) -> dict[str, Any]:
        """Una estrategia lista para volver a correr, venga de donde venga.

        El banco y Mis estrategias guardan lo mismo con distinta forma: el
        banco tiene la fila y el contexto en su corrida, y una guardada lo
        lleva todo en su `meta`. Unificarlo acá evita que cada validación
        tenga que saber de dónde salió lo que está evaluando.
        """
        if origen == "banco":
            filas = db.get_banco([ident], dueno)
            if not filas:
                raise HTTPException(404, "Esa estrategia ya no está en el banco.")
            f = filas[0]
            ctx = f["contexto"]
            return {
                "id": ident, "origen": origen, "nombre": f["nombre"],
                "spec": f["fila"].get("spec") or {},
                "dataset_id": f["dataset_id"] or "", "timeframe": f["timeframe"] or "",
                "dataset_name": f["dataset_name"] or "",
                "settings": ctx.get("settings") or {},
                "medido": ctx.get("measured_range") or {},
                "metricas": (f["fila"].get("metrics") or {}),
            }
        try:
            s = db.get_strategy(ident, dueno)
        except KeyError as exc:
            raise HTTPException(404, "Esa estrategia no existe.") from exc
        m = s.get("meta") or {}
        return {
            "id": ident, "origen": "guardada", "nombre": s["name"],
            "spec": s["spec"],
            "dataset_id": m.get("dataset_id") or "", "timeframe": m.get("timeframe") or "",
            "dataset_name": m.get("dataset_name") or "",
            "settings": {"initial_capital": m.get("capital"), "spread": m.get("spread"),
                         "slippage": m.get("slippage"), "commission_pct": m.get("commission")},
            "medido": m.get("measured_range") or {},
            "metricas": m.get("metrics") or {},
        }

    def _se_solapa(medido: dict[str, Any], desde: str, hasta: str) -> float:
        """Qué porcentaje del período pedido ya lo vio la búsqueda.

        Es la comprobación que decide si una validación significa algo. Volver
        a correr una estrategia sobre las mismas velas con las que se la
        encontró no la valida: devuelve los mismos números por construcción, y
        confirma nada más que la aritmética funciona. Como el error se ve
        idéntico a un éxito, hay que medirlo y decirlo.
        """
        if not medido.get("from") or not medido.get("to"):
            return 0.0
        try:
            mi, mf = pd.Timestamp(medido["from"]), pd.Timestamp(medido["to"])
            pi, pf = pd.Timestamp(desde), pd.Timestamp(hasta)
        except (ValueError, TypeError):
            return 0.0
        cruce = (min(mf, pf) - max(mi, pi)).total_seconds()
        total = (pf - pi).total_seconds()
        if total <= 0 or cruce <= 0:
            return 0.0
        return round(min(cruce / total, 1.0) * 100.0, 1)

    @app.post("/api/validar")
    def validar(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        """Corre estrategias ya encontradas sobre un período que elige el usuario.

        La diferencia con la validación del minado es cuándo se decide el
        tramo. Ahí se reserva ANTES de buscar; acá se elige después, y eso
        permite preguntar algo que antes no se podía: cómo le fue a esto en el
        último año, o durante un año concreto.
        """
        desde = str(payload.get("date_from") or "").strip()
        hasta = str(payload.get("date_to") or "").strip()
        if not desde or not hasta:
            raise HTTPException(400, "Hace falta el período sobre el que validar.")
        pedidas = payload.get("estrategias") or []
        if not pedidas:
            raise HTTPException(400, "Elegí al menos una estrategia.")
        dueno = duenio(request)

        salida = []
        for p in pedidas[:30]:
            e = _para_validar(str(p.get("origen") or "banco"), str(p.get("id") or ""), dueno)
            fila: dict[str, Any] = {
                "id": e["id"], "origen": e["origen"], "nombre": e["nombre"],
                "antes": e["metricas"],
                "solapamiento_pct": _se_solapa(e["medido"], desde, hasta),
            }
            if not e["dataset_id"]:
                fila["error"] = "No sabemos con qué instrumento se encontró."
                salida.append(fila)
                continue
            try:
                df = _load_df({"dataset_id": e["dataset_id"], "timeframe": e["timeframe"],
                               "date_from": desde, "date_to": hasta})
                res = run_backtest(df, StrategySpec.from_dict(e["spec"]),
                                   BacktestSettings.from_dict(
                                       {k: v for k, v in e["settings"].items() if v is not None}))
            except HTTPException as exc:
                fila["error"] = str(exc.detail)
                salida.append(fila)
                continue
            except ValueError as exc:
                fila["error"] = str(exc)
                salida.append(fila)
                continue
            d = res.to_dict()
            fila["despues"] = d["metrics"]
            fila["score"] = bq_score(d["metrics"])
            fila["equity"] = d.get("equity", [])
            fila["timestamps"] = d.get("timestamps", [])
            # cuánto sobrevive la ventaja: profit factor de afuera sobre el de
            # adentro. Se usa el PF y no la ganancia porque no depende de
            # cuántos años tenga cada tramo.
            pf_antes = float(e["metricas"].get("profit_factor") or 0.0)
            pf_ahora = float(d["metrics"].get("profit_factor") or 0.0)
            fila["ratio"] = (round(min(pf_ahora / pf_antes, 9.99), 3)
                             if pf_antes > 1e-9 else None)
            salida.append(fila)
        return {"periodo": {"from": desde, "to": hasta}, "resultados": salida}

    @app.post("/api/robustez")
    def robustez(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        """Monte Carlo sobre VARIAS estrategias, para poder compararlas.

        De a una no sirve para decidir: el número solo no dice si está bien o
        mal. Puestos al lado, se ve cuál de las que uno encontró aguanta mejor
        una racha mala, que es la pregunta que se está haciendo en realidad.
        """
        pedidas = payload.get("estrategias") or []
        if not pedidas:
            raise HTTPException(400, "Elegí al menos una estrategia.")
        dueno = duenio(request)
        sims = int(min(max(int(payload.get("simulations", 1000)), 100), 5000))
        umbral = float(payload.get("ruin_threshold_pct", 30.0))
        semilla = int(payload.get("seed", 42))

        salida = []
        for p in pedidas[:20]:
            e = _para_validar(str(p.get("origen") or "banco"), str(p.get("id") or ""), dueno)
            fila: dict[str, Any] = {
                "id": e["id"], "origen": e["origen"], "nombre": e["nombre"],
                # dos corridas distintas nombran S-001 a su primera estrategia:
                # sin el mercado, la tabla muestra dos filas idénticas
                "mercado": e["dataset_name"], "timeframe": e["timeframe"],
            }
            try:
                if not e["dataset_id"]:
                    raise ValueError("No sabemos con qué instrumento se encontró.")
                medido = e["medido"] or {}
                ajustes = {k: v for k, v in e["settings"].items() if v is not None}
                df = _load_df({"dataset_id": e["dataset_id"], "timeframe": e["timeframe"],
                               **({"date_from": medido["from"], "date_to": medido["to"]}
                                  if medido.get("from") else {})})
                res = run_backtest(df, StrategySpec.from_dict(e["spec"]),
                                   BacktestSettings.from_dict(ajustes))
                pnls = [t["pnl"] for t in res.to_dict().get("trades", [])]
                mc = monte_carlo(pnls,
                                 initial_capital=float(ajustes.get("initial_capital") or 10_000.0),
                                 simulations=sims, ruin_threshold_pct=umbral, seed=semilla)
            except (ValueError, HTTPException) as exc:
                fila["error"] = str(getattr(exc, "detail", exc))
                salida.append(fila)
                continue
            inicial = mc["initial_capital"]
            fila["mc"] = mc
            fila["prob_perder"] = mc["final_equity"]["prob_loss"]
            fila["ruina"] = mc["risk_of_ruin_pct"]
            fila["dd_p95"] = mc["max_drawdown_pct"]["p95"]
            fila["final_mediana"] = mc["final_equity"]["median"]
            fila["operaciones"] = mc["trades_per_sim"]
            # El capital con el que se termina en el peor de cada veinte
            # repartos. Es el número por el que se elige: junta cuánto gana y
            # cuánto puede salir mal en una sola cifra que se entiende sola,
            # sin inventar un puntaje que nadie pueda comprobar. Ordenar por
            # ganancia premiaría a la que tuvo suerte; ordenar sólo por riesgo
            # premiaría a la que no arriesga y no gana nada.
            fila["peor_razonable"] = mc["final_equity"]["ci_90"][0]
            fila["peor_razonable_pct"] = round(
                (fila["peor_razonable"] / inicial - 1.0) * 100.0, 2) if inicial else 0.0
            salida.append(fila)

        # Ordena por con qué frecuencia termina ganando, y desempata por lo que
        # queda en el peor escenario.
        #
        # Se probó al revés —primero el peor escenario— y elegía mal: ponía
        # arriba una que gana el 67% de las veces sobre otra que gana el 89%,
        # por una diferencia de medio punto en el peor caso que es ruido. La
        # frecuencia con que gana es lo que de verdad separa a una de otra, y
        # además es lo único que alguien puede leer sin que se lo expliquen.
        sanas = [x for x in salida if "mc" in x]
        sanas.sort(key=lambda x: (x["prob_perder"], -x["peor_razonable"]))
        for i, x in enumerate(sanas):
            x["puesto"] = i + 1
        return {"resultados": salida, "simulations": sims, "ruin_threshold_pct": umbral}

    # --------------------------------------------------------- poner a prueba
    #: Los valores con los que corren las pruebas. Estaban como perillas en la
    #: pantalla y se sacaron: elegir "4 tramos" o "6 tramos" es una decisión que
    #: quien usa esto no puede tomar con fundamento, y ofrecerla sólo consigue
    #: que la pantalla parezca difícil. Cuatro tramos con 70% de ajuste es el
    #: estándar de la industria y aguanta cualquier histórico de los que se
    #: minan acá.
    PRUEBA = {"folds": 4, "train_pct": 70.0, "budget": 40,
              "simulations": 1000, "ruin_threshold_pct": 30.0}

    #: Veredicto del walk-forward -> estado que muestra la lista de estrategias.
    #: Cuatro estados y no dos porque "a medias" es un resultado real y muy
    #: común: decir "no pasó" de algo que sobrevivió en la mitad de los tramos
    #: sería mentir en la dirección contraria.
    ESTADOS = {"robust": "aprobada", "acceptable": "aceptable",
               "overfitted": "no_paso"}

    def _resumen_mc(mc: dict[str, Any]) -> dict[str, Any]:
        """Lo poco de Monte Carlo que hay que mirar, sin la distribución entera.

        Monte Carlo no dice si la estrategia sirve —rebaraja SUS operaciones,
        así que la ganancia total sale igual en las mil simulaciones y no puede
        detectar sobreajuste. Lo que sí mide es el camino: qué caída podrías
        haber tenido que aguantar si las pérdidas te hubieran caído juntas.
        Por eso de acá sólo salen dos números y no un tablero.
        """
        return {
            "dd_tipico_pct": mc["max_drawdown_pct"]["median"],
            "dd_malo_pct": mc["max_drawdown_pct"]["p95"],
            "ruina_pct": mc["risk_of_ruin_pct"],
            "prob_perder_pct": mc["final_equity"]["prob_loss"],
            "peor_razonable": mc["final_equity"]["ci_90"][0],
            "simulaciones": mc.get("simulations", PRUEBA["simulations"]),
            "operaciones": mc.get("trades_per_sim"),
        }

    def _detalle_prueba(wf: dict[str, Any], mc: dict[str, Any] | None) -> dict[str, Any]:
        """Lo justo para DIBUJAR la prueba después, no la distribución entera.

        Hasta acá el detalle viajaba una vez y se tiraba: quedaban tres
        números y una frase, y "cuatro tramos" no se entendía sin verlos. Se
        guarda muestreado —la curva a 120 puntos, las bandas a 60— y pesa
        unos pocos KB por estrategia, que es lo que cuesta poder mostrar los
        tramos, la curva fuera de muestra y el abanico de Monte Carlo cada
        vez que se abre la ficha.
        """
        def muestra(xs, n):
            xs = list(xs)
            if len(xs) <= n:
                return xs
            paso = (len(xs) - 1) / (n - 1)
            return [xs[round(i * paso)] for i in range(n)]

        tramos = [{
            "n": int(f["fold"]),
            "entrena": [str(f["train_start"])[:10], str(f["train_end"])[:10]],
            "juzga": [str(f["test_start"])[:10], str(f["test_end"])[:10]],
            "adentro_pct": round(float(f["is_net_profit_pct"]), 2),
            "afuera_pct": round(float(f["oos_net_profit_pct"]), 2),
            "operaciones": int(f["oos_trades"]),
            "caida_pct": round(float(f["oos_max_dd_pct"]), 2),
        } for f in wf.get("folds", [])]
        detalle: dict[str, Any] = {
            "tramos": tramos,
            "afuera": {
                "curva": [round(float(v), 2) for v in muestra(wf.get("oos_equity", []), 120)],
                "fechas": [str(x)[:10] for x in muestra(wf.get("oos_timestamps", []), 120)],
            },
        }
        if mc:
            b = mc["bands"]
            detalle["mc"] = {
                "bandas": {k: [round(float(v), 2) for v in muestra(b[k], 60)]
                           for k in ("p5", "p25", "p50", "p75", "p95")},
                "capital": float(mc["initial_capital"]),
                "caidas": mc["max_drawdown_pct"]["histogram"],
            }
        return detalle

    @app.post("/api/probar")
    def probar(request: Request, payload: dict[str, Any]) -> dict[str, str]:
        """Corre las dos pruebas sobre una estrategia GUARDADA y archiva el veredicto.

        Una sola acción y no dos botones: son dos preguntas distintas sobre la
        misma estrategia —¿sobrevive fuera de los datos donde la encontré? y
        ¿qué se siente operarla?— y ninguna de las dos se entiende sola. Además,
        pedirle a alguien que elija entre "walk-forward" y "Monte Carlo" es
        pedirle que sepa la respuesta antes de la pregunta.

        Sólo sobre guardadas: validar filas sueltas de un databank de novecientas
        no significa nada y llena la pantalla de trabajo inútil. Guardar es el
        gesto que dice "esta me interesa en serio", y es el que habilita esto.
        """
        sid = str(payload.get("strategy_id") or "").strip()
        if not sid:
            raise HTTPException(400, "Falta la estrategia.")
        dueno = duenio(request)
        e = _para_validar("guardada", sid, dueno)
        if not e["dataset_id"]:
            raise HTTPException(400, "No sabemos con qué instrumento se encontró.")

        spec = StrategySpec.from_dict(e["spec"])
        ajustes = {k: v for k, v in e["settings"].items() if v is not None}
        settings = BacktestSettings.from_dict(ajustes)
        medido = e["medido"] or {}
        df = _load_df({"dataset_id": e["dataset_id"], "timeframe": e["timeframe"],
                       **({"date_from": medido["from"], "date_to": medido["to"]}
                          if medido.get("from") else {})})

        def work(progress):
            progress(0.02, "Preparando")
            wf = walk_forward(
                df, spec, folds=int(PRUEBA["folds"]),
                train_pct=float(PRUEBA["train_pct"]),
                optimize_budget=int(PRUEBA["budget"]), settings=settings,
                progress=lambda f, m: progress(0.02 + f * 0.88, m),
            )
            # Monte Carlo va después y sobre el backtest COMPLETO, no sobre los
            # tramos: rebaraja las operaciones que la estrategia hizo de verdad
            # en todo el período, que es la muestra más grande disponible.
            progress(0.92, "Rebarajando las operaciones")
            res = run_backtest(df, spec, settings)
            pnls = [t.pnl for t in res.trades]
            mc = None
            if len(pnls) >= 5:
                mc = monte_carlo(
                    pnls, initial_capital=float(ajustes.get("initial_capital") or 10_000.0),
                    simulations=int(PRUEBA["simulations"]),
                    ruin_threshold_pct=float(PRUEBA["ruin_threshold_pct"]))

            resumen = wf["summary"]
            salida = {
                "estado": ESTADOS.get(resumen["verdict"], "no_paso"),
                "veredicto": resumen["verdict"],
                "tramos": resumen["folds"],
                "tramos_ganadores": resumen["profitable_folds"],
                "eficiencia": resumen["wf_efficiency"],
                "consistencia_pct": resumen["consistency_pct"],
                "retorno_fuera_pct": resumen["total_oos_return_pct"],
                "probada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "periodo": {"from": str(df.index[0])[:10], "to": str(df.index[-1])[:10]},
                "mc": _resumen_mc(mc) if mc else None,
                # y lo justo para dibujarla cada vez que se abra la ficha
                "detalle": _detalle_prueba(wf, mc),
            }
            try:
                db.guardar_validacion(sid, salida, dueno)
            except (KeyError, sqlite3.Error):
                # que falle el archivado no puede tirar el resultado: la prueba
                # ya tardó sus minutos y está en pantalla
                traceback.print_exc()
            # el detalle crudo viaja además entero, para quien lo pida ahora
            return {**salida, "detalle": {**salida["detalle"],
                                          "folds": wf["folds"],
                                          "oos_equity": wf["oos_equity"],
                                          "oos_timestamps": wf["oos_timestamps"]}}

        return {"job_id": jobs.submit("probar", work, dueno)}

    @app.delete("/api/probar/{sid}")
    def olvidar_prueba(request: Request, sid: str) -> dict[str, bool]:
        """Vuelve una estrategia a 'sin probar'. Sirve tras editarle las salidas:
        el veredicto viejo describía otra estrategia."""
        try:
            db.borrar_validacion(sid, duenio(request))
        except KeyError as exc:
            raise HTTPException(404, "Esa estrategia no existe.") from exc
        return {"ok": True}

    # ------------------------------------------------------------- portfolio
    @app.post("/api/portfolio")
    def portfolio(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        """Combina varias estrategias en una sola curva.

        Acepta resultados guardados —como nació— o estrategias del banco y de
        Mis estrategias, que es de donde salen en la práctica: nadie guarda un
        "resultado" para después armar un portafolio, guarda estrategias.

        Cuando vienen del banco hay que correrles el backtest para tener sus
        curvas. Es más lento que leer un resultado archivado y es lo correcto:
        la curva tiene que salir del mismo tramo y los mismos costos con los
        que se encontró cada una, o la combinación suma cosas que no son
        comparables.
        """
        dueno = duenio(request)
        components: list[dict[str, Any]] = []
        nombres_vistos: dict[str, int] = {}

        for p in (payload.get("estrategias") or [])[:12]:
            e = _para_validar(str(p.get("origen") or "banco"), str(p.get("id") or ""), dueno)
            if not e["dataset_id"]:
                raise HTTPException(400, f"{e['nombre']}: no sabemos con qué instrumento se encontró.")
            medido = e["medido"] or {}
            ajustes = {k: v for k, v in e["settings"].items() if v is not None}
            df = _load_df({"dataset_id": e["dataset_id"], "timeframe": e["timeframe"],
                           **({"date_from": medido["from"], "date_to": medido["to"]}
                              if medido.get("from") else {})})
            res = run_backtest(df, StrategySpec.from_dict(e["spec"]),
                               BacktestSettings.from_dict(ajustes))
            d = res.to_dict()
            # Dos corridas distintas llaman S-001 a su primera estrategia. Sin
            # desambiguar, pandas colapsaría las dos columnas en una y el
            # portafolio tendría menos componentes de los que se pidieron.
            base = f"{e['nombre']} · {e['dataset_name'] or ''}".strip(" ·")
            nombres_vistos[base] = nombres_vistos.get(base, 0) + 1
            nombre = base if nombres_vistos[base] == 1 else f"{base} ({nombres_vistos[base]})"
            components.append({
                "name": nombre,
                "equity": d.get("equity", []),
                "timestamps": d.get("timestamps", []),
                "initial_capital": float(ajustes.get("initial_capital") or 10_000.0),
                "metrics": d.get("metrics", {}),
                "origen": e["origen"], "id": e["id"],
            })

        for rid in (payload.get("result_ids") or []):
            try:
                row = db.get_result(rid, dueno)
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            p2 = row["payload"]
            components.append({
                "name": row["strategy_name"],
                "equity": p2.get("equity", []),
                "timestamps": p2.get("timestamps", []),
                "initial_capital": p2.get("equity", [10_000.0])[0] if p2.get("equity") else 10_000.0,
                "metrics": p2.get("metrics", {}),
            })
        try:
            salida = build_portfolio(components, payload.get("weights"),
                                     float(payload.get("initial_capital", 10_000.0)))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        # Las métricas de cada componente por separado viajan con el resultado:
        # el portafolio sólo tiene sentido comparado contra sus partes, y sin
        # esto la pantalla tendría que pedir cada backtest otra vez.
        salida["componentes"] = [
            {"name": c["name"], "metrics": c.get("metrics") or {}} for c in components
        ]
        return salida

    # ------------------------------------------------------------ strategies
    @app.get("/api/strategies")
    def list_strategies(request: Request, mundo: str = "") -> list[dict[str, Any]]:
        """Las estrategias guardadas, con hasta dónde puede llegar cada una.

        El veredicto de la cantera viaja acá y no se calcula en la pantalla
        por dos motivos. Uno: es la MISMA función que usa el endpoint de
        encender, así que lo que se ve y lo que se hace no pueden divergir.
        Dos: que el destino aparezca cerrado ANTES de apretar es la mitad del
        valor del filtro — un rechazo después del clic enseña lo mismo pero
        se siente como un obstáculo, y uno antes se lee como una guía.
        """
        from botiquant import cantera, estados

        filas = [f for f in db.list_strategies(duenio(request))
                 if _es_del_mundo((f.get("meta") or {}).get("dataset_name") or "", mundo)]
        for f in filas:
            # DONDE ESTA, que es distinto de hasta donde PODRIA llegar. Una
            # estrategia puede estar habilitada para real y no haberse
            # encendido nunca; si el estado se dedujera de las metricas,
            # encender un bot no cambiaria nada en la pantalla.
            f["estado"] = estados.normalizar(f.get("estado"))
            f["siguiente"] = estados.siguiente(f["estado"])
            meta = f.get("meta") or {}
            entrada = {"metrics": meta.get("metrics"), "oos": meta.get("oos")}
            f["cantera"] = {
                d: {"pasa": (r := cantera.revisar(entrada, d)).pasa,
                    "por_que_no": cantera.por_que_no(r)}
                for d in (cantera.SIMULACRO, cantera.PRACTICA, cantera.REAL)
            }
        return filas

    @app.post("/api/strategies")
    def save_strategy(request: Request, payload: dict[str, Any]) -> dict[str, str]:
        spec = _spec(payload)
        # el contexto viaja tal cual lo mandó la UI: sin instrumento, timeframe
        # y costos, una estrategia guardada no se puede volver a exportar
        meta = dict(payload.get("meta") or {})
        if payload.get("dataset_id"):
            meta.setdefault("dataset_id", payload["dataset_id"])
            try:
                meta.setdefault("dataset_name",
                                db.get_dataset(payload["dataset_id"], duenio(request))["name"])
            except KeyError:
                pass
        try:
            sid = db.save_strategy(str(payload.get("name") or spec.name), spec.to_dict(),
                                   strategy_id=payload.get("id"),
                                   notes=str(payload.get("notes", "")),
                                   meta=meta, user_id=duenio(request))
        except KeyError as exc:
            # Actualizar algo que no es tuyo devuelve 404 y no 403: un 403
            # confirmaría que ese id existe y es de otro.
            raise HTTPException(404, "Esa estrategia no existe.") from exc
        return {"id": sid}

    @app.post("/api/strategies/{sid}/nota")
    def guardar_nota(request: Request, sid: str, payload: dict[str, Any]) -> dict[str, str]:
        """Cambia SÓLO la nota de una estrategia guardada.

        Existe aparte de ``POST /api/strategies`` porque ese endpoint espera el
        spec entero y lo reescribe. Para anotar por qué guardaste algo, mandar
        de vuelta la estrategia completa es pedirle a la pantalla que arriesgue
        pisar el spec con lo que tenga en memoria.
        """
        dueno = duenio(request)
        try:
            s = db.get_strategy(sid, dueno)
        except KeyError as exc:
            raise HTTPException(404, "Esa estrategia no existe.") from exc
        # Un tope generoso pero real: es un campo de texto libre que va a la
        # base sin límite propio, y un pegado accidental de dos megabytes se
        # guardaría sin protestar.
        nota = str(payload.get("notes", ""))[:4000]
        db.save_strategy(s["name"], s["spec"], strategy_id=sid, notes=nota,
                         meta=s.get("meta") or {}, user_id=dueno)
        return {"status": "ok", "notes": nota}

    @app.delete("/api/strategies/{sid}")
    def delete_strategy(request: Request, sid: str) -> dict[str, str]:
        db.delete_strategy(sid, duenio(request))
        return {"status": "deleted"}

    # ----------------------------------------------------------------- banco
    #: Cuántas filas devuelve un pedido del banco. El tope existe porque la
    #: tabla ya viene ordenada por la base: pedir más que esto es pedir filas
    #: que nadie va a mirar, y cada una arrastra su curva de capital.
    _PAGINA_BANCO = 200

    def _es_del_mundo(nombre_dataset: str, mundo: str) -> bool:
        """Si un histórico se muestra en la sección pedida.

        CADA SECCIÓN VE SÓLO LO SUYO. Con las dos secciones compartiendo el
        banco, "Cripto" abría con las 236 corridas de SP500 y la sección
        parecía no hacer nada al cambiar (2 de septiembre). Lo que no se
        puede clasificar —un CSV propio, una guardada vieja— se ve en las
        dos, porque adivinarle un mundo sería peor que dejarlo a la vista.
        """
        if not mundo:
            return True
        m = mundo_de_nombre(nombre_dataset or "")
        return m is None or m == mundo

    def _corridas_del_mundo(dueno, mundo: str):
        """Las corridas de la sección, y sus ids (None = sin recorte)."""
        corridas = [c for c in db.list_corridas(dueno)
                    if _es_del_mundo(c.get("dataset_name") or "", mundo)]
        ids = [c["id"] for c in corridas] if mundo else None
        return corridas, ids

    @app.get("/api/corridas")
    def list_corridas(request: Request, mundo: str = "") -> dict[str, Any]:
        dueno = duenio(request)
        corridas, ids = _corridas_del_mundo(dueno, mundo)
        return {
            "corridas": corridas,
            "total": db.contar_banco(dueno, corrida_ids=ids),
            "tope": db.TOPE_BANCO,
            "tope_corridas": db.TOPE_CORRIDAS,
        }

    @app.get("/api/banco")
    def list_banco(request: Request, corrida: str = "", orden: str = "puesto",
                   dir: str = "", limite: int = _PAGINA_BANCO,
                   desde: int = 0, mundo: str = "") -> list[dict[str, Any]]:
        desc = None if dir not in ("asc", "desc") else (dir == "desc")
        _, ids = _corridas_del_mundo(duenio(request), mundo)
        filas = db.list_banco(
            corrida_id=corrida or None, orden=orden, desc=desc,
            limite=max(1, min(limite, _PAGINA_BANCO)), desde=max(0, desde),
            user_id=duenio(request), corrida_ids=ids)

        # HASTA DÓNDE LLEGA CADA UNA, en la lista y no después de guardarla.
        #
        # Una corrida deja cien candidatas y de esas unas pocas tienen
        # evidencia fuera de muestra suficiente para operar con plata. Sin
        # esto hay que guardarlas de a una para enterarse, que es justo el
        # trabajo que la cantera existe para evitar.
        from botiquant import azar, cantera

        # CUANTO DE ESTO PUEDE SER HABER BUSCADO MUCHO.
        #
        # La dispersion se calcula sobre las candidatas de LA MISMA corrida,
        # que es la comparacion que corresponde: el umbral del azar depende de
        # cuantas veces se probo en esa busqueda, no en todas las del historial.
        #
        # Y sale de las que sobrevivieron el filtro, que son parecidas entre
        # si: eso SUBESTIMA la dispersion y por lo tanto el umbral. Va marcado
        # en la respuesta para que no se lea como un numero exacto.
        # La dispersion sale de la CORRIDA ENTERA y no de esta pagina.
        #
        # Calculada sobre lo que toco venir en la respuesta, el umbral cambia
        # con la paginacion: medido, cuatro filas de la corrida de BTCUSDT
        # daban 2,00 y las cien daban 1,56. Un numero que depende de cuantas
        # filas pediste no significa nada.
        por_corrida: dict[str, tuple[float, float, int]] = {}
        for cid in {str(f.get("corrida_id") or "") for f in filas}:
            if not cid:
                continue
            todas = db.list_banco(corrida_id=cid, limite=_PAGINA_BANCO,
                                  user_id=duenio(request))
            sh = [float(v) for x in todas
                  if (v := (x.get("metrics") or {}).get("sharpe")) is not None]
            if len(sh) >= 2:
                media = sum(sh) / len(sh)
                var = sum((x - media) ** 2 for x in sh) / (len(sh) - 1)
                por_corrida[cid] = (media, var ** 0.5, len(sh))

        intentos_de = {c["id"]: int(c.get("tested") or 0)
                       for c in (db.list_corridas(duenio(request)) or [])}

        for f in filas:
            entrada = {"metrics": f.get("metrics"), "oos": f.get("oos")}
            r = cantera.revisar(entrada, cantera.REAL)
            f["cantera"] = {
                "real": r.pasa,
                "practica": cantera.revisar(entrada, cantera.PRACTICA).pasa,
                "por_que_no": cantera.por_que_no(r),
            }
            cid = str(f.get("corrida_id") or "")
            if cid in por_corrida and intentos_de.get(cid, 0) >= 2:
                media, desvio, muestra = por_corrida[cid]
                f["azar"] = azar.contexto(
                    (f.get("metrics") or {}).get("sharpe"),
                    media_sr=media, desvio_sr=desvio,
                    intentos=intentos_de[cid], muestra=muestra)
        return filas

    @app.delete("/api/corridas/{cid}")
    def borrar_corrida(request: Request, cid: str) -> dict[str, int]:
        return {"borradas": db.borrar_corrida(cid, duenio(request))}

    @app.post("/api/banco/borrar")
    def borrar_del_banco(request: Request, payload: dict[str, Any]) -> dict[str, int]:
        ids = [str(x) for x in (payload.get("ids") or [])]
        return {"borradas": db.borrar_banco(ids, duenio(request))}

    @app.post("/api/strategies/{sid}/estado")
    def mover_estado(sid: str, payload: dict[str, Any],
                     request: Request) -> dict[str, Any]:
        """Mueve una estrategia por el camino, o la retira.

        La regla que importa esta en `botiquant.estados` y no acá: no se puede
        saltear un paso, y del cementerio se vuelve al PRINCIPIO. Reactivar en
        produccion algo retirado "porque venia teniendo mala suerte" es el
        movimiento con el que se pierde plata.
        """
        from botiquant import estados

        dueno = duenio(request)
        try:
            actual = estados.normalizar(db.get_strategy(sid, dueno).get("estado"))
        except KeyError as exc:
            raise HTTPException(404, "Esa estrategia ya no está.") from exc

        try:
            cambio = estados.mover(actual, str(payload.get("estado") or ""),
                                   motivo=str(payload.get("motivo") or ""))
        except estados.EstadoError as exc:
            raise HTTPException(409, str(exc)) from exc

        db.mover_estado(sid, cambio, dueno)
        return {"id": sid, "estado": cambio["estado"],
                "siguiente": estados.siguiente(cambio["estado"]),
                "retiro": cambio.get("retiro")}

    @app.post("/api/strategies/{sid}/validar")
    def validar_estrategia(sid: str, payload: dict[str, Any],
                           request: Request) -> dict[str, Any]:
        """Le corre las pruebas de robustez y la mueve a `validada`.

        ES UN PASO DEL CAMINO, no un botón suelto. La diferencia importa: un
        botón que hay que apretar es un paso que en un sistema automático no
        ocurre nunca. Acá el ciclo puede llamarlo solo sobre todo lo que esté
        en `nueva`.

        QUE SIGNIFICA "VALIDADA": que se le corrieron las pruebas y quedaron
        registradas. NO que las pasó — eso lo decide la cantera, que es otra
        cosa y mira otras métricas. Confundirlas haría que "validada" sonara a
        aprobación y alguien la encendiera por eso.

        Monte Carlo reordena las mismas operaciones mil veces. Contesta algo
        que el backtest no puede: la caída histórica es UNA realización, y acá
        se ve cuánto llegó a caer en el 95% de los ordenamientos. Medido sobre
        las de BTCUSDT, esa cifra fue entre 1,3 y 3,9 veces la histórica.
        """
        from botiquant import estados

        dueno = duenio(request)
        try:
            fila = db.get_strategy(sid, dueno)
        except KeyError as exc:
            raise HTTPException(404, "Esa estrategia ya no está.") from exc

        actual = estados.normalizar(fila.get("estado"))
        meta = fila.get("meta") or {}
        if not meta.get("dataset_id"):
            raise HTTPException(
                422, "No sabemos con qué instrumento se encontró, así que no "
                     "se le puede volver a correr el backtest.")

        medido = meta.get("measured_range") or {}
        ajustes = {"initial_capital": meta.get("capital"),
                   "spread": meta.get("spread"), "slippage": meta.get("slippage"),
                   "commission_pct": meta.get("commission")}
        ajustes = {k: v for k, v in ajustes.items() if v is not None}

        df = _load_df({"dataset_id": meta["dataset_id"],
                       "timeframe": meta.get("timeframe") or "1h",
                       **({"date_from": medido["from"], "date_to": medido["to"]}
                          if medido.get("from") else {})})
        res = run_backtest(df, StrategySpec.from_dict(fila["spec"]),
                           _settings({"dataset_id": meta["dataset_id"],
                                      "settings": ajustes}))
        crudo = res.to_dict()
        mc = monte_carlo(
            [t["pnl"] for t in crudo.get("trades", [])],
            initial_capital=float(ajustes.get("initial_capital") or 10_000.0),
            simulations=int(min(max(int(payload.get("simulations", 1000)), 100), 5000)),
            seed=int(payload.get("seed", 42)))

        dd_hist = float(crudo["metrics"].get("max_drawdown_pct") or 0.0)
        dd_p95 = float(mc["max_drawdown_pct"]["p95"])
        validacion = {
            "cuando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "operaciones": mc["trades_per_sim"],
            "dd_historica_pct": round(dd_hist, 2),
            "dd_p95_pct": round(dd_p95, 2),
            # Cuánto peor puede ser el mismo conjunto de operaciones en otro
            # orden. Es el número que enseña algo: una caída histórica baja
            # con un múltiplo alto significa que tuvo suerte con la secuencia.
            "cuanto_peor": round(dd_p95 / dd_hist, 2) if dd_hist > 1e-9 else None,
            "peor_razonable": mc["final_equity"]["ci_90"][0],
            "prob_perder_pct": mc["final_equity"]["prob_loss"],
        }
        # Y LA PRUEBA FUERA DE MUESTRA, que es la que dice si aguanta.
        #
        # ==================================================================
        # PASÓ DE VERDAD: el ciclo validó con Monte Carlo solo, promovió por
        # las métricas del minado, y una estrategia de ADA quedó operando en
        # demo con veredicto "sobreajustada" —un tramo ganador de cuatro,
        # −15 % fuera de muestra— que recién apareció cuando alguien apretó
        # "ponerla a prueba" a mano. Monte Carlo reordena las operaciones que
        # ya hubo; el walk-forward pregunta si las habría sobre datos que
        # nunca vio. Sin la segunda, "validada" no decía nada del futuro.
        # ==================================================================
        #
        # Se registra igual que la prueba manual —mismas claves— para que la
        # pantalla y el ciclo lean una sola cosa. Si la prueba no se puede
        # correr (pocas operaciones, histórico corto) se anota y no se frena
        # la validación: el ciclo decide con lo que hay.
        try:
            wf = walk_forward(
                df, StrategySpec.from_dict(fila["spec"]),
                folds=int(PRUEBA["folds"]), train_pct=float(PRUEBA["train_pct"]),
                optimize_budget=int(PRUEBA["budget"]),
                settings=_settings({"dataset_id": meta["dataset_id"],
                                    "settings": ajustes}))
            resumen = wf["summary"]
            validacion.update({
                "estado": ESTADOS.get(resumen["verdict"], "no_paso"),
                "veredicto": resumen["verdict"],
                "tramos": resumen["folds"],
                "tramos_ganadores": resumen["profitable_folds"],
                "eficiencia": resumen["wf_efficiency"],
                "consistencia_pct": resumen["consistency_pct"],
                "retorno_fuera_pct": resumen["total_oos_return_pct"],
                "probada": validacion["cuando"],
                # El período probado, como lo guarda la prueba manual: sin
                # esto la ficha decía "Probada sobre — → —" para todo lo que
                # validó el ciclo.
                "periodo": {"from": str(df.index[0])[:10], "to": str(df.index[-1])[:10]},
                "mc": _resumen_mc(mc),
                "detalle": _detalle_prueba(wf, mc),
            })
        except Exception as exc:                            # noqa: BLE001
            validacion["prueba_error"] = str(exc)[:200]
        db.guardar_validacion(sid, validacion, dueno)

        movida = False
        if actual == estados.NUEVA:
            db.mover_estado(sid, estados.mover(actual, estados.VALIDADA), dueno)
            movida = True
        return {"id": sid, "validacion": validacion,
                "estado": estados.VALIDADA if movida else actual}

    @app.get("/api/estrategias/resumen")
    def resumen_estados(request: Request) -> dict[str, Any]:
        """Cuántas hay en cada punto del camino.

        Lo pide el ciclo automático tanto como la pantalla: para saber si hay
        algo que validar o que retirar hay que poder contar sin traerse las
        estrategias enteras.
        """
        from botiquant import estados
        return {"por_estado": estados.resumen(db.list_strategies(duenio(request))),
                "orden": estados.ORDEN, "cementerio": estados.RETIRADA}

    def _guardar_filas_del_banco(filas: list[dict[str, Any]],
                                 dueno: str | None) -> list[dict[str, Any]]:
        """Copia filas del banco a Mis estrategias, como nuevas.

        Es UNA sola función para el botón y para el ciclo. Hasta acá sólo
        existía el botón: el ciclo minaba, archivaba la corrida en el banco y
        ahí se quedaba — nada la pasaba a Mis estrategias, así que el ciclo
        sólo llegaba a validar y promover lo que una persona guardó a mano.
        Un "sistema interminable" que no se alimenta de lo que encuentra.
        """
        guardadas: list[dict[str, Any]] = []
        for f in filas:
            fila, ctx = f["fila"], f["contexto"]
            ajustes = ctx.get("settings") or {}
            riesgo = ctx.get("risk") or {}
            por_lotes = riesgo.get("size_mode") == "fixed_units"
            meta = {
                "dataset_id": f["dataset_id"] or "", "dataset_name": f["dataset_name"] or "",
                "timeframe": f["timeframe"] or "", "direction": ctx.get("direction", "both"),
                "spread": ajustes.get("spread"), "slippage": ajustes.get("slippage"),
                "commission": ajustes.get("commission_pct"),
                "capital": ajustes.get("initial_capital"),
                "sizing": "lots" if por_lotes else "risk",
                "riskPct": None if por_lotes else riesgo.get("size_value"),
                "lots": riesgo.get("size_value") if por_lotes else None,
                "rr": riesgo.get("reward_ratio"),
                "stop_mult": fila.get("stop_mult"), "blocks": fila.get("blocks") or "",
                "genes_label": fila.get("genes_label") or "", "score": fila.get("score"),
                "oos": fila.get("oos"), "oos_ratio": fila.get("oos_ratio"),
                "metrics": fila.get("metrics") or {},
                "measured_range": ctx.get("measured_range"),
                "corrida_id": f["corrida_id"],
                "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            # El campo de notas es del usuario y se deja vacío. Salía de
            # fábrica con "Del banco · SP500 1h" escrito en castellano, así que
            # alguien con la aplicación en inglés veía una frase en español en
            # su propia nota — y encima ese texto no decía nada que la fila no
            # dijera ya en sus columnas de mercado y temporalidad. De dónde
            # salió y cuándo viajan en `meta` (`corrida_id`, `saved_at`), que es
            # donde van los datos, y la interfaz los dibuja en su idioma.
            # EL NOMBRE LLEVA EL MERCADO: cada corrida arranca en S-001 y en
            # Probar convivían tres "S-001" (2 de septiembre). S-001-ETH dice
            # de dónde salió sin abrirla.
            nombre = _nombre_con_mercado(f["nombre"], f["dataset_name"] or "")
            sid = db.save_strategy(
                nombre, fila.get("spec") or {},
                notes="", meta=meta, user_id=dueno)
            guardadas.append({"id": sid, "name": nombre})
        return guardadas

    def _nombre_con_mercado(nombre: str, dataset_name: str) -> str:
        base = (dataset_name or "").split(" ")[0].upper()
        token = re.sub(r"(USDT|USD|BUSD|USDC)$", "", base)[:5] if base else ""
        nombre = str(nombre or "S")
        if not token or nombre.upper().endswith("-" + token):
            return nombre
        return f"{nombre}-{token}"

    @app.post("/api/banco/guardar")
    def guardar_del_banco(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        """Copia filas del banco a Mis estrategias.

        Se arma del lado del servidor porque el contexto de una fila vive en su
        corrida, no en la pantalla: guardar mirando la configuración actual le
        pegaría a una estrategia de EURUSD los costos que hoy están cargados
        para el S&P, y el backtest de mañana no se parecería en nada.
        """
        ids = [str(x) for x in (payload.get("ids") or [])]
        dueno = duenio(request)
        filas = db.get_banco(ids, dueno)
        if not filas:
            raise HTTPException(404, "Esas estrategias ya no están en el banco.")
        return {"guardadas": _guardar_filas_del_banco(filas, dueno)}

    # --------------------------------------------------------------- results
    @app.get("/api/results")
    def list_results(request: Request) -> list[dict[str, Any]]:
        return db.list_results(user_id=duenio(request))

    @app.get("/api/results/{rid}")
    def get_result(request: Request, rid: str) -> dict[str, Any]:
        try:
            return db.get_result(rid, duenio(request))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.delete("/api/results/{rid}")
    def delete_result(request: Request, rid: str) -> dict[str, str]:
        db.delete_result(rid, duenio(request))
        return {"status": "deleted"}

    # --------------------------------------------------------------- reports
    def _result_or_404(rid: str, request: Request) -> dict[str, Any]:
        try:
            return db.get_result(rid, duenio(request))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/results/{rid}/report.html")
    def report_html(request: Request, rid: str) -> HTMLResponse:
        row = _result_or_404(rid, request)
        return HTMLResponse(html_report(row["payload"], row["strategy_name"],
                                        row["dataset_name"]))

    @app.get("/api/results/{rid}/trades.csv")
    def report_trades(request: Request, rid: str) -> PlainTextResponse:
        row = _result_or_404(rid, request)
        return PlainTextResponse(trades_csv(row["payload"]), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="trades_{rid}.csv"'})

    @app.get("/api/results/{rid}/metrics.csv")
    def report_metrics(request: Request, rid: str) -> PlainTextResponse:
        row = _result_or_404(rid, request)
        return PlainTextResponse(metrics_csv(row["payload"]), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="metrics_{rid}.csv"'})

    @app.get("/api/results/{rid}/report.xlsx")
    def report_excel(request: Request, rid: str) -> Response:
        row = _result_or_404(rid, request)
        data = excel_report(row["payload"], row["strategy_name"])
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="report_{rid}.xlsx"'})

    def _offset_broker(payload: dict[str, Any],
                       dueno: str | None = None) -> int:
        """Horas que adelanta el servidor del bróker respecto de UTC.

        MANDA EL RELOJ DEL HISTORICO, y sólo si no lo hay manda el que eligió
        el usuario en la pantalla. El orden importa: el EA tiene que operar en
        la MISMA franja horaria en la que se minó la estrategia, y quien sabe
        en qué reloj están esas velas es el histórico, no un desplegable.

        Los datos de MetaTrader traen el reloj medido de su servidor —el de
        MetaQuotes-Demo va en UTC+3—; los de Dukascopy no traen ninguno, y ahí
        la elección del usuario es lo único que hay.

        Un desfase equivocado no falla en ningún lado: la estrategia se minó
        entre las 7 y las 16 de un reloj y el robot opera entre las 7 y las 16
        de otro. Los números no se parecen y nadie sabe por qué.

        Se acota a ±14 porque no existe ninguna zona fuera de ese rango.
        """
        del_historico = None
        ds_id = payload.get("dataset_id")
        if ds_id:
            try:
                ds = store.db.get_dataset(str(ds_id), dueno)
                del_historico = ds.get("utc_offset")
            except (KeyError, AttributeError):
                del_historico = None

        crudo = del_historico if del_historico is not None else             payload.get("server_utc_offset")
        try:
            return max(-14, min(14, int(round(float(crudo)))))
        except (TypeError, ValueError):
            return 0

    #: Lo unico que se acepta en el nombre de un archivo exportado.
    #: Se sanea porque el nombre llega en el payload y despues se usa para
    #: construir una ruta: `carpeta / nombre`. Con "C:/Windows/Temp/x" la ruta
    #: absoluta reemplaza la carpeta entera, y con "../../.." se sale de ella.
    #: Medido: ambos escribian fuera de ~/Downloads/Botiquant.
    _NOMBRE_OK = re.compile(r"[^A-Za-z0-9_.\-]")

    def _nombre_de_archivo(crudo: str, porDefecto: str) -> str:
        """Un nombre de archivo seguro, sin partes de ruta.

        Se queda con el ultimo tramo —lo que iria despues de la ultima barra—
        y reemplaza todo lo que no sea letra, digito, guion, guion bajo o punto.
        Los puntos iniciales se van para que no salga un ".." ni un archivo
        oculto.
        """
        base = str(crudo or "").replace("\\", "/").rsplit("/", 1)[-1]
        base = _NOMBRE_OK.sub("_", base).lstrip(".").strip("_")
        return (base or porDefecto)[:80]

    def _codigo_exportado(formato: str, payload: dict[str, Any],
                          request: Request) -> tuple[str, str]:
        """Renderiza la estrategia y devuelve (código, nombre de archivo).

        Lo comparten la descarga por el navegador y el guardado en disco: son
        dos formas de entregar exactamente el mismo texto, y duplicar el
        renderizado garantizaba que un día dieran archivos distintos.
        """
        _exigir_para_descargar(request)
        spec = _spec(payload)
        ds_name = ""
        if payload.get("dataset_id"):
            try:
                ds_name = db.get_dataset(payload["dataset_id"], duenio(request))["name"]
            except KeyError:
                ds_name = ""
        tf = str(payload.get("timeframe") or "")
        metricas = payload.get("metrics") or None
        if formato == "bingx":
            # El unico export que no es codigo sino una descripcion, porque del
            # otro lado no hay una plataforma que lea estrategias sino una API
            # que recibe ordenes. Quien ejecuta es un programa nuestro.
            name = _nombre_de_archivo(payload.get("name"), "BQ_Bot")
            ds = None
            if payload.get("dataset_id"):
                try:
                    ds = db.get_dataset(payload["dataset_id"], duenio(request))
                except KeyError:
                    ds = None
            # El dataset se llama "BTCUSDT M1"; el simbolo es el primer
            # tramo. Se saca de ahi y no del catalogo porque un dataset
            # importado a mano no esta en el catalogo y tiene que exportar
            # igual — que despues el exchange diga que no conoce el simbolo.
            simbolo = (ds_name or "").split()[0] if ds_name else ""
            if not simbolo:
                # Un archivo sin simbolo es un archivo que el runner va a
                # rechazar. Mejor negarse aca, donde el usuario esta mirando,
                # que entregarle algo que falla recien al querer operarlo.
                raise HTTPException(
                    400, "Elegí el instrumento antes de exportar el bot: el "
                         "archivo tiene que decir en qué símbolo operar.")
            # Los costos se COPIAN CAMPO POR CAMPO y no en bloque. `settings`
            # llega del cliente, y volcarlo entero mete en el archivo cualquier
            # cosa que venga adentro. El archivo de enlace se manda por mail y
            # se pega en foros: lo que entra aca se hace publico.
            _COSTOS = ("spread", "slippage", "commission_pct", "slippage_pct",
                       "swap_anual", "initial_capital")
            crudo = payload.get("settings") or {}
            costos = {k: crudo[k] for k in _COSTOS if k in crudo}
            code = export_bingx(
                spec, name=str(payload.get("name") or "BQ Bot"),
                symbol_source=simbolo, timeframe=tf,
                metrics=metricas, costs=costos,
                measured_from=str((ds or {}).get("start") or ""),
                measured_to=str((ds or {}).get("end") or ""),
                oos=payload.get("oos"))
            return code, f"{name}.bqbot"
        if formato == "pine":
            # el nombre VISIBLE dentro del script puede llevar espacios; el del
            # archivo no puede llevar nada que forme una ruta
            name = str(payload.get("name") or "QF Strategy")
            # UN PERPETUO NECESITA OTRO DIMENSIONAMIENTO. El piso de un
            # contrato que protege a los indices es catastrofico en cripto: un
            # contrato de BTC son ochenta mil dolares, y una cuenta de mil
            # pesos no puede abrirlo. Ademas, en cripto este Pine no es un
            # borrador para mirar sino lo que va a operar por webhook, asi que
            # el tamano minado se usa siempre y no detras de un interruptor.
            ds_pine = None
            if payload.get("dataset_id"):
                try:
                    ds_pine = db.get_dataset(payload["dataset_id"], duenio(request))
                except KeyError:
                    ds_pine = None
            fraccionable = (ds_pine or {}).get("source") == "binance"
            minimo = 0.0
            if fraccionable:
                # El minimo real del contrato, cuando el catalogo lo sabe. Si
                # no, cero: mejor sin piso que con un piso inventado.
                simbolo = (ds_name or "").split()[0] if ds_name else ""
                minimo = float(MINIMOS_PERPETUO.get(simbolo.upper(), 0.0))
            # La comision con la que se MIDIO viaja al script. Sin esto el
            # Strategy Tester de TradingView mostraba la estrategia mas
            # rentable que el backtest, y una divergencia que favorece no la
            # investiga nadie: se descubre operando.
            comision = float((payload.get("settings") or {}).get("commission_pct") or 0.0)
            code = export_pine(spec, name=name, symbol_hint=ds_name,
                               timeframe_hint=tf, metrics=metricas,
                               fraccionable=fraccionable, minimo=minimo,
                               comision_pct=comision,
                               desde=str((ds_pine or {}).get("start") or ""),
                               hasta=str((ds_pine or {}).get("end") or ""))
            return code, _nombre_de_archivo(name, "QF_Strategy") + ".pine"
        name = _nombre_de_archivo(payload.get("name"), "BQ_Strategy")
        code = export_mql5(spec, ea_name=name, symbol_hint=ds_name,
                           timeframe_hint=tf, metrics=metricas,
                              server_utc_offset=_offset_broker(payload,
                                                                duenio(request)))
        return code, f"{name}.mq5"

    @app.post("/api/export/mql5")
    def export_mql5_endpoint(payload: dict[str, Any], request: Request) -> PlainTextResponse:
        """Render a mined strategy as a compilable MQL5 Expert Advisor.

        Minar y mirar resultados es libre; bajarse el archivo pide cuenta. Es
        el momento en que el usuario se lleva algo, y el unico donde la
        friccion del registro se justifica."""
        code, archivo = _codigo_exportado("mql5", payload, request)
        return PlainTextResponse(code, media_type="text/plain",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="{archivo}"'})

    @app.post("/api/export/bingx")
    def export_bingx_endpoint(payload: dict[str, Any],
                              request: Request) -> PlainTextResponse:
        """El archivo que enlaza una estrategia con BingX.

        No lleva la clave de API del usuario ni puede llevarla: describe QUÉ
        operar, no con qué cuenta. Hay una prueba que se pone roja si alguna
        vez aparece una credencial acá adentro."""
        code, archivo = _codigo_exportado("bingx", payload, request)
        return PlainTextResponse(code, media_type="application/json",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="{archivo}"'})

    @app.post("/api/export/bingx/objeto")
    def export_bingx_objeto(payload: dict[str, Any],
                            request: Request) -> dict[str, Any]:
        """El mismo archivo de enlace, pero como objeto y sin bajar nada.

        Lo usa el botón de encender: para arrancar un bot desde la aplicación
        no tiene sentido escribir un archivo en Descargas y volver a leerlo.
        Es el MISMO renderizado —no una segunda versión que un día diverja—
        así que lo que se enciende es exactamente lo que se exportaría.
        """
        import json as _json
        code, _ = _codigo_exportado("bingx", payload, request)
        return _json.loads(code)

    @app.post("/api/export/pine")
    def export_pine_endpoint(payload: dict[str, Any], request: Request) -> PlainTextResponse:
        """Render a mined strategy as a TradingView Pine Script v5 strategy."""
        code, archivo = _codigo_exportado("pine", payload, request)
        return PlainTextResponse(code, media_type="text/plain",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="{archivo}"'})

    @app.post("/api/export/portafolio")
    def export_portafolio(payload: dict[str, Any],
                          request: Request) -> dict[str, Any]:
        """Baja un CONJUNTO de EA que van a convivir en una cuenta.

        No es exportar cinco veces de a uno con menos clics: el reparto del
        capital, la concentracion y el riesgo combinado solo existen mirando el
        conjunto, y exportando de a uno nadie los mira nunca.

        Cada EA sale con SU PORCION ya adentro. Con cinco archivos exportados
        por separado, cada uno se cree dueno del 100% de la cuenta y entre
        todos arriesgan cinco veces lo que se pidio — y el aviso de riesgo de
        cada uno dice que esta bien, porque contra su propio numero lo esta.
        """
        _exigir_para_descargar(request)
        from botiquant.reports import portafolio as port

        ids = [str(x) for x in (payload.get("ids") or [])]
        if not ids:
            raise HTTPException(400, "Elegí al menos una estrategia.")
        if len(ids) > 20:
            raise HTTPException(
                400, "Veinte es el máximo por conjunto. Con más, las porciones "
                     "quedan tan chicas que el lote mínimo del bróker manda "
                     "sobre lo que la estrategia quiere arriesgar.")

        dueno = duenio(request)
        filas = []
        for sid in ids:
            try:
                filas.append(db.get_strategy(sid, dueno))
            except KeyError:
                raise HTTPException(404, f"La estrategia {sid} ya no está.")

        # ANTES DE REPARTIR NADA: si el conjunto mezcla un CFD con un
        # perpetuo, no es un conjunto. Ver `MundosMezclados`.
        try:
            port.exigir_un_solo_mundo(filas)
        except port.MundosMezclados as exc:
            raise HTTPException(400, str(exc)) from exc

        reparto = port.repartir(
            filas, usar_pct=float(payload.get("usar_pct") or 90.0))

        carpeta = carpeta_de_estrategias()
        carpeta.mkdir(parents=True, exist_ok=True)
        # NOMBRES ÚNICOS DENTRO DEL CONJUNTO, y no es cosmético.
        #
        # Dos estrategias guardadas pueden llamarse igual —guardar dos veces la
        # misma desde el banco alcanza— y el nombre decide DOS cosas: el
        # archivo y el Magic Number. Con el nombre repetido:
        #
        #   · el segundo archivo pisa al primero, así que el conjunto sale con
        #     menos robots de los que dice. Visto: tres estrategias, el aviso
        #     decía "3 robots guardados" y en el disco había dos. El reparto ya
        #     había calculado 30% para cada uno de tres, o sea que la cuenta
        #     quedaba operando al 60% en vez del 90%.
        #   · y si no se pisaran, compartirían Magic Number, que es peor: dos
        #     EA con el mismo número creen cada uno que las posiciones del otro
        #     son suyas. Uno cierra lo que el otro abrió y ninguno da error.
        #
        # QUIÉN SE QUEDA CON EL NOMBRE LIMPIO NO PUEDE DEPENDER DEL ORDEN EN
        # QUE SE TILDARON. Se lo queda el de id más chico, que es el mismo
        # siempre; los demás llevan un sufijo con su propio id.
        #
        # La primera versión le dejaba el nombre limpio al primero de la lista,
        # y eso hacía que reexportar el mismo conjunto en otro orden cambiara
        # los Magic Number — con lo cual el EA nuevo no reconocería la posición
        # que dejó abierta el anterior. Lo encontró la prueba, después de que
        # el comentario de acá afirmara que no pasaba.
        repetidos: dict[str, list[str]] = {}
        for f in filas:
            repetidos.setdefault(str(f["name"]), []).append(str(f["id"]))

        nombres: dict[str, str] = {}
        for base, unos in repetidos.items():
            dueno_del_nombre = min(unos)
            for sid in unos:
                nombres[sid] = (base if sid == dueno_del_nombre
                                else f"{base}_{sid[:4]}")

        escritos = []
        for f in filas:
            meta = f.get("meta") or {}
            propio = nombres[str(f["id"])]
            nombre = _nombre_de_archivo(f"BQ_{propio}", "BQ_Strategy")
            codigo = export_mql5(
                StrategySpec.from_dict(f["spec"]), ea_name=nombre,
                symbol_hint=meta.get("dataset_name") or "",
                timeframe_hint=meta.get("timeframe") or "",
                metrics=meta.get("metrics"),
                # CADA EA LEE EL RELOJ DE SU PROPIO HISTORICO. Un portafolio
                # puede mezclar instrumentos bajados de fuentes distintas, y un
                # solo desfase para todos dejaría a algunos operando en otra
                # franja que la que se minó.
                server_utc_offset=_offset_broker(
                    {**payload, "dataset_id": meta.get("dataset_id")}, dueno),
                porcion=reparto.porciones[str(f["id"])])
            destino = carpeta / f"{nombre}.mq5"
            destino.write_text(codigo, encoding="utf-8")
            escritos.append({"nombre": propio, "archivo": destino.name,
                             "porcion_pct": reparto.porciones[str(f["id"])]})

        return {"carpeta": str(carpeta), "archivos": escritos,
                **port.resumen(filas, reparto)}

    @app.post("/api/export/{formato}/archivo")
    def export_a_disco(formato: str, payload: dict[str, Any],
                       request: Request) -> dict[str, Any]:
        """Escribe la estrategia en el disco del usuario y dice dónde quedó.

        Este es el camino bueno en el escritorio, y no por gusto: la ventana
        nativa CANCELA las descargas del navegador, así que el botón de bajar
        no hacía absolutamente nada — ni archivo, ni error, ni aviso.

        Pero además es mejor que una descarga aunque funcionara. El servidor
        corre en la máquina del usuario: puede escribir el archivo directamente
        en una carpeta fija, sin diálogo de por medio, y decir la ruta exacta.
        Un .mq5 hay que ir a buscarlo con MetaEditor, así que saber dónde está
        es la mitad del trabajo.
        """
        if formato not in ("mql5", "pine", "bingx"):
            raise HTTPException(404, "Formato desconocido.")
        code, archivo = _codigo_exportado(formato, payload, request)

        # Un .mq5 puede ir directo a la carpeta de robots de MetaTrader. Ahí
        # aparece en el Navegador y compila donde el Probador lo encuentra;
        # compilado desde Descargas, el .ex5 queda al lado del .mq5 y el
        # terminal no lo ve nunca. Ver botiquant/metatrader.py.
        terminal = str(payload.get("terminal") or "").strip()
        carpeta, donde = carpeta_de_estrategias(), ""
        if terminal and formato == "mql5":
            experts = experts_de(terminal)
            if experts is None:
                raise HTTPException(404, "Ese MetaTrader ya no está en esta máquina.")
            carpeta = experts
            donde = next((t["nombre"] for t in terminales() if t["id"] == terminal), "")

        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = (carpeta / archivo).resolve()
            # Segunda capa, por si el saneo del nombre cambia alguna vez: se
            # comprueba que el destino REAL caiga dentro de la carpeta pedida.
            # Un saneo se puede aflojar sin querer al agregar un caracter a la
            # lista; esta comprobacion no depende de esa lista.
            if not destino.is_relative_to(carpeta.resolve()):
                raise HTTPException(400, "Nombre de archivo inválido.")
            destino.write_text(code, encoding="utf-8")
        except OSError as exc:
            # disco lleno, permisos, ruta redirigida a OneDrive sin conexión…
            raise HTTPException(
                500, f"No se pudo escribir en {carpeta}: {exc.strerror or exc}") from exc
        return {"ruta": str(destino), "carpeta": str(carpeta), "archivo": archivo,
                "terminal": donde}

    @app.get("/api/metatrader")
    def listar_metatrader() -> dict[str, Any]:
        """Los MetaTrader 5 de ESTA máquina. Sólo tiene sentido en el escritorio."""
        if MULTIUSER:
            return {"terminales": []}
        return {"terminales": [{"id": t["id"], "nombre": t["nombre"],
                                "experts": t["experts"]} for t in terminales()]}

    def _carpetas_permitidas() -> list[Path]:
        """Las únicas carpetas cuyos archivos esta aplicación acepta abrir."""
        permitidas = [carpeta_de_estrategias()]
        permitidas.extend(Path(t["experts"]) for t in terminales())
        return permitidas

    @app.post("/api/abrir-archivo")
    def abrir_archivo(payload: dict[str, Any]) -> dict[str, str]:
        """Abre el archivo con el programa que le corresponda en el sistema.

        Que es lo que el usuario quiere: un .mq5 abre MetaEditor, listo para
        compilar con F7. No hay que saber dónde quedó ni ir a buscarlo.

        Abrir un archivo por su asociación es, literalmente, ejecutar lo que el
        sistema tenga configurado para esa extensión. Así que se comprueban dos
        cosas y no una: que la extensión sea de las nuestras, y que el archivo
        esté DENTRO de una carpeta nuestra. Con sólo lo primero, un .mq5 puesto
        en cualquier lado por otro programa sería un destino válido.
        """
        if MULTIUSER:
            raise HTTPException(404, "No disponible.")
        try:
            ruta = Path(str(payload.get("ruta") or "")).resolve()
        except (OSError, ValueError) as exc:
            raise HTTPException(400, "Ruta inválida.") from exc
        if ruta.suffix.lower() not in (".mq5", ".pine", ".bqbot"):
            raise HTTPException(400, "Sólo se abren estrategias exportadas.")
        if not any(ruta.is_relative_to(c.resolve()) for c in _carpetas_permitidas()
                   if c.exists()):
            raise HTTPException(403, "Ese archivo no lo exportó Botiquant.")
        if not ruta.is_file():
            raise HTTPException(404, "El archivo ya no está ahí.")
        try:
            if sys.platform == "win32":
                os.startfile(ruta)                        # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(ruta)])
            else:
                subprocess.Popen(["xdg-open", str(ruta)])
        except OSError as exc:
            raise HTTPException(500, f"No se pudo abrir: {exc}") from exc
        return {"ruta": str(ruta)}

    # ------------------------------------------------------------- exchanges
    #
    # SOLO EN EL ESCRITORIO. En un servidor compartido, guardar las claves de
    # trading de otras personas es un problema completamente distinto —custodia
    # de credenciales ajenas— y no es lo que esta aplicacion hace. Con
    # BQ_MULTIUSER=1 estos endpoints no existen.

    def _solo_escritorio() -> None:
        if MULTIUSER:
            raise HTTPException(
                404, "Las claves de exchange sólo se configuran en la "
                     "aplicación de escritorio.")

    @app.get("/api/exchanges")
    def exchanges_listar() -> list[dict[str, Any]]:
        """Qué claves hay cargadas. NUNCA devuelve un secreto."""
        _solo_escritorio()
        from botiquant.vivo import claves
        return claves.listar(workdir / "claves")

    @app.post("/api/exchanges/{exchange}/{entorno}")
    def exchanges_guardar(exchange: str, entorno: str,
                          payload: dict[str, Any]) -> dict[str, Any]:
        """Cifra y guarda una clave. Devuelve sólo lo que se puede mostrar."""
        _solo_escritorio()
        from botiquant.vivo import claves
        try:
            return claves.guardar(
                workdir / "claves", exchange, entorno,
                api_key=str(payload.get("api_key") or ""),
                secret=str(payload.get("secret") or ""))
        except claves.ClaveError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/exchanges/{exchange}/{entorno}")
    def exchanges_borrar(exchange: str, entorno: str) -> dict[str, Any]:
        _solo_escritorio()
        from botiquant.vivo import claves
        try:
            return {"borrada": claves.borrar(workdir / "claves", exchange, entorno)}
        except claves.ClaveError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/exchanges/{exchange}/{entorno}/comprobar")
    def exchanges_comprobar(exchange: str, entorno: str) -> dict[str, Any]:
        """Prueba la conexión de menos a más riesgo. NO manda ninguna orden.

        Los dos primeros pasos no usan la clave, así que si fallan el problema
        no es de credenciales: es de red o de región. Distinguirlo acá ahorra
        media hora de revisar una clave que estaba bien.
        """
        _solo_escritorio()
        from botiquant.data import bingx
        from botiquant.vivo import claves
        from botiquant.vivo.adaptador import (BASE_PRACTICA, BASE_REAL,
                                              Binance, BingX)

        pasos: list[dict[str, Any]] = []

        def paso(nombre: str, fn) -> bool:
            try:
                pasos.append({"paso": nombre, "ok": True, "detalle": fn()})
                return True
            except bingx.BingXError as exc:
                # El rechazo del exchange, sin envolverlo en una frase nuestra:
                # su texto viene en inglés siempre y la interfaz está en dos
                # idiomas, así que una frase en español alrededor queda mal en
                # los dos. El código es lo que se busca cuando hay que
                # preguntarle a alguien.
                pasos.append({"paso": nombre, "ok": False,
                              "detalle": exc.del_exchange})
                return False
            except Exception as exc:                       # noqa: BLE001
                pasos.append({"paso": nombre, "ok": False, "detalle": str(exc)})
                return False

        # EL SIMBOLO Y EL LECTOR CAMBIAN SEGUN EL EXCHANGE. BingX pide el
        # guion —BTC-USDT— y Binance lo rechaza; es el error mas comun al
        # cambiar de casa, y aca se elige bien de entrada en vez de dejar que
        # el exchange conteste algo que suena a "el simbolo no existe".
        es_binance = exchange == "binance"
        simbolo = "BTCUSDT" if es_binance else "BTC-USDT"
        base = BASE_REAL if entorno == "real" else BASE_PRACTICA
        lector = Binance("", "") if es_binance else BingX("", "", base=base)

        if not paso("responde", lambda: f"{len(lector.velas(simbolo, '1h', 2))} velas"):
            return {"pasos": pasos, "listo": False}

        try:
            api_key, secret = claves.leer(workdir / "claves", exchange, entorno)
        except claves.ClaveError as exc:
            pasos.append({"paso": "clave", "ok": False, "detalle": str(exc)})
            return {"pasos": pasos, "listo": False}

        cliente = (Binance(api_key, secret) if es_binance
                   else BingX(api_key, secret, base=base))
        if not paso("saldo", lambda: f"{cliente.capital():,.2f} disponible"):
            return {"pasos": pasos, "listo": False}
        paso("modo", lambda: (cliente.modo() if es_binance else
                              ("cobertura" if cliente.cobertura() else "simple")))
        # TODAS LAS POSICIONES DE LA CUENTA, no sólo la del símbolo de prueba:
        # decía "ninguna abierta" con un corto de ETH abierto, porque miraba
        # BTCUSDT. En BingX el adaptador sólo sabe preguntar por símbolo.
        def _abiertas() -> str:
            if es_binance:
                from botiquant.data import binance_trade as bt
                n = len(bt.posiciones(api_key, secret, base=bt.BASE_PRUEBA))
                return "ninguna abierta" if n == 0 else f"{n} abiertas"
            return "hay una abierta" if cliente.posicion(simbolo).abierta else "ninguna abierta"
        paso("posiciones", _abiertas)

        return {"pasos": pasos, "listo": all(p["ok"] for p in pasos)}

    # ------------------------------------------------------------------- bot
    #
    # Encender un bot es la unica accion de toda la aplicacion que puede mover
    # plata, asi que todo lo de esta seccion es explicito: el modo se manda, el
    # entorno se manda, y ninguno tiene un default que opere.

    # ------------------------------------------------------------ el ciclo
    #
    # SOLO EN EL ESCRITORIO, igual que el bot. Un ciclo que mina, promueve y
    # opera solo, corriendo en un servidor compartido, seria operar la cuenta
    # de otra persona sin que este mirando.

    def _leer_para_el_ciclo() -> dict[str, Any]:
        """Lo que el ciclo necesita para decidir, y nada mas.

        Se arma aca y no en el orquestador para que aquel se pueda probar sin
        base de datos: se le pasan funciones y se comprueba a cuales llamo.
        """
        from botiquant import cantera, estados as est
        from botiquant.vivo import semaforo
        from botiquant.vivo.piloto import PILOTO

        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

        def _vueltas(f: dict[str, Any]) -> int:
            """Cuantas vueltas en naranja lleva, contadas de verdad.

            ==================================================================
            ES EL CABLE QUE LE FALTABA AL RETIRO AUTOMATICO.
            ==================================================================

            La rama de retiro de `ciclo.que_toca` pregunta esto, y hasta ahora
            recibia 0 fijo, asi que no podia dispararse nunca. El mecanismo
            estaba escrito entero y no estaba conectado.

            SE CALCULA DESDE EL REGISTRO GUARDADO y no desde el bot encendido:
            asi el semaforo tambien opina sobre las que operaron ayer y hoy no
            estan corriendo, que son la mayoria cuando hay un bot a la vez.

            SOLO PARA LAS QUE OPERARON. Una estrategia que nunca se encendio no
            tiene con que compararse, y preguntarle a la base por operaciones
            que no existen en cada vuelta del ciclo es trabajo al pedo.
            """
            estado = est.normalizar(f.get("estado"))
            if estado not in (est.PRACTICA, est.PRODUCCION):
                return int((f.get("vigilancia") or {}).get("vueltas_naranja") or 0)

            ops = db.operaciones(f["id"])
            if not ops:
                return int((f.get("vigilancia") or {}).get("vueltas_naranja") or 0)

            respaldo = ((f.get("meta") or {}).get("metrics")) or {}
            v = semaforo.revisar(ops, respaldo)
            nueva = semaforo.actualizar(f.get("vigilancia"), v, cuando=ahora)
            db.guardar_vigilancia(f["id"], nueva)
            return int(nueva["vueltas_naranja"])

        def _operable(spec: Any) -> bool:
            """Si el bot la encenderia, con el criterio del bot.

            Un spec que ni siquiera se puede leer tampoco se enciende, asi
            que cuenta como no operable en vez de tirar abajo la vuelta.
            """
            from botiquant.core.models import StrategySpec
            from botiquant.vivo.runner import por_que_no_operable
            try:
                return not por_que_no_operable(StrategySpec.from_dict(spec))
            except Exception:                       # noqa: BLE001
                return False

        filas = []
        for f in db.list_strategies(None):
            meta = f.get("meta") or {}
            entrada = {"metrics": meta.get("metrics"), "oos": meta.get("oos")}
            filas.append({
                "id": f["id"], "estado": est.normalizar(f.get("estado")),
                # EL INSTRUMENTO, para el tope de concentracion. Sin esto el
                # ciclo no ve que tres candidatas son todas de Bitcoin y las
                # promueve las tres — que no es un portafolio de tres sino una
                # apuesta con tres nombres.
                "instrumento": str(meta.get("dataset_id") or ""),
                # SI EL BOT PODRIA ENCENDERLA. Promover es encender, y el
                # ciclo promovio una con trailing que el bot rechazo: quedo
                # en "practica" sin operar. Se pregunta antes, con el mismo
                # criterio que usa el bot al arrancar.
                "operable": _operable(f.get("spec")),
                # LO QUE SALIÓ "SOBREAJUSTADO" FUERA DE MUESTRA NO SE PROMUEVE,
                # aunque las métricas del minado pasen la cantera: son las
                # métricas de los datos donde se la encontró. Sin veredicto
                # (validada antes de que el ciclo corriera esta prueba) no se
                # frena: la ausencia no es un rechazo.
                "cantera": {"practica": cantera.revisar(entrada, cantera.PRACTICA).pasa
                                        and (f.get("validacion") or {}).get("veredicto") != "overfitted",
                            "real": cantera.revisar(entrada, cantera.REAL).pasa
                                    and (f.get("validacion") or {}).get("veredicto") != "overfitted"},
                # Contadas desde el registro guardado. Ver `_vueltas`.
                #
                # Que esto sea distinto de cero no significa que se retire: el
                # ciclo sale con `retirar_solo` APAGADO, y entonces dice a
                # quien sacaria sin sacarlo. Prenderlo es una decision de una
                # persona, despues de ver el semaforo cambiar de color varias
                # veces y decidir si le cree.
                "vueltas_en_naranja": _vueltas(f),
                "vigilancia": f.get("vigilancia") or {},
            })

        corridas = db.list_corridas(None) or []
        horas = 9_999.0
        if corridas:
            try:
                ultima = datetime.fromisoformat(str(corridas[0]["created"]))
                if ultima.tzinfo is None:
                    ultima = ultima.replace(tzinfo=timezone.utc)
                horas = (datetime.now(timezone.utc) - ultima).total_seconds() / 3600.0
            except (ValueError, KeyError, TypeError):
                pass

        return {"estrategias": filas, "horas_desde_minado": horas,
                # CUANTOS, no "hay o no hay": el ciclo usa este número para
                # saber si le queda lugar, y con varios bots un booleano le
                # decía que había lugar cuando ya estaban todos ocupados.
                "en_practica": PILOTO.cuantos}

    def _ds_de(ds_id: str | None) -> dict[str, Any] | None:
        if not ds_id:
            return None
        try:
            return db.get_dataset(str(ds_id), None)
        except (KeyError, sqlite3.Error):
            return None

    def _elegir_instrumento(p) -> dict[str, Any] | None:
        """Sobre cuál minar esta vuelta.

        EL QUE MENOS ESTRATEGIAS TIENE, y no uno al azar ni siempre el mismo.
        El ciclo ya evita promover tres del mismo instrumento —serían una
        apuesta con tres nombres— así que minar siempre sobre el mismo llena el
        banco de candidatas que después no va a poder promover.

        Sólo perpetuos: el ciclo enciende en Binance demo, y minar un CFD para
        dejarlo sin encender es gastar el tiempo de búsqueda en algo que
        despues necesita a una persona.
        """
        elegidos = [str(x) for x in (p.instrumentos or [])]
        candidatos = [d for d in db.list_datasets(None)
                      if d.get("source") == "binance"
                      and (not elegidos or d["id"] in elegidos)]
        if not candidatos:
            return None
        cuantas: dict[str, int] = {}
        for f in db.list_strategies(None):
            dsid = (f.get("meta") or {}).get("dataset_id")
            if dsid:
                cuantas[str(dsid)] = cuantas.get(str(dsid), 0) + 1
        candidatos.sort(key=lambda d: (cuantas.get(d["id"], 0), d["name"]))
        return candidatos[0]

    def _encender_del_ciclo(fila: dict[str, Any], meta: dict[str, Any],
                            adoptar: bool = False) -> None:
        """Pone a operar una estrategia recién promovida. Binance demo, siempre.

        LA PORCION SALE DEL TOPE DEL CICLO Y NO DE LO QUE QUEDE LIBRE. Con "lo
        que quede", el primero se llevaría casi todo y el quinto operaría con
        migajas: el reparto dependería del orden de promoción, que es azar.
        Repartir por el tope deja a los cinco iguales desde el principio.
        """
        from botiquant.vivo import claves
        from botiquant.vivo.adaptador import Binance
        from botiquant.vivo.piloto import PILOTO
        from botiquant.vivo.runner import PRACTICA, Bot

        p = _orq().params
        porcion = round(0.85 / max(int(p.max_en_practica), 1), 4)

        api_key, secret = claves.leer(workdir / "claves", "binance", "practica")
        doc = export_bingx_objeto({
            "spec": fila["spec"], "name": fila.get("name") or fila["id"],
            "dataset_id": meta.get("dataset_id"),
            "timeframe": meta.get("timeframe") or "1h",
            "settings": {"commission_pct": meta.get("commission") or 0.04},
            "metrics": meta.get("metrics"), "oos": meta.get("oos"),
        }, _PedidoLocal())
        sid = fila["id"]

        def anotar(f: dict[str, Any]) -> None:
            if f.get("accion") in ("abrir", "cerrar"):
                db.anotar_operacion(sid, f)

        PILOTO.encender(Bot(
            doc=doc, adaptador=Binance(api_key, secret), modo=PRACTICA,
            porcion=porcion, oyente=anotar, adoptar=adoptar))

    def _orq():
        """El ciclo del proceso, armado la primera vez que se lo pide."""
        from botiquant import ciclo as cic, estados as est, orquestador as orq

        if orq.ORQUESTADOR is None:
            def validar(ids):
                for sid in ids:
                    try:
                        validar_estrategia(sid, {}, _PedidoLocal())
                    except HTTPException as exc:
                        # UNA ESTRATEGIA SIN HISTORICO TRABABA EL CICLO PARA
                        # SIEMPRE. Validar fallaba, el estado seguia en
                        # "nueva", y la vuelta siguiente la elegia de nuevo:
                        # el ciclo no llegaba nunca a promover ni a minar.
                        #
                        # Pasa al borrar un instrumento desde Datos, que es una
                        # accion normal. Se retira con el motivo adentro —el
                        # cementerio existe justamente para no volver a
                        # encender lo que ya se sabe que no sirve— y el ciclo
                        # sigue con las que si se pueden probar.
                        if exc.status_code != 404:
                            raise
                        actual = est.normalizar(
                            db.get_strategy(sid, None).get("estado"))
                        db.mover_estado(sid, est.mover(
                            actual, est.RETIRADA,
                            motivo="se borró el histórico con el que se "
                                   "encontró, así que no se puede volver a "
                                   "probar"), None)

            #: Por que no arranco cada uno, para que se pueda ver.
            _fallos_encendido: list[str] = []

            def promover(ids):
                """Mueve el estado Y ENCIENDE, que es lo que faltaba.

                Mover el estado a "practica" y no encender dejaba el ciclo a
                mitad de camino: decia que habia promovido cinco y no operaba
                ninguna. El estado dice donde ESTA; encenderla es lo que la
                pone a operar, y son dos cosas distintas que aca van juntas
                porque promover significa justamente eso.

                SOLO EN BINANCE DEMO. El adaptador no tiene forma de apuntar a
                la cuenta real, asi que el ciclo no puede mover plata de verdad
                ni equivocandose. Para CFDs no enciende: MetaTrader necesita
                que una persona compile y arranque el EA.
                """
                for sid in ids:
                    fila = db.get_strategy(sid, None)
                    actual = est.normalizar(fila.get("estado"))
                    db.mover_estado(sid, est.mover(actual, est.PRACTICA), None)

                    meta = fila.get("meta") or {}
                    ds = _ds_de(meta.get("dataset_id"))
                    if not ds or ds.get("source") != "binance":
                        continue                    # un CFD lo enciende alguien
                    try:
                        _encender_del_ciclo(fila, meta)
                    except Exception as exc:        # noqa: BLE001
                        # Que uno no arranque no puede frenar al ciclo: se
                        # anota y sigue. El motivo mas comun es benigno —ya hay
                        # un bot en ese simbolo— y el ciclo lo reintenta solo
                        # en la vuelta siguiente con otra estrategia.
                        #
                        # VA AL REGISTRO DEL CICLO Y NO A UN `print`. La
                        # aplicacion de escritorio no tiene consola: un print
                        # ahi no lo lee NADIE, y el sintoma es un ciclo que
                        # dice haber promovido cinco y no tiene ninguno
                        # operando, sin ningun lugar donde mirar por que.
                        _fallos_encendido.append(
                            f"{fila.get('name') or sid}: {exc}")
                if _fallos_encendido:
                    # Se levanta DESPUES de intentar con todos: cortar en el
                    # primero dejaria a los demas sin siquiera intentarlo.
                    fallos, _fallos_encendido[:] = list(_fallos_encendido), []
                    raise RuntimeError("no arrancaron: " + " · ".join(fallos))

            def minar(_ids):
                """Busca mas estrategias, con los parametros del ciclo.

                NO LANZA DOS A LA VEZ. Una vuelta del ciclo dura un minuto y un
                minado dura varios, y el minado solo deja rastro en la base
                cuando TERMINA: sin la guarda, el ciclo veria "hace horas que
                no se mina" en cada vuelta y encolaria uno por minuto.
                """
                if jobs.hay_corriendo("mine"):
                    return
                p = _orq().params
                ds = _elegir_instrumento(p)
                if not ds:
                    return
                start_mine(_PedidoLocal(), {
                    "dataset_id": ds["id"], "timeframe": ds.get("timeframe") or "1h",
                    "max_candidates": int(p.candidatas_por_vuelta),
                    "target_keep": 5, "min_trades": 60,
                    "oos_pct": float(p.reservar_pct), "exigir_oos": True,
                    "min_pf": 1.15,
                    # SOLO LO QUE EL BOT PUEDE ENCENDER. Minar con trailing y
                    # descubrirlo al promover seria dejar al ciclo eligiendo
                    # entre estrategias que no va a poder usar.
                    "sin_trailing": True,
                    # Y QUE QUEDEN GUARDADAS: es lo que las hace visibles para
                    # la vuelta siguiente, que valida lo "nuevo".
                    "guardar_al_terminar": True,
                })

            orq.ORQUESTADOR = orq.Orquestador(
                leer_estado=_leer_para_el_ciclo,
                # RETIRAR sigue sin conectar, y es deliberado: el ciclo sale
                # con `retirar_solo` apagado, asi que dice a quien sacaria sin
                # sacarlo. Conectarlo antes de que alguien haya visto el
                # semaforo cambiar de color varias veces seria decidir por el.
                acciones={cic.VALIDAR: validar, cic.PROMOVER: promover,
                          cic.MINAR: minar})
        return orq.ORQUESTADOR

    class _PedidoLocal:
        """Un pedido de mentira para llamar a los endpoints desde adentro.

        El ciclo corre sin nadie del otro lado: no hay sesion ni cookie. En el
        escritorio el dueno es siempre el que esta sentado adelante.
        """
        cookies: dict = {}
        headers: dict = {}

    @app.get("/api/ciclo")
    def ciclo_estado() -> dict[str, Any]:
        """Que esta haciendo el ciclo y que va a hacer.

        `proxima` es lo que HARIA ahora, sin haberlo hecho: se puede mirar sin
        encender nada, que es como conviene estrenarlo.
        """
        _solo_escritorio()
        return _orq().estado()

    @app.post("/api/ciclo/params")
    def ciclo_params(payload: dict[str, Any]) -> dict[str, Any]:
        """Con que se maneja. Ver `botiquant/ciclo.py` para que hace cada uno."""
        _solo_escritorio()
        from botiquant import ciclo as cic

        o = _orq()
        o.params = cic.Parametros.from_dict(payload)
        if o.params.encendido and not o.corriendo:
            o.encender()
        elif not o.params.encendido and o.corriendo:
            o.apagar()
        return o.estado()

    @app.post("/api/ciclo/paso")
    def ciclo_paso() -> dict[str, Any]:
        """Una vuelta a mano, para verlo dar un paso sin dejarlo corriendo.

        Es como conviene estrenarlo: se mira que iba a hacer, se le pide que
        lo haga, y se comprueba que hizo lo que decia.
        """
        _solo_escritorio()
        return {"hizo": _orq().una_vuelta(a_mano=True).to_dict(),
                "estado": _orq().estado()}

    def _promovidas_sin_bot() -> list[dict[str, Any]]:
        """Las que están en práctica y no tienen bot corriendo.

        Pasa cada vez que la aplicación se cierra: los bots mueren con el
        proceso y NO se reencienden solos —nadie retoma una posición sin
        mirarla— pero la estrategia sigue en "práctica". Sin esto, la pantalla
        decía "8 en práctica" con cero operando y ningún lugar donde verlo.
        Se listan para que alguien las reencienda con un clic; sólo las de
        Binance, que son las únicas que el piloto sabe encender.
        """
        from botiquant import estados as est
        from botiquant.vivo.adaptador import a_simbolo
        from botiquant.vivo.piloto import PILOTO

        corriendo = {v.get("simbolo") for v in PILOTO.estado().get("vuelos", [])
                     if v.get("encendido")}
        fuera: list[dict[str, Any]] = []
        for f in db.list_strategies(None):
            if est.normalizar(f.get("estado")) != est.PRACTICA:
                continue
            meta = f.get("meta") or {}
            ds = _ds_de(meta.get("dataset_id"))
            if not ds or ds.get("source") != "binance":
                continue
            simbolo = a_simbolo(str(ds.get("name") or "").split()[0], con_guion=True)
            if simbolo in corriendo:
                continue
            fuera.append({"id": f["id"], "name": f.get("name") or f["id"],
                          "simbolo": simbolo})
        return fuera

    @app.get("/api/bot")
    def bot_estado() -> dict[str, Any]:
        _solo_escritorio()
        from botiquant.vivo.piloto import PILOTO
        e = PILOTO.estado()
        e["apagadas"] = _promovidas_sin_bot()
        return e

    @app.post("/api/bot/reencender")
    def bot_reencender() -> dict[str, Any]:
        """Enciende las promovidas que quedaron sin bot. Un clic, no solo.

        Reencender solo al arrancar sería retomar posiciones sin que nadie
        las mire; reencender de a una a mano es el clic de más que este
        proyecto viene evitando. Un clic para todas, con el reparto del ciclo.
        """
        _solo_escritorio()
        encendidas, fallos = [], []
        for a in _promovidas_sin_bot():
            fila = db.get_strategy(a["id"], None)
            try:
                # Reencender es una persona decidiendo después de mirar: si
                # en el símbolo hay una posición —la suya, con su stop—, el
                # bot la adopta en vez de detenerse por "posición ajena".
                _encender_del_ciclo(fila, fila.get("meta") or {}, adoptar=True)
                encendidas.append(a)
            except Exception as exc:                        # noqa: BLE001
                fallos.append({**a, "motivo": str(exc)})
        return {"encendidas": encendidas, "fallos": fallos}

    _MEMO_RENDIMIENTO: dict[str, Any] = {"cuando": 0.0, "valor": None}

    @app.get("/api/cuenta/rendimiento")
    def cuenta_rendimiento() -> dict[str, Any]:
        """Con memoria de 30 s: son cuatro pedidos al exchange (5 s) y la
        pantalla lo pide desde tres lugares al abrir Operar."""
        if _MEMO_RENDIMIENTO["valor"] is not None and time.time() - _MEMO_RENDIMIENTO["cuando"] < 30:
            return _MEMO_RENDIMIENTO["valor"]
        valor = _cuenta_rendimiento_crudo()
        _MEMO_RENDIMIENTO.update(cuando=time.time(), valor=valor)
        return valor

    def _cuenta_rendimiento_crudo() -> dict[str, Any]:
        """Lo que la CUENTA hizo, no lo que los bots recuerdan.

        ==================================================================
        SE LE PREGUNTA AL EXCHANGE. Es la misma regla que la posición: lo que
        el bot recuerda se pierde al cerrar la aplicación, no incluye lo que
        alguien haya hecho a mano desde Binance, y no sabe de comisiones.
        ==================================================================

        EL RESULTADO VA PARTIDO POR CONCEPTO y no como un solo número, porque
        un solo número esconde la única pregunta que importa: si la estrategia
        no sirve, o si sirve y los costos se la comen. Medido en esta misma
        cuenta demo: -0,049 de PNL contra -0,220 de comisiones — el costo pesó
        cuatro veces y media más que la pérdida operativa. Sumado da "pierde",
        que manda a cambiar la estrategia cuando lo que hay que cambiar es
        cuánto opera.

        Sólo demo, como todo lo de Binance en esta versión.
        """
        _solo_escritorio()
        from botiquant.data import binance_trade as bt
        from botiquant.vivo import claves

        try:
            api_key, secret = claves.leer(workdir / "claves", "binance", "practica")
        except claves.ClaveError as exc:
            raise HTTPException(400, str(exc)) from exc

        base = bt.BASE_PRUEBA
        # LOS PEDIDOS VAN A LA VEZ, no uno detras del otro. Cada uno tarda
        # alrededor de un segundo contra la demo y no dependen entre si:
        # en fila, la pantalla decia "preguntando al exchange" cinco
        # segundos; en paralelo tarda lo que el mas lento.
        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                f_saldo = pool.submit(bt.saldo, api_key, secret, base=base)
                f_abiertas = pool.submit(bt.posiciones, api_key, secret, base=base)
                f_movs = pool.submit(bt.movimientos, api_key, secret, base=base)
                saldo = f_saldo.result()
                abiertas = f_abiertas.result()
                movs = f_movs.result()
        except bt.BinanceError as exc:
            raise HTTPException(502, exc.del_exchange) from exc

        por_concepto: dict[str, float] = {}
        simbolos: set[str] = set()
        for m in movs:
            tipo = str(m.get("incomeType") or "")
            # El depósito inicial no es resultado: es el punto de partida.
            # Sumarlo haría que la cuenta parezca ganadora por haber recibido
            # su propio dinero.
            if tipo == "TRANSFER":
                continue
            por_concepto[tipo] = round(
                por_concepto.get(tipo, 0.0) + float(m.get("income") or 0.0), 8)
            if m.get("symbol"):
                simbolos.add(str(m["symbol"]))

        pnl = por_concepto.get("REALIZED_PNL", 0.0)
        comision = por_concepto.get("COMMISSION", 0.0)
        fondeo = por_concepto.get("FUNDING_FEE", 0.0)

        def _cerradas_de(sim: str) -> list[dict[str, Any]]:
            try:
                return bt.cerradas(sim, api_key, secret, limite=50, base=base)
            except bt.BinanceError:
                return []

        # Un pedido por simbolo, tambien a la vez: con seis simbolos operados
        # eran seis segundos mas de espera en fila.
        cerradas: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            for lote in pool.map(_cerradas_de, sorted(simbolos)[:6]):
                cerradas.extend(lote)
        cerradas.sort(key=lambda x: x["cuando"], reverse=True)

        ganadoras = [c for c in cerradas if c["pnl"] > 0]
        con_pnl = [c for c in cerradas if c["pnl"] != 0]

        return {
            "saldo": saldo,
            "posiciones": abiertas,
            "pnl_abierto": round(sum(p["pnl_abierto"] for p in abiertas), 4),
            "resultado": {
                "pnl": round(pnl, 4),
                "comision": round(comision, 4),
                "funding": round(fondeo, 4),
                # La suma va aparte y NO reemplaza a las partes: es lo que
                # efectivamente cambió el saldo.
                "neto": round(pnl + comision + fondeo, 4),
            },
            "cerradas": cerradas[:40],
            "cuantas_cerradas": len(con_pnl),
            "win_rate_pct": (round(100.0 * len(ganadoras) / len(con_pnl), 1)
                             if con_pnl else None),
        }

    @app.post("/api/bot/plan-conjunto")
    def bot_plan_conjunto(payload: dict[str, Any]) -> dict[str, Any]:
        """Cómo quedaría el conjunto, SIN encender nada.

        Decidir separado de hacer, como el ciclo: se puede mirar el plan, no
        gustar, y cerrar la pantalla sin que haya pasado nada. El botón de
        encender viene después y es otro pedido.

        LAS EXPECTATIVAS SALEN DEL BACKTEST DE CADA UNA, Y SE DICE ASI. No son
        una promesa: son lo que esas estrategias hicieron sobre su histórico,
        agregado con la única aritmética defendible:

          · operaciones por mes: se SUMAN. La frecuencia no depende de la
            porción — la porción cambia cuánto se arriesga, no cuándo entra.
          · retorno anual esperado: Σ (porción × CAGR). Cada una compone
            sobre su pedazo, así que el conjunto suma a prorrata.
          · win rate: promedio PONDERADO POR FRECUENCIA. Un promedio simple
            dejaría que una estrategia de 2 operaciones al mes pese igual que
            una de 40 en un número que describe "lo que se ve al operar".

        Lo que NO se calcula: el drawdown del conjunto. Sumarlo supone que
        caen todas juntas (falso si diversifican) y promediarlo supone que
        nunca coinciden (falso también). Se muestra el peor individual, con su
        nombre, y listo — inventar un número intermedio sería precisión falsa.
        """
        _solo_escritorio()
        from botiquant.reports import portafolio as port

        ids = [str(x) for x in (payload.get("ids") or [])]
        if len(ids) < 2:
            raise HTTPException(400, "Un conjunto son al menos dos estrategias.")
        if len(ids) > 8:
            raise HTTPException(400, "Ocho es el tope de bots a la vez.")

        filas = []
        for sid in ids:
            try:
                filas.append(db.get_strategy(sid, None))
            except KeyError:
                raise HTTPException(404, f"La estrategia {sid} ya no está.")

        try:
            port.exigir_un_solo_mundo(filas)
        except port.MundosMezclados as exc:
            raise HTTPException(400, str(exc)) from exc

        usar_pct = float(payload.get("usar_pct") or 90.0)
        reparto = port.repartir(filas, usar_pct=usar_pct)

        # -------------------------------------------- las expectativas
        ops_mes = 0.0
        retorno = 0.0
        wr_num = 0.0
        peor_dd = None
        detalle = []
        for f in filas:
            meta = f.get("meta") or {}
            m = meta.get("metrics") or {}
            porc = float(reparto.porciones.get(str(f["id"])) or 0.0)
            tpm = float(m.get("trades_per_month") or 0.0)
            cagr = float(m.get("cagr_pct") or 0.0)
            wr = float(m.get("win_rate_pct") or 0.0)
            dd = float(m.get("max_drawdown_pct") or 0.0)
            ops_mes += tpm
            retorno += (porc / 100.0) * cagr
            wr_num += wr * tpm
            if peor_dd is None or dd > peor_dd[1]:
                peor_dd = (str(f.get("name") or f["id"]), dd)
            detalle.append({
                "id": f["id"], "nombre": f.get("name") or "",
                "instrumento": str(meta.get("dataset_name") or ""),
                "timeframe": str(meta.get("timeframe") or ""),
                "porcion_pct": porc,
                "ops_mes": tpm, "cagr_pct": cagr, "win_rate_pct": wr,
                "dd_pct": dd, "score": meta.get("score"),
                "pf": m.get("profit_factor"),
            })

        return {
            "detalle": detalle,
            "porciones": reparto.porciones,
            "avisos": [{"clave": a.clave, "texto": a.texto}
                       for a in reparto.avisos],
            "esperado": {
                "ops_mes": round(ops_mes, 1),
                "retorno_anual_pct": round(retorno, 2),
                "win_rate_pct": (round(wr_num / ops_mes, 1) if ops_mes else None),
                "peor_dd": ({"nombre": peor_dd[0], "dd_pct": peor_dd[1]}
                            if peor_dd else None),
            },
            "usar_pct": usar_pct,
        }

    @app.post("/api/bot/encender")
    def bot_encender(payload: dict[str, Any]) -> dict[str, Any]:
        """Arranca un bot desde un archivo de enlace.

        `modo` no tiene default a proposito. Un default que opere convierte un
        payload incompleto —un bug nuestro, un cliente viejo— en ordenes
        reales; sin default, lo peor que pasa es que no arranque.
        """
        _solo_escritorio()
        from botiquant.vivo import claves
        from botiquant.vivo.adaptador import (BASE_PRACTICA, BASE_REAL,
                                              Binance, BingX,
                                              Papel, SoloDatos)
        from botiquant.vivo.piloto import PILOTO
        from botiquant.vivo.runner import PRACTICA, REAL, SIMULACRO, Bot

        modo = str(payload.get("modo") or "")
        if modo not in (SIMULACRO, PRACTICA, REAL):
            raise HTTPException(
                400, "Falta decir en qué modo arrancar: simulacro, práctica o real.")

        # Se valida ACA, antes de tocar una clave o abrir un hilo. Un
        # documento incompleto reventaba despues con un KeyError en medio del
        # arranque: un error que no dice nada y que aparece mas tarde de lo
        # necesario.
        from botiquant.reports.bingx import validar as validar_bot
        try:
            doc = validar_bot(payload.get("bot"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        # LA CANTERA. Nada llega a un destino con riesgo sin pasar sus puertas.
        # Se revisa ACA y no en la pantalla: una comprobacion que vive solo en
        # el navegador la saltea cualquiera que llame al endpoint, y este es el
        # unico endpoint de la aplicacion que puede mover plata.
        from botiquant import cantera
        respaldo = doc.get("respaldo") or {}
        veredicto = cantera.revisar(
            {"metrics": respaldo, "oos": doc.get("fuera_de_muestra")}, modo)
        if not veredicto.pasa:
            raise HTTPException(422, {
                "mensaje": f"Esta estrategia todavía no puede operar en "
                           f"{modo}: {cantera.por_que_no(veredicto)}",
                "puertas": veredicto.puertas,
            })

        # EN QUE CASA SE OPERA. Explicito y no deducido del simbolo: BingX
        # pide BTC-USDT y Binance BTCUSDT, y adivinar por el guion convertiria
        # un error de tipeo en una orden al exchange equivocado.
        exchange = str(payload.get("exchange") or "bingx").lower()
        if exchange not in ("bingx", "binance"):
            raise HTTPException(400, f"Exchange desconocido: {exchange}")

        # BINANCE ESTA HABILITADO SOLO EN DEMO, y se corta ACA ademas de en el
        # adaptador. El adaptador ya no tiene forma de apuntar a la cuenta
        # real —no acepta una base— pero un 400 explica POR QUE no se puede,
        # mientras que un adaptador que igual opera en demo dejaria al usuario
        # creyendo que encendio en real.
        if exchange == "binance" and modo == REAL:
            raise HTTPException(
                400, "Binance está habilitado sólo en demo. La aplicación no "
                     "tiene forma de mandar una orden real a Binance: para "
                     "operar en real hay que cambiar el código a propósito.")

        if modo == SIMULACRO:
            # Sin credenciales: los datos de mercado son publicos y este modo
            # no manda ninguna orden. Asi se puede mirar que haria el bot
            # antes de haber creado siquiera la clave.
            datos: Any = Binance("", "") if exchange == "binance" else SoloDatos(BASE_PRACTICA)
            adaptador: Any = Papel(datos=datos,
                                   capital_inicial=float(payload.get("capital") or 1000.0))
        elif exchange == "binance":
            try:
                api_key, secret = claves.leer(workdir / "claves", "binance",
                                              "practica")
            except claves.ClaveError as exc:
                raise HTTPException(400, str(exc)) from exc
            adaptador = Binance(api_key, secret)
        else:
            entorno = "real" if modo == REAL else "practica"
            try:
                api_key, secret = claves.leer(workdir / "claves", "bingx", entorno)
            except claves.ClaveError as exc:
                raise HTTPException(400, str(exc)) from exc
            adaptador = BingX(api_key, secret,
                              base=BASE_REAL if modo == REAL else BASE_PRACTICA)

        # QUE LO OPERADO SOBREVIVA A CERRAR LA APLICACION. Sin esto el
        # registro vive en memoria y se pierde, y con el la unica evidencia de
        # como le fue en vivo — que es lo que el semaforo compara contra el
        # backtest para decidir si la ventaja se agoto.
        #
        # Se guardan solo las filas que son una operacion. El bot anota una por
        # vuelta aunque no haga nada, y eso serian veinticuatro filas por dia
        # por bot diciendo "no hubo senal".
        sid = str(payload.get("estrategia_id") or "").strip()

        def _anotar_afuera(fila: dict[str, Any]) -> None:
            if sid and fila.get("accion") in ("abrir", "cerrar"):
                db.anotar_operacion(sid, fila)

        # QUE PORCION DE LA CUENTA MANEJA. Por omisión la entera, que es lo
        # que corresponde con un solo bot y lo que hacían los que ya existían.
        # `or 1.0` NO SIRVE ACA: un cero es falso en Python, así que
        # `porcion: 0` se convertiría en 1.0 y el bot manejaría LA CUENTA
        # ENTERA justo cuando alguien pidió que no manejara nada. Se compara
        # contra None, que es lo único que significa "no lo mandaron".
        crudo = (payload or {}).get("porcion")
        try:
            porcion = 1.0 if crudo is None else float(crudo)
        except (TypeError, ValueError):
            raise HTTPException(400, "La porción tiene que ser un número.")

        try:
            bot = Bot(doc=doc, adaptador=adaptador, modo=modo, porcion=porcion,
                      oyente=_anotar_afuera if sid else None,
                      perdida_maxima_diaria=float(payload.get("perdida_maxima") or 0.0))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        try:
            return PILOTO.encender(bot)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/bot/apagar")
    def bot_apagar(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Deja de operar. NO cierra la posición: para eso está el pánico.

        Sin `simbolo` apaga TODOS. Es el botón de "me voy", y que exista uno
        solo para todo evita el caso peor: apagar cuatro de cinco creyendo que
        se apagaron los cinco.
        """
        _solo_escritorio()
        from botiquant.vivo.piloto import PILOTO
        simbolo = str((payload or {}).get("simbolo") or "").strip() or None
        return PILOTO.apagar(simbolo)

    @app.post("/api/bot/panico")
    def bot_panico(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Apaga y cierra lo que haya abierto. Sin `simbolo`, todos."""
        _solo_escritorio()
        from botiquant.vivo.piloto import PILOTO
        simbolo = str((payload or {}).get("simbolo") or "").strip() or None
        return PILOTO.panico(simbolo)

    #: Los enlaces que la aplicacion sabe abrir. SE PIDEN POR NOMBRE Y NO POR
    #: URL, que es mas fuerte que una lista blanca de direcciones: aunque
    #: alguien llame al endpoint a mano, lo unico que puede pedir es una de
    #: estas dos. Un endpoint que abre la URL que le manden es un endpoint que
    #: manda a la gente adonde le manden.
    ENLACES = {
        # Donde se crea la clave del entorno demo. NO es la de binance.com a
        # secas: esa seria la de la cuenta real.
        "binance_clave": "https://demo.binance.com/en/my/settings/api-management",
        # La pantalla donde se ve la orden aparecer del otro lado. Es la que
        # convierte "el registro dice que anduvo" en "lo vi".
        "binance_demo": "https://demo.binance.com/en/futures/BTCUSDT",
    }

    @app.post("/api/abrir-enlace")
    def abrir_enlace(payload: dict[str, Any] | None = None) -> dict[str, str]:
        """Abre en el navegador del sistema uno de NUESTROS enlaces.

        En el navegador del sistema y no en la ventana de la aplicacion: el
        escritorio es una sola ventana sin barra de direcciones, asi que
        navegar adentro dejaria al usuario en Binance sin forma de volver.

        Y solo en el escritorio, igual que abrir una carpeta. Servido a varios,
        esto abriria una pestania en la maquina del servidor.
        """
        _solo_escritorio()
        nombre = str((payload or {}).get("nombre") or "")
        url = ENLACES.get(nombre)
        if url is None:
            raise HTTPException(403, f"Ese enlace no es de Botiquant: {nombre}")
        import webbrowser
        webbrowser.open(url)
        return {"abierto": url}

    @app.post("/api/abrir-carpeta")
    def abrir_carpeta(payload: dict[str, Any] | None = None) -> dict[str, str]:
        """Abre en el explorador una de NUESTRAS carpetas de salida.

        La ruta que llega no se usa como ruta: se busca en la lista de carpetas
        que la aplicación misma calculó, y si no está, no se abre. Un endpoint
        que abre lo que le manden es un endpoint que ejecuta lo que le manden.

        Y sólo en el escritorio. Servido a varios, esto abriría una ventana en
        la máquina del servidor, que nadie va a ver y nadie pidió.
        """
        if MULTIUSER:
            raise HTTPException(404, "No disponible.")
        carpeta = carpeta_de_estrategias()
        pedida = str((payload or {}).get("ruta") or "").strip()
        if pedida:
            elegida = next((c for c in _carpetas_permitidas() if str(c) == pedida), None)
            if elegida is None:
                raise HTTPException(403, "Esa carpeta no es de Botiquant.")
            carpeta = elegida
        carpeta.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(carpeta)                     # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(carpeta)])
            else:
                subprocess.Popen(["xdg-open", str(carpeta)])
        except OSError as exc:
            raise HTTPException(500, f"No se pudo abrir la carpeta: {exc}") from exc
        return {"carpeta": str(carpeta)}

    # ------------------------------------------------------- descarga y cuenta
    def _instalador() -> Path | None:
        """El instalador, si ya se generó.

        La página consulta esto en vez de asumir que existe. Ofrecer una
        descarga que devuelve 404 es peor que decir que todavía no está: el
        usuario cree que el producto está roto en vez de que aún no salió.
        """
        ruta = BUILD_DIR / INSTALADOR
        return ruta if ruta.is_file() else None

    # ══════════════════════════════════ COMPARTIR UNA ESTRATEGIA CON UN ENLACE
    # El enlace se abre sin cuenta. Publica sólo la estrategia: nombre,
    # instrumento, costos, métricas, curva muestreada, veredicto y reglas en
    # palabras. Nunca claves, cuenta, saldo ni robots. Quien comparte recibe
    # un secreto y con eso apaga el enlace. Sin licencia, con un tope por día
    # por dirección para que nadie lo use de basurero.
    SITIO = os.environ.get("BQ_SITIO", "https://botiquant.com").rstrip("/")
    _TOPE_COMPARTIR_DIA = 30
    _TAM_MAX_DOC = 300_000

    def _ip_de(request: Request) -> str:
        xff = request.headers.get("x-forwarded-for", "")
        return (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")) or ""

    def _doc_compartible(payload: dict[str, Any]) -> dict[str, Any]:
        """Lo que se publica, y nada más: se copia campo por campo."""
        nivel = "mirar" if str(payload.get("nivel") or "") == "mirar" else "usar"
        doc = {
            "nivel": nivel,
            "nombre": str(payload.get("nombre") or "Estrategia")[:80],
            "autor": str(payload.get("autor") or "")[:40],
            "instrumento": str(payload.get("instrumento") or "")[:60],
            "timeframe": str(payload.get("timeframe") or "")[:8],
            "direccion": str(payload.get("direccion") or "")[:10],
            # "Para mirar" tampoco publica los bloques: son la receta de la
            # estrategia dicha en dos palabras (2 de septiembre).
            "bloques": str(payload.get("bloques") or "")[:200] if nivel == "usar" else "",
            # "Para mirar" es sin reglas: ni las ejecutables ni las escritas.
            "reglas": [str(x)[:200] for x in (payload.get("reglas") or [])][:20] if nivel == "usar" else [],
            "salidas": str(payload.get("salidas") or "")[:200] if nivel == "usar" else "",
            "costos": {k: float(v) for k, v in (payload.get("costos") or {}).items()
                       if isinstance(v, (int, float)) and k in ("spread", "slippage", "commission_pct", "initial_capital")},
            "metricas": {k: v for k, v in (payload.get("metricas") or {}).items()
                         if isinstance(v, (int, float, type(None)))},
            "curva": [round(float(v), 2) for v in (payload.get("curva") or [])][:240],
            "fechas": [str(x)[:10] for x in (payload.get("fechas") or [])][:240],
            "validacion": payload.get("validacion") if isinstance(payload.get("validacion"), dict) else None,
            "mundo": "exchange" if payload.get("mundo") == "exchange" else "metatrader",
            # las horas que el servidor del bróker adelanta a UTC: el .mq5 las
            # necesita para operar la franja horaria correcta
            "utc_offset": float(payload.get("utc_offset") or 0),
        }
        if nivel == "usar":
            doc["spec"] = payload.get("spec") or {}
        # UN PORTAFOLIO TAMBIÉN SE COMPARTE. Es la otra mitad del producto:
        # el conjunto dice si dos estrategias se suman o son la misma apuesta,
        # y eso es justo lo que uno quiere mostrarle a alguien.
        if payload.get("tipo") == "portafolio":
            pf = payload.get("portafolio") or {}
            doc["tipo"] = "portafolio"
            doc["portafolio"] = {
                "nombres": [str(x)[:60] for x in (pf.get("nombres") or [])][:12],
                "correlacion": (float(pf["correlacion"]) if isinstance(pf.get("correlacion"), (int, float)) else None),
                "ventana": {"from": str((pf.get("ventana") or {}).get("from") or "")[:10],
                            "to": str((pf.get("ventana") or {}).get("to") or "")[:10]},
                "partes": [{"nombre": str(c.get("nombre") or "")[:60],
                            "cagr_pct": c.get("cagr_pct"), "riesgo_pct": c.get("riesgo_pct")}
                           for c in (pf.get("partes") or [])][:12],
            }
        if len(json.dumps(doc)) > _TAM_MAX_DOC:
            raise HTTPException(413, "La estrategia es demasiado grande para compartirla.")
        return doc

    @app.post("/api/compartir")
    def compartir(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        ip = _ip_de(request)
        if db.compartidas_hoy(ip) >= _TOPE_COMPARTIR_DIA:
            raise HTTPException(429, "Ya compartiste muchas hoy. Mañana podés seguir.")
        doc = _doc_compartible(payload)
        codigo, secreto = db.crear_compartida(doc, ip)
        return {"codigo": codigo, "secreto": secreto, "url": f"{SITIO}/s/{codigo}"}

    @app.post("/api/compartir/remoto")
    def compartir_remoto(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Desde la aplicación de escritorio: manda la estrategia al sitio.

        En el sitio mismo (SOLO_WEB) se guarda acá directo; en la máquina del
        usuario se reenvía a botiquant.com, que es donde el enlace tiene que
        abrir para cualquiera.
        """
        if SOLO_WEB:
            return compartir(payload, request)
        import urllib.error
        import urllib.request as _ur
        datos = json.dumps(payload).encode("utf-8")
        req = _ur.Request(f"{SITIO}/api/compartir", data=datos,
                          headers={"Content-Type": "application/json", "User-Agent": f"Botiquant/{__version__}"})
        try:
            with _ur.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detalle = json.loads(exc.read().decode("utf-8")).get("detail") or str(exc)
            except Exception:  # noqa: BLE001
                detalle = str(exc)
            raise HTTPException(exc.code, str(detalle)) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise HTTPException(502, "No se pudo llegar a botiquant.com para publicar el enlace.") from exc

    @app.post("/api/compartir/apagar")
    def compartir_apagar_remoto(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        codigo = str(payload.get("codigo") or "")
        if SOLO_WEB:
            return apagar_compartida(codigo, payload)
        import urllib.error
        import urllib.request as _ur
        req = _ur.Request(f"{SITIO}/api/s/{codigo}/apagar", data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json", "User-Agent": f"Botiquant/{__version__}"})
        try:
            with _ur.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise HTTPException(exc.code, "No se pudo apagar el enlace.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise HTTPException(502, "No se pudo llegar a botiquant.com.") from exc

    @app.post("/api/s/{codigo}/apagar")
    def apagar_compartida(codigo: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not db.apagar_compartida(codigo, str(payload.get("secreto") or "")):
            raise HTTPException(404, "Ese enlace no existe o el secreto no coincide.")
        return {"ok": True}

    def _compartida_viva(codigo: str, contar: bool = False) -> dict[str, Any]:
        c = db.get_compartida(codigo, contar=contar)
        if not c:
            raise HTTPException(404, "Ese enlace no existe.")
        if c["apagada"]:
            raise HTTPException(410, "Quien compartió esta estrategia apagó el enlace.")
        return c

    @app.get("/api/s/{codigo}")
    def ver_compartida(codigo: str) -> dict[str, Any]:
        c = _compartida_viva(codigo)
        doc = dict(c["doc"])
        doc.pop("spec", None)          # las reglas ejecutables sólo viajan en el archivo
        return {"codigo": codigo, "creado": c["created"], "vistas": c["vistas"], **doc}

    @app.get("/api/s/{codigo}/{formato}")
    def bajar_compartida(codigo: str, formato: str) -> PlainTextResponse:
        c = _compartida_viva(codigo)
        doc = c["doc"]
        if doc.get("nivel") != "usar" or not doc.get("spec"):
            raise HTTPException(403, "Esta estrategia se compartió sólo para mirar.")
        spec = StrategySpec.from_dict(doc["spec"])
        simbolo = (doc.get("instrumento") or "").split(" ")[0]
        nombre = _nombre_de_archivo(doc.get("nombre"), "BQ_Compartida")
        if formato == "pine":
            codigo_txt = export_pine(spec, name=doc.get("nombre") or "Botiquant", symbol_hint=simbolo,
                                     timeframe_hint=doc.get("timeframe") or "", metrics=doc.get("metricas") or None,
                                     comision_pct=float((doc.get("costos") or {}).get("commission_pct") or 0.0))
            archivo = f"{nombre}.pine"
        elif formato == "mql5":
            ea = nombre if nombre.startswith("BQ_") else f"BQ_{nombre}"
            codigo_txt = export_mql5(spec, ea_name=ea, symbol_hint=simbolo,
                                     timeframe_hint=doc.get("timeframe") or "", metrics=doc.get("metricas") or None,
                                     server_utc_offset=int(round(doc.get("utc_offset") or 0)))
            archivo = f"{ea}.mq5"
        else:
            raise HTTPException(404, "Formato desconocido.")
        return PlainTextResponse(codigo_txt, media_type="text/plain",
                                 headers={"Content-Disposition": f'attachment; filename="{archivo}"'})

    @app.get("/s/{codigo}", include_in_schema=False)
    def pagina_compartida(codigo: str) -> HTMLResponse:
        """La estrategia, para cualquiera, sin cuenta. Una página liviana del
        servidor con vista previa para WhatsApp, X y Telegram."""
        try:
            c = _compartida_viva(codigo, contar=True)
        except HTTPException as exc:
            cuerpo = ("Quien compartió esta estrategia apagó el enlace." if exc.status_code == 410
                      else "Ese enlace no existe.")
            return HTMLResponse(_html_compartida_vacia(cuerpo), status_code=exc.status_code, headers=_NO_CACHE)
        return HTMLResponse(_html_compartida(codigo, c["doc"]), headers=_NO_CACHE)

    def _html_compartida_vacia(mensaje: str) -> str:
        return ("<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                "<meta name='robots' content='noindex'><title>BotiQuant</title>"
                "<style>body{margin:0;background:#0d1113;color:#e6ebed;font:16px/1.5 system-ui;display:grid;place-items:center;min-height:100vh}"
                "main{max-width:420px;padding:32px;text-align:center}a{color:#3fc3b8}</style></head>"
                f"<body><main><h1 style='font-size:22px'>{html_lib.escape(mensaje)}</h1>"
                "<p><a href='/'>Conocer BotiQuant</a></p></main></body></html>")

    def _bloque_portafolio(d: dict[str, Any], e) -> str:
        """El conjunto, en la página pública: qué lo compone, qué tan parecidas
        son entre sí y sobre qué ventana está medido."""
        pf = d.get("portafolio") or {}
        if not pf.get("nombres"):
            return ""
        c = pf.get("correlacion")
        if c is None:
            juicio, color = "No se pudo medir qué tan parecidas son", "#7d8b93"
        elif c >= 0.7:
            juicio, color = "Son casi la misma apuesta", "#f27a70"
        elif c >= 0.3:
            juicio, color = "Se parecen bastante", "#f0b64a"
        else:
            juicio, color = "Apuestas de verdad distintas", "#5ad38f"
        filas = "".join(
            f"<li>{e(str(p.get('nombre') or ''))}"
            f"{(' · ' + f'{float(p[chr(99)+chr(97)+chr(103)+chr(114)+chr(95)+chr(112)+chr(99)+chr(116)]):+.2f}% anual') if isinstance(p.get('cagr_pct'), (int, float)) else ''}"
            f"{(' · ' + f'{float(p[chr(114)+chr(105)+chr(101)+chr(115)+chr(103)+chr(111)+chr(95)+chr(112)+chr(99)+chr(116)]):.0f}% del riesgo') if isinstance(p.get('riesgo_pct'), (int, float)) else ''}"
            "</li>" for p in (pf.get("partes") or []))
        v = pf.get("ventana") or {}
        ventana = (f"<p style='margin:8px 0 0;color:var(--dim)'>Medido sobre la ventana que comparten: "
                   f"{e(v.get('from') or '—')} → {e(v.get('to') or '—')}.</p>") if v.get("from") else ""
        return (f"<div class='ver'><b class='w' style='color:{color}'>{juicio}</b>"
                f"{('<p style=\'margin:4px 0 0;color:var(--dim)\'>Qué tan parecidas son: ' + f'{c:.2f}' + ' — 1,0 es la misma apuesta dos veces; por debajo de 0,3 es diversificación de verdad.</p>') if c is not None else ''}"
                f"<ul style='margin:12px 0 0;padding-left:18px'>{filas}</ul>{ventana}</div>")

    def _html_compartida(codigo: str, d: dict[str, Any]) -> str:
        e = html_lib.escape
        m = d.get("metricas") or {}
        v = d.get("validacion") or {}
        def num(x, dec=2):
            try:
                return f"{float(x):,.{dec}f}"
            except (TypeError, ValueError):
                return "—"
        cagr = m.get("cagr_pct"); dd = m.get("max_drawdown_pct"); pf = m.get("profit_factor"); ops = m.get("trades")
        est = v.get("estado") or ""
        veredicto = {"aprobada": ("Aprobada", "#5ad38f"), "aceptable": ("Aguantó a medias", "#f0b64a"),
                     "no_paso": ("No pasó", "#f27a70")}.get(est, ("Sin probar", "#7d8b93"))
        curva = d.get("curva") or []
        if len(curva) >= 2:
            lo, hi = min(curva), max(curva)
            span = (hi - lo) or 1.0
            pts = " ".join(f"{i / (len(curva) - 1) * 600:.1f},{(1 - (c - lo) / span) * 150 + 10:.1f}" for i, c in enumerate(curva))
            grafico = (f"<svg viewBox='0 0 600 170' preserveAspectRatio='none'><polyline points='{pts}' fill='none' "
                       f"stroke='#3fc3b8' stroke-width='2'/></svg>")
        else:
            grafico = ""
        tramos = ""
        for tr in ((v.get("detalle") or {}).get("tramos") or [])[:4]:
            gana = (tr.get("afuera_pct") or 0) > 0
            tramos += (f"<div class='tramo'><span>Tramo {tr.get('n')}</span><i class='bar'><b class='in'></b>"
                       f"<b class='out' style='background:{'#5ad38f' if gana else '#f27a70'}'></b></i>"
                       f"<small>{e(str(tr.get('juzga', ['', ''])[0]))} → {e(str(tr.get('juzga', ['', ''])[1]))} · "
                       f"<strong style='color:{'#5ad38f' if gana else '#f27a70'}'>{'+' if gana else ''}{num(tr.get('afuera_pct'), 1)}%</strong></small></div>")
        reglas = "".join(f"<li>{e(r)}</li>" for r in (d.get("reglas") or []))
        usar = d.get("nivel") == "usar"
        titulo = f"{d.get('nombre') or 'Estrategia'} · {d.get('instrumento') or ''}".strip(" ·")
        descr = f"{'+' if (cagr or 0) >= 0 else ''}{num(cagr, 1)}% anual · caída máxima {num(dd, 1)}% · {veredicto[0]}"
        botones = ""
        if usar:
            botones = (f"<a class='btn pri' href='/api/s/{e(codigo)}/pine' download>Usar en TradingView</a>"
                       f"<a class='btn' href='/api/s/{e(codigo)}/mql5' download>Usar en MetaTrader 5</a>")
        botones += "<a class='btn' href='/'>Abrir en BotiQuant</a>"
        # LOS COSTOS, DICHOS: la página cerraba con "con los costos indicados"
        # y no indicaba ninguno (2 de septiembre).
        c = d.get("costos") or {}
        partes = []
        if c.get("commission_pct"):
            partes.append(f"comisión {num(c['commission_pct'], 3)}%")
        if c.get("spread"):
            partes.append(f"spread {num(c['spread'], 2)}")
        if c.get("slippage"):
            partes.append(f"deslizamiento {num(c['slippage'], 3)}")
        if c.get("initial_capital"):
            partes.append(f"capital inicial {num(c['initial_capital'], 0)}")
        costos_txt = ("Costos: " + " · ".join(partes) + ". ") if partes else ""
        return f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<meta name='robots' content='noindex'>
<title>{e(titulo)} · BotiQuant</title>
<meta property='og:title' content='{e(titulo)}'><meta property='og:description' content='{e(descr)}'>
<meta property='og:image' content='{SITIO}/social.png'><meta name='twitter:card' content='summary_large_image'>
<style>
:root{{--bg:#0d1113;--card:#161b1e;--inset:#1d2327;--line:#242b30;--ink:#e6ebed;--dim:#7d8b93;--acc:#3fc3b8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:720px;margin:0 auto;padding:32px 20px 64px}}
.marca{{display:flex;align-items:center;gap:10px;color:var(--dim);font-size:13px;margin-bottom:24px}}.marca i{{width:28px;height:28px;border-radius:8px;background:var(--acc);display:inline-block}}
h1{{font-size:28px;margin:0 0 4px;letter-spacing:-.02em}}.sub{{color:var(--dim);font-size:13px;margin:0 0 20px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}}.kpi{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}}
.kpi span{{display:block;font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}}.kpi b{{font-size:20px}}
.ver{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}}.ver b.w{{font-size:18px}}
.tramos{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}}.tramo{{background:var(--inset);border-radius:8px;padding:8px;font-size:11px;color:var(--dim)}}
.tramo .bar{{display:flex;height:6px;gap:1px;margin:6px 0;border-radius:3px;overflow:hidden}}.tramo .in{{flex:7;background:#344049;display:block}}.tramo .out{{flex:3;display:block}}
.graf{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:16px 0}}.graf svg{{width:100%;height:170px;display:block}}
.reglas{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}}.reglas ul{{margin:8px 0 0;padding-left:18px}}
.btns{{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}}.btn{{padding:10px 16px;border-radius:8px;border:1px solid #344049;color:var(--ink);text-decoration:none;font-weight:600;font-size:14px}}.btn.pri{{background:var(--acc);color:#06201d;border-color:transparent}}
.pie{{color:var(--dim);font-size:12px;margin-top:28px}}
@media (max-width:560px){{.kpis,.tramos{{grid-template-columns:1fr 1fr}}}}
</style></head><body><main>
<div class='marca'><i></i>Compartida desde BotiQuant{(' por ' + e(d['autor'])) if d.get('autor') else ''}</div>
<h1>{e(d.get('nombre') or 'Estrategia')}</h1>
<p class='sub'>{e(d.get('instrumento') or '')} · {e(d.get('timeframe') or '')} · {e(d.get('direccion') or '')} · {e(d.get('bloques') or '')}</p>
<div class='kpis'><div class='kpi'><span>Anual</span><b>{'+' if (cagr or 0) >= 0 else ''}{num(cagr, 1)}%</b></div>
<div class='kpi'><span>Caída máxima</span><b>{num(dd, 1)}%</b></div><div class='kpi'><span>Profit factor</span><b>{num(pf, 2)}</b></div>
<div class='kpi'><span>Operaciones</span><b>{num(ops, 0)}</b></div></div>
{_bloque_portafolio(d, e) if d.get("tipo") == "portafolio" else ""}
<div class='ver'{" hidden" if d.get("tipo") == "portafolio" else ""}><b class='w' style='color:{veredicto[1]}'>{veredicto[0]}</b>
{('<p style="margin:4px 0 0;color:var(--dim)">Ganó en ' + str(v.get('tramos_ganadores')) + ' de ' + str(v.get('tramos')) + ' tramos que nunca había visto · ' + ('+' if (v.get('retorno_fuera_pct') or 0) >= 0 else '') + num(v.get('retorno_fuera_pct'), 1) + '% fuera de muestra</p>') if est else '<p style="margin:4px 0 0;color:var(--dim)">Todavía no se puso a prueba sobre datos que no vio.</p>'}
{('<div class="tramos">' + tramos + '</div>') if tramos else ''}</div>
{('<div class="graf">' + grafico + '</div>') if grafico else ''}
{('<div class="reglas"><b>Reglas</b><ul>' + reglas + '</ul>' + ('<p style="margin:8px 0 0;color:var(--dim);font-size:13px">' + e(d.get('salidas') or '') + '</p>' if d.get('salidas') else '') + '</div>') if reglas else ''}
<div class='btns'>{botones}</div>
<p class='pie'>{costos_txt}Medida sobre datos históricos con esos costos. No es una recomendación de inversión: probala en una cuenta demo antes de ponerle plata.</p>
</main></body></html>"""

    @app.get("/api/descarga")
    def estado_descarga() -> dict[str, Any]:
        ruta = _instalador()
        return {
            "disponible": ruta is not None,
            "archivo": INSTALADOR,
            "bytes": ruta.stat().st_size if ruta else 0,
            "version": __version__,
        }

    #: Días que dura una licencia antes de refrescarse. No es una traba: la
    #: aplicación funciona sin conexión todo ese tiempo. Es lo que permite que
    #: dar de baja un plan tenga efecto alguna vez, sin obligar a consultar al
    #: servidor en cada backtest.
    LICENCIA_DIAS = _entero("BQ_LICENCIA_DIAS") or 90

    #: Hasta cuando se considera fundador a quien se dio de alta, en epoch.
    #: Vacio = todavia no se reconoce a nadie, que es lo correcto mientras no
    #: haya nada que cobrar. No se pierde nada por dejarlo asi: la fecha de
    #: alta vive en la base desde siempre y la licencia se vuelve a emitir cada
    #: vez que alguien entra a su cuenta, asi que la decision de a quien
    #: reconocer se puede tomar dentro de un anio con la misma informacion.
    FUNDADORES_HASTA = _entero("BQ_FUNDADORES_HASTA") or 0

    @app.get("/api/licencia")
    def emitir_licencia(request: Request, descargar: int = 0) -> Response:
        """Emite la licencia del usuario, firmada.

        Se emite acá y no en el escritorio porque la clave privada vive sólo en
        el servidor: la aplicación lleva la pública y puede verificar, nunca
        fabricar.
        """
        u = usuario_actual(request)
        if u is None:
            raise HTTPException(401, "Entrá con tu cuenta para obtener tu licencia.")
        privada = os.environ.get("BQ_LICENCIA_PRIVADA", "").strip()
        if not privada:
            raise HTTPException(
                503, "Este servidor todavía no tiene configurada la firma de licencias.")

        plan = str(u.get("plan") or "free")
        # El plan gratuito NO vence. Una licencia gratis que caduca a los tres
        # meses manda a todo el mundo a re-descargar la aplicacion justo cuando
        # se habia acostumbrado a usarla, y no protege nada: lo gratis ya es
        # gratis. La fecha existe para lo que se cobre.
        expira = 0 if plan == "free" else int(time.time()) + LICENCIA_DIAS * 86400

        # La fecha de alta viaja en la licencia para que la aplicacion pueda
        # decir "con nosotros desde marzo" sin preguntarle a ningun servidor.
        alta = _epoch_de(u.get("created"))
        token = firmar({"user_id": str(u["id"]), "email": str(u["email"]),
                        "plan": plan, "expira": expira, "alta": alta,
                        "fundador": bool(FUNDADORES_HASTA and alta
                                         and alta <= FUNDADORES_HASTA)}, privada)
        if descargar:
            return PlainTextResponse(
                token, media_type="text/plain",
                headers={"Content-Disposition": 'attachment; filename="botiquant.licencia"'})
        return JSONResponse({
            "token": token, "plan": plan, "expira": expira, "alta": alta,
            # None y no un numero cuando no vence: "0 dias restantes" se lee
            # como vencida, que es exactamente lo contrario
            "dias_restantes": None if expira == 0 else LICENCIA_DIAS,
        })

    #: La licencia del lado de la maquina del usuario.
    #:
    #: Solo en modo escritorio. En un servidor compartido no tiene sentido: ahi
    #: las licencias se emiten, no se guardan, y un archivo unico en disco seria
    #: de todos y de nadie.
    #:
    #: Hoy no habilita ni bloquea nada — la aplicacion funciona igual con
    #: licencia y sin ella. Esta puesto desde el principio porque una version
    #: publicada que no mira la licencia la va a ignorar para siempre, y no hay
    #: forma de agregarle el control despues a las copias ya instaladas.
    if not MULTIUSER:

        @app.get("/api/licencia/local")
        def licencia_local() -> dict[str, Any]:
            """Quien esta usando la aplicacion, comprobado sin red."""
            return licencia_en_disco.leer().to_dict()

        @app.post("/api/licencia/local")
        def poner_licencia(payload: dict[str, Any]) -> dict[str, Any]:
            """Importar una licencia pegada o traida de un archivo.

            Comprueba antes de escribir: pegar una licencia equivocada no puede
            dejar al usuario sin la que ya tenia puesta.
            """
            texto = str(payload.get("texto") or "").strip()
            if not texto:
                raise HTTPException(400, "Pegá el texto de tu licencia.")
            estado = licencia_en_disco.guardar(texto)
            if estado.situacion != "valida":
                raise HTTPException(400, _POR_QUE_NO_SIRVE.get(
                    estado.situacion, "Esa licencia no se pudo comprobar."))
            return estado.to_dict()

        @app.delete("/api/licencia/local")
        def sacar_licencia() -> dict[str, Any]:
            """Sacarla de la maquina. Es de quien la usa."""
            return licencia_en_disco.borrar().to_dict()

    @app.api_route("/descargar", methods=["GET", "HEAD"], include_in_schema=False)
    def descargar(request: Request) -> Response:
        """Baja el instalador. Pide cuenta: es el momento en que se entrega
        algo, y es donde el registro se justifica."""
        _exigir_para_descargar(request)
        ruta = _instalador()
        if ruta is None:
            raise HTTPException(
                503, "La aplicación de escritorio todavía no está publicada.")
        if XACCEL:
            # Cuerpo vacío a propósito: nginx lo reemplaza por el archivo. El
            # Content-Disposition sí viaja, para que el navegador lo guarde con
            # su nombre en vez de mostrarlo.
            return Response(
                headers={
                    "X-Accel-Redirect": f"{XACCEL.rstrip('/')}/{ruta.name}",
                    "Content-Disposition": f'attachment; filename="{INSTALADOR}"',
                    "Content-Type": "application/octet-stream",
                })
        return FileResponse(ruta, filename=INSTALADOR,
                            media_type="application/octet-stream")

    # ------------------------------------------------------------------- UI
    # The UI is edited in place and served locally, so a cached copy is always
    # wrong and never a win — a stale app.js silently shows an older Botiquant.
    # Asset URLs carry the file's mtime, which makes the browser refetch the
    # moment a file changes and cache it happily in between.
    _NO_CACHE = {"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"}

    def _html_de_la_app() -> HTMLResponse:
        html = (UI_DIR / "index.html").read_text(encoding="utf-8")
        # La lista tiene que llevar TODOS los archivos que index.html enlaza.
        # i18n.js quedó afuera al agregarlo y fue el único que se servía
        # cacheado: la aplicación nueva con el diccionario viejo, que se ve
        # como claves crudas en pantalla y no como un error.
        for asset in ("app.js", "charts.js", "i18n.js", "styles.css"):
            path = UI_DIR / asset
            if path.exists():
                html = html.replace(f"/static/{asset}",
                                    f"/static/{asset}?v={int(path.stat().st_mtime)}")
        return HTMLResponse(html, headers=_NO_CACHE)

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def landing() -> HTMLResponse:
        """La portada explica el producto; la aplicación vive en /app.

        Si la landing no está (por ejemplo en un checkout parcial) se sirve la
        aplicación: quedarse sin portada es un problema, quedarse sin producto
        es otro mucho peor.
        """
        portada = LANDING_DIR / "index.html"
        if not portada.exists():
            return _html_de_la_app()
        return HTMLResponse(portada.read_text(encoding="utf-8"), headers=_NO_CACHE)

    #: Las dos páginas que Google exige para publicar la aplicación a cualquiera
    #: y no sólo a una lista de correos de prueba. Van servidas por el mismo
    #: proceso y no como archivos sueltos porque tienen que existir siempre: si
    #: la política de privacidad no carga, el revisor rechaza la aplicación.
    #: Lo que todo sitio sirve y este no servía. Trece pedidos a /robots.txt y
    #: diez a /favicon.ico terminaron en 404: el icono existe pero viaja
    #: embebido en el HTML, así que lo ve el navegador y no lo ve nada de lo
    #: que lo pide por separado —marcadores, buscadores, la barra de tareas—.
    _ROBOTS = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /app\n"
        "Disallow: /cuenta\n"
        "Disallow: /s/\n"
        "Disallow: /api/\n"
        "\n"
        "Sitemap: https://botiquant.com/sitemap.xml\n"
    )

    @app.api_route("/robots.txt", methods=["GET", "HEAD"], include_in_schema=False)
    def robots() -> Response:
        return Response(_ROBOTS, media_type="text/plain")

    @app.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
    def sitemap() -> Response:
        paginas = ("", "descargar", "privacidad", "terminos")
        cuerpo = "".join(
            f"<url><loc>https://botiquant.com/{p}</loc></url>" for p in paginas)
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{cuerpo}</urlset>",
            media_type="application/xml")

    @app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
    def favicon() -> Response:
        ico = ROOT / "botiquant.ico"
        if not ico.exists():
            raise HTTPException(404, "sin icono")
        return FileResponse(ico, media_type="image/x-icon",
                            headers={"Cache-Control": "public, max-age=86400"})

    @app.api_route("/privacidad", methods=["GET", "HEAD"], include_in_schema=False)
    def pagina_privacidad() -> Response:
        return _pagina_legal("privacidad.html")

    @app.api_route("/terminos", methods=["GET", "HEAD"], include_in_schema=False)
    def pagina_terminos() -> Response:
        return _pagina_legal("terminos.html")

    def _pagina_legal(archivo: str) -> Response:
        pagina = LANDING_DIR / archivo
        if not pagina.exists():
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(pagina.read_text(encoding="utf-8"), headers=_NO_CACHE)

    #: Los tres nombres llevan al mismo lugar. Alguien ya probó /contact y se
    #: comió un 404: el que busca ayuda prueba la palabra que se le ocurre, y
    #: hacerlo adivinar es exactamente lo contrario de lo que se necesita.
    @app.api_route("/soporte", methods=["GET", "HEAD"], include_in_schema=False)
    def pagina_soporte() -> Response:
        pagina = LANDING_DIR / "soporte.html"
        if not pagina.exists():
            raise HTTPException(404, "No está.")
        return HTMLResponse(pagina.read_text(encoding="utf-8"))

    @app.api_route("/contacto", methods=["GET", "HEAD"], include_in_schema=False)
    @app.api_route("/contact", methods=["GET", "HEAD"], include_in_schema=False)
    @app.api_route("/ayuda", methods=["GET", "HEAD"], include_in_schema=False)
    def soporte_alias() -> Response:
        return RedirectResponse("/soporte", status_code=308)

    @app.api_route("/social.png", methods=["GET", "HEAD"], include_in_schema=False)
    def tarjeta_social() -> Response:
        """La imagen de la tarjeta al compartir el enlace.

        Va en la raíz y no bajo /static-landing porque varios lectores de
        enlaces sólo siguen rutas simples, y porque es una URL que después
        queda escrita en mensajes que no se pueden editar."""
        img = LANDING_DIR / "social.png"
        if not img.exists():
            raise HTTPException(404, "No está.")
        return FileResponse(img, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/static-landing/legal.css", include_in_schema=False)
    def css_legal() -> Response:
        hoja = LANDING_DIR / "legal.css"
        if not hoja.exists():
            raise HTTPException(404, "No está.")
        return Response(hoja.read_text(encoding="utf-8"), media_type="text/css")

    @app.api_route("/cuenta", methods=["GET", "HEAD"], include_in_schema=False)
    def pagina_cuenta() -> Response:
        """Quién sos, tu licencia y la descarga. Es lo único que el servidor
        hace por el usuario: el trabajo pesado corre después en su máquina."""
        pagina = LANDING_DIR / "cuenta.html"
        if not pagina.exists():
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(pagina.read_text(encoding="utf-8"), headers=_NO_CACHE)

    @app.get("/app", include_in_schema=False)
    def app_ui(request: Request) -> Response:
        # La aplicación no se usa en la web. Se manda a la cuenta, que es donde
        # está la descarga, en vez de a una pantalla que no va a poder hacer nada.
        if SOLO_WEB:
            return RedirectResponse("/cuenta", status_code=303)
        # Sin cuenta no se entra: se vuelve a la portada, que es donde está el
        # botón. Servir la pantalla y que después fallara todo adentro sería
        # dejar al usuario mirando una aplicación rota.
        if _auth_listo() and usuario_actual(request) is None:
            return RedirectResponse("/?login=requerido", status_code=303)
        return _html_de_la_app()

    @app.get("/static/index.html", include_in_schema=False)
    def shell_suelto() -> Response:
        """La carcasa de la app también vive en /static, porque ahí se monta la
        carpeta entera para servir el JS y el CSS. Entrando por ese camino se
        saltea el control de /app.

        No filtra nada —la API responde 401 igual— pero deja a alguien mirando
        una pantalla que falla entera. Se manda a la puerta de siempre.
        """
        return RedirectResponse("/app", status_code=303)

    class _UISinCache(StaticFiles):
        """La interfaz se revalida SIEMPRE; los tipos de letra se cachean.

        Sin esto, el navegador aplica caché heurística —StaticFiles manda ETag
        pero no Cache-Control— y se queda con el JavaScript de la versión
        anterior. Se ve exactamente como que la actualización no llegó: la
        aplicación nueva corriendo la pantalla vieja, sin ningún error.

        ``no-cache`` no significa "no guardes": significa "guardá pero
        preguntá antes de usar". Con el ETag que ya se manda, un archivo que
        no cambió se resuelve en un 304 sin cuerpo, así que no cuesta ancho de
        banda. Las tipografías sí se cachean un año porque llevan el hash en
        el nombre y no cambian nunca.
        """

        def file_response(self, full_path, stat_result, scope, status_code=200):
            resp = super().file_response(full_path, stat_result, scope, status_code)
            es_fuente = str(full_path).lower().endswith((".woff2", ".woff", ".ttf"))
            resp.headers["cache-control"] = ("public, max-age=31536000, immutable"
                                             if es_fuente else "no-cache")
            return resp

    # va DESPUÉS de la ruta: el mount toma todo lo que empiece con /static, así
    # que declarado antes se quedaría también con index.html
    app.mount("/static", _UISinCache(directory=str(UI_DIR)), name="static")

    @app.exception_handler(HTTPException)
    async def error_traducido(request: Request, exc: HTTPException):
        """Devuelve el mensaje en el idioma de la interfaz.

        La interfaz manda su idioma en una cabecera; sin ella se responde en
        espanol, que es lo que hacia antes. Traducir aca y no en cada `raise`
        evita que todas las funciones internas tengan que arrastrar el idioma
        hasta el fondo.
        """
        idioma = (request.headers.get("x-idioma") or "").lower()[:2]
        detalle = exc.detail
        if isinstance(detalle, str):
            detalle = traducir_error(detalle, idioma)
        return JSONResponse({"detail": detalle}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(DemasiadoTrabajo)
    async def sin_cupo(request, exc):
        """429 y no 500: quedarse sin cupo es una respuesta normal del servidor,
        no una falla. La interfaz muestra el texto tal cual, así que tiene que
        decir qué pasó y qué hacer."""
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unhandled(request, exc):  # pragma: no cover
        return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})

    return app


app = create_app()
