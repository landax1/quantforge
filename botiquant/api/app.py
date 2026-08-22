"""FastAPI application: JSON API + static UI, all local, all offline.

Fast operations (single backtest, Monte Carlo, portfolio) run synchronously;
search operations (generate / evolve / optimize / walk-forward) run as
background jobs polled via ``/api/jobs/{id}``.
"""

from __future__ import annotations

import dataclasses
import hmac
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
from botiquant.data.catalog import BY_KEY, CATALOG, default_stop_points
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
from botiquant.reports.pine import export_pine
from botiquant.reports.report import excel_report, html_report, metrics_csv, trades_csv
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
    # puede ni probar. Sólo si el workspace está vacío — ver semilla.sembrar.
    sembrar(store, len(db.list_datasets(None)))
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
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            # pedir un timeframe más fino que el del dataset: 400 y no 500,
            # porque es una elección corregible y el texto explica cómo
            raise HTTPException(400, str(exc)) from exc
        return _slice_dates(df, payload)

    def _spec(payload: dict[str, Any]) -> StrategySpec:
        raw = payload.get("spec")
        if not raw:
            raise HTTPException(400, "spec is required")
        return StrategySpec.from_dict(raw)

    def _settings(payload: dict[str, Any]) -> BacktestSettings:
        return BacktestSettings.from_dict(payload.get("settings") or {})

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
            if entry["label"].lower() in low or entry["dukascopy"].lower() in low:
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
        out = []
        for entry in CATALOG:
            names = (entry["label"].lower(), entry["dukascopy"].lower())
            have = next((d for d in owned
                         if any(n in d["name"].lower() for n in names)), None)
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
                        "end": have["end"] if have else None})
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
            df = catalog_download(key, workdir, progress=progress)
            progress(0.98, "Guardando…")
            return store.add(f"{entry['label']} M1", df, source="dukascopy")
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
        if (_auth_listo() and ruta.startswith("/api/") and ruta not in SIN_CUENTA
                and usuario_actual(request) is None):
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
        accept = {"min_pf": _crit("min_pf"), "min_sharpe": _crit("min_sharpe"),
                  "min_win_rate_pct": _crit("min_win_rate_pct"),
                  "max_dd_pct": _crit("max_dd_pct"), "min_net_pct": _crit("min_net_pct"),
                  "min_cagr_pct": _crit("min_cagr_pct"),
                  "min_ret_dd": _crit("min_ret_dd"),
                  "min_trades_month": _crit("min_trades_month"),
                  "min_exposure_pct": _crit("min_exposure_pct")}

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
                "risk": dataclasses.asdict(risk), "settings": dataclasses.asdict(settings),
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
                sessions=ses,
                method="evolution" if payload.get("method") == "evolution" else "random",
                population=int(min(max(int(payload.get("population", 40)), 8), 200)),
                seed=seed,
                handle=handle,
            )
            out["range"] = used_range
            out["corrida_id"] = archivar(out)
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
            }
            try:
                db.guardar_validacion(sid, salida, dueno)
            except (KeyError, sqlite3.Error):
                # que falle el archivado no puede tirar el resultado: la prueba
                # ya tardó sus minutos y está en pantalla
                traceback.print_exc()
            # el detalle viaja para dibujar, pero NO se guarda: son cientos de
            # puntos de curva por estrategia y lo que hace falta después es el
            # veredicto, no el gráfico
            return {**salida, "detalle": {"folds": wf["folds"],
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
    def list_strategies(request: Request) -> list[dict[str, Any]]:
        return db.list_strategies(duenio(request))

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

    @app.get("/api/corridas")
    def list_corridas(request: Request) -> dict[str, Any]:
        dueno = duenio(request)
        return {
            "corridas": db.list_corridas(dueno),
            "total": db.contar_banco(dueno),
            "tope": db.TOPE_BANCO,
            "tope_corridas": db.TOPE_CORRIDAS,
        }

    @app.get("/api/banco")
    def list_banco(request: Request, corrida: str = "", orden: str = "puesto",
                   dir: str = "", limite: int = _PAGINA_BANCO,
                   desde: int = 0) -> list[dict[str, Any]]:
        desc = None if dir not in ("asc", "desc") else (dir == "desc")
        return db.list_banco(
            corrida_id=corrida or None, orden=orden, desc=desc,
            limite=max(1, min(limite, _PAGINA_BANCO)), desde=max(0, desde),
            user_id=duenio(request))

    @app.delete("/api/corridas/{cid}")
    def borrar_corrida(request: Request, cid: str) -> dict[str, int]:
        return {"borradas": db.borrar_corrida(cid, duenio(request))}

    @app.post("/api/banco/borrar")
    def borrar_del_banco(request: Request, payload: dict[str, Any]) -> dict[str, int]:
        ids = [str(x) for x in (payload.get("ids") or [])]
        return {"borradas": db.borrar_banco(ids, duenio(request))}

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
        guardadas = []
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
            sid = db.save_strategy(
                f["nombre"], fila.get("spec") or {},
                notes="", meta=meta, user_id=dueno)
            guardadas.append({"id": sid, "name": f["nombre"]})
        return {"guardadas": guardadas}

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

    def _offset_broker(payload: dict[str, Any]) -> int:
        """Horas que adelanta el servidor del bróker respecto de UTC.

        Viaja en cada exportación en vez de guardarse del lado del servidor:
        es una preferencia de la máquina del usuario, igual que el spread por
        instrumento, y el servidor no tiene forma de saberla.

        Se acota a ±14 porque no existe ninguna zona fuera de ese rango, y un
        número absurdo movería la franja horaria a cualquier lado sin que nada
        avise.
        """
        crudo = payload.get("server_utc_offset")
        try:
            return max(-14, min(14, int(crudo)))
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
        if formato == "pine":
            # el nombre VISIBLE dentro del script puede llevar espacios; el del
            # archivo no puede llevar nada que forme una ruta
            name = str(payload.get("name") or "QF Strategy")
            code = export_pine(spec, name=name, symbol_hint=ds_name,
                               timeframe_hint=tf, metrics=metricas)
            return code, _nombre_de_archivo(name, "QF_Strategy") + ".pine"
        name = _nombre_de_archivo(payload.get("name"), "BQ_Strategy")
        code = export_mql5(spec, ea_name=name, symbol_hint=ds_name,
                           timeframe_hint=tf, metrics=metricas,
                              server_utc_offset=_offset_broker(payload))
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

    @app.post("/api/export/pine")
    def export_pine_endpoint(payload: dict[str, Any], request: Request) -> PlainTextResponse:
        """Render a mined strategy as a TradingView Pine Script v5 strategy."""
        code, archivo = _codigo_exportado("pine", payload, request)
        return PlainTextResponse(code, media_type="text/plain",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="{archivo}"'})

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
        if formato not in ("mql5", "pine"):
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
        if ruta.suffix.lower() not in (".mq5", ".pine"):
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

    @app.get("/descargar", include_in_schema=False)
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

    @app.get("/", include_in_schema=False)
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
    @app.get("/privacidad", include_in_schema=False)
    def pagina_privacidad() -> Response:
        return _pagina_legal("privacidad.html")

    @app.get("/terminos", include_in_schema=False)
    def pagina_terminos() -> Response:
        return _pagina_legal("terminos.html")

    def _pagina_legal(archivo: str) -> Response:
        pagina = LANDING_DIR / archivo
        if not pagina.exists():
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(pagina.read_text(encoding="utf-8"), headers=_NO_CACHE)

    @app.get("/static-landing/legal.css", include_in_schema=False)
    def css_legal() -> Response:
        hoja = LANDING_DIR / "legal.css"
        if not hoja.exists():
            raise HTTPException(404, "No está.")
        return Response(hoja.read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/cuenta", include_in_schema=False)
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
