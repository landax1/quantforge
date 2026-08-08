"""FastAPI application: JSON API + static UI, all local, all offline.

Fast operations (single backtest, Monte Carlo, portfolio) run synchronously;
search operations (generate / evolve / optimize / walk-forward) run as
background jobs polled via ``/api/jobs/{id}``.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response,
)
from fastapi.staticfiles import StaticFiles

from quantforge import __version__
from quantforge.auth import SessionError, clear_cookie, read_cookie, set_cookie, sign, verify
from quantforge.auth.google import (
    GoogleConfig, authorize_url, exchange_code, fetch_profile, new_state,
)
from quantforge.analysis.montecarlo import monte_carlo
from quantforge.analysis.walkforward import walk_forward
from quantforge.backtesting.engine import run_backtest
from quantforge.backtesting.metrics import SCORE_PARTS, qf_score, score_breakdown
from quantforge.core.jobs import JobManager
from quantforge.core.models import (
    OPERATORS, PRICE_FIELDS, BacktestSettings, RiskConfig, StrategySpec, TimeFilter,
)
from quantforge.data.catalog import BY_KEY, CATALOG, default_stop_points
from quantforge.data.catalog import download as catalog_download
from quantforge.data.loader import parse_ohlcv_csv
from quantforge.data.sample import generate_sample
from quantforge.data.store import DataStore
from quantforge.database.db import Database
from quantforge.generator.generator import generate_strategies
from quantforge.generator.templates import template_catalog
from quantforge.genetic.evolution import evolve
from quantforge.mining.miner import mine
from quantforge.indicators import indicator_catalog
from quantforge.optimizer.optimizer import discover_dimensions, optimize
from quantforge.portfolio.portfolio import build_portfolio
from quantforge.reports.mql5 import export_mql5
from quantforge.reports.pine import export_pine
from quantforge.reports.report import excel_report, html_report, metrics_csv, trades_csv

ROOT = Path(__file__).resolve().parent.parent.parent
UI_DIR = ROOT / "ui"
WORK_DIR = ROOT / "workspace"

#: En una máquina propia el usuario ya puede leer sus archivos, así que la
#: importación por ruta es una comodidad. Servido a terceros, ese mismo
#: endpoint lee cualquier archivo del servidor: se apaga con QF_MULTIUSER=1.
MULTIUSER = os.environ.get("QF_MULTIUSER", "").strip() not in ("", "0", "false")


def create_app(workdir: Path | None = None) -> FastAPI:
    workdir = Path(workdir or WORK_DIR)
    workdir.mkdir(parents=True, exist_ok=True)

    db = Database(workdir / "quantforge.sqlite")
    store = DataStore(workdir / "datasets", db)
    jobs = JobManager()

    app = FastAPI(title="QuantForge", version=__version__, docs_url="/api/docs")

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
    def list_datasets() -> list[dict[str, Any]]:
        """Datasets plus the exit distances that make sense for each one.

        A stop is an absolute price distance, so the UI cannot carry a single
        default: 40 points is a normal stop on the S&P and unreachable on
        EURUSD. Every dataset ships with its own suggestion so the mining page
        can never propose a stop the market will not travel.
        """
        out = []
        for d in store.list():
            entry = _catalog_entry_for(d.get("name", ""))
            if entry and entry.get("stop_points"):
                stop, target = entry["stop_points"], entry["target_points"]
            else:
                stop, target = default_stop_points(d.get("last_close") or 0.0)
            out.append({**d, "suggested_stop": stop, "suggested_target": target,
                        "suggested_spread": entry["spread"] if entry else None,
                        "suggested_slippage": entry["slippage"] if entry else None})
        return out

    @app.post("/api/datasets/upload")
    async def upload_dataset(file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        try:
            df = parse_ohlcv_csv(content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        name = (file.filename or "upload.csv").rsplit(".", 1)[0]
        return store.add(name, df, source="upload")

    @app.post("/api/datasets/sample")
    def create_sample(payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload.get("symbol", "DEMO"))[:20] or "DEMO"
        bars = int(min(max(int(payload.get("bars", 20_000)), 500), 200_000))
        tf = int(payload.get("timeframe_minutes", 60))
        df = generate_sample(symbol=symbol, bars=bars, timeframe_minutes=tf,
                             start_price=float(payload.get("start_price", 100.0)),
                             start=str(payload.get("start", "2021-01-01")))
        return store.add(f"{symbol} (sample)", df, source="sample")

    @app.get("/api/catalog")
    def instrument_catalog() -> list[dict[str, Any]]:
        """Popular instruments with their broker cost profile."""
        # only real market data counts as "ready" — a synthetic sample named
        # EURUSD must never be mistaken for downloaded history
        owned = [d for d in store.list() if d["source"] != "sample"]
        out = []
        for entry in CATALOG:
            names = (entry["label"].lower(), entry["dukascopy"].lower())
            have = next((d for d in owned
                         if any(n in d["name"].lower() for n in names)), None)
            out.append({**entry,
                        "dataset_id": have["id"] if have else None,
                        "rows": have["rows"] if have else 0,
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
        ``QF_MULTIUSER=1`` and let users upload instead.
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
    def delete_dataset(ds_id: str) -> dict[str, str]:
        """En modo multiusuario, los datasets compartidos no se borran.

        Sin esto, un clic en "Borrar" de cualquier usuario deja al resto sin
        el S&P 500 hasta que alguien lo reponga a mano: 4,6 millones de velas
        que hay que volver a descargar de Dukascopy.
        """
        if MULTIUSER:
            try:
                fuente = db.get_dataset(ds_id).get("source", "")
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            if fuente not in BORRABLE:
                raise HTTPException(
                    403, "Este instrumento es compartido y no se puede borrar. "
                         "Sólo podés borrar los CSV que subiste vos.")
        store.delete(ds_id)
        return {"status": "deleted"}

    # -------------------------------------------------------------- backtest
    @app.post("/api/backtest")
    def backtest(payload: dict[str, Any]) -> dict[str, Any]:
        df = _load_df(payload)
        spec = _spec(payload)
        # an explicit risk block overrides whatever the spec carries, so the
        # inspector can re-run a mined strategy under different exit settings
        if payload.get("risk"):
            spec.risk = _risk(payload)
        result = run_backtest(df, spec, _settings(payload)).to_dict()
        result["score"] = qf_score(result["metrics"])
        result["score_parts"] = {k: round(v, 3)
                                 for k, v in score_breakdown(result["metrics"]).items()}
        out: dict[str, Any] = {"result": result}
        if payload.get("save"):
            ds = db.get_dataset(payload["dataset_id"])
            rid = db.save_result(spec.name, ds["id"], ds["name"], result,
                                 kind="backtest", strategy_id=payload.get("strategy_id"))
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
        nadie. Con login configurado, bajarse un archivo requiere estar dentro."""
        if not _auth_listo():
            return None
        u = usuario_actual(request)
        if u is None:
            raise HTTPException(
                401, "Creá tu cuenta para descargar la estrategia. "
                     "Minar y ver resultados es libre.")
        return u

    @app.get("/api/auth/me")
    def auth_me(request: Request) -> dict[str, Any]:
        u = usuario_actual(request)
        return {
            "configurado": _auth_listo(),
            "usuario": None if u is None else {
                "email": u["email"], "name": u["name"], "picture": u["picture"],
            },
        }

    @app.get("/api/auth/google/start", include_in_schema=False)
    def auth_start() -> Response:
        if not _auth_listo():
            raise HTTPException(503, "El inicio de sesión no está configurado en este servidor.")
        estado = new_state()
        r = RedirectResponse(authorize_url(gcfg, estado), status_code=307)
        # el state viaja firmado en una cookie propia y corta: es lo que
        # permite comprobar en el callback que la vuelta corresponde a una ida
        # que salió de acá y no de otro sitio
        r.set_cookie("qf_oauth_state", sign({"s": estado}, SECRET, max_age=600),
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
            guardado = verify(request.cookies.get("qf_oauth_state", ""), SECRET)
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
        r = RedirectResponse("/?login=ok", status_code=303)
        set_cookie(r, sign({"uid": u["id"]}, SECRET), secure=COOKIE_SECURE)
        r.delete_cookie("qf_oauth_state", path="/")
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
    def start_mine(payload: dict[str, Any]) -> dict[str, str]:
        df = _load_df(payload)
        risk = _risk(payload)
        settings = _settings(payload)
        _check_cost_scale(df, settings)
        from quantforge.generator.templates import drivers as all_drivers, filters as all_filters
        drv = payload.get("drivers") or [d.id for d in all_drivers()]
        flt = payload.get("filters")
        if flt is None:
            flt = [f.id for f in all_filters()]
        raw_seed = payload.get("seed")
        seed = int(raw_seed) if raw_seed not in (None, "") else None

        def _crit(key):
            v = payload.get(key)
            return float(v) if v not in (None, "") else None
        accept = {"min_pf": _crit("min_pf"), "min_sharpe": _crit("min_sharpe"),
                  "min_win_rate_pct": _crit("min_win_rate_pct"),
                  "max_dd_pct": _crit("max_dd_pct"), "min_net_pct": _crit("min_net_pct"),
                  "min_cagr_pct": _crit("min_cagr_pct"),
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
                method="evolution" if payload.get("method") == "evolution" else "random",
                population=int(min(max(int(payload.get("population", 40)), 8), 200)),
                seed=seed,
                handle=handle,
            )
            out["range"] = used_range
            return out
        return {"job_id": jobs.submit_streaming("mine", work)}

    @app.post("/api/generate")
    def start_generate(payload: dict[str, Any]) -> dict[str, str]:
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
        return {"job_id": jobs.submit("generate", work)}

    @app.post("/api/evolve")
    def start_evolve(payload: dict[str, Any]) -> dict[str, str]:
        df = _load_df(payload)
        risk = _risk(payload)
        settings = _settings(payload)
        from quantforge.generator.templates import drivers as all_drivers, filters as all_filters
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
        return {"job_id": jobs.submit("evolve", work)}

    @app.post("/api/optimize/dimensions")
    def optimize_dimensions(payload: dict[str, Any]) -> dict[str, Any]:
        spec = _spec(payload)
        return {"dimensions": [d.to_dict() for d in discover_dimensions(spec)]}

    @app.post("/api/optimize")
    def start_optimize(payload: dict[str, Any]) -> dict[str, str]:
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
        return {"job_id": jobs.submit("optimize", work)}

    @app.post("/api/walkforward")
    def start_walkforward(payload: dict[str, Any]) -> dict[str, str]:
        df = _load_df(payload)
        spec = _spec(payload)
        settings = _settings(payload)

        def work(progress):
            return walk_forward(
                df, spec,
                folds=int(payload.get("folds", 4)),
                train_pct=float(payload.get("train_pct", 70.0)),
                optimize_budget=int(payload.get("budget", 40)),
                settings=settings,
                fitness_mode=payload.get("fitness", "composite"),
                seed=int(payload.get("seed", 42)),
                progress=progress,
            )
        return {"job_id": jobs.submit("walkforward", work)}

    # ----------------------------------------------------------- monte carlo
    @app.post("/api/montecarlo")
    def run_montecarlo(payload: dict[str, Any]) -> dict[str, Any]:
        rid = payload.get("result_id")
        if rid:
            row = db.get_result(rid)
            pnls = [t["pnl"] for t in row["payload"].get("trades", [])]
            initial = float(payload.get("initial_capital", 10_000.0))
        else:
            pnls = [float(x) for x in payload.get("trade_pnls", [])]
            initial = float(payload.get("initial_capital", 10_000.0))
        try:
            return monte_carlo(
                pnls, initial_capital=initial,
                simulations=int(payload.get("simulations", 1000)),
                ruin_threshold_pct=float(payload.get("ruin_threshold_pct", 30.0)),
                seed=int(payload.get("seed", 42)),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ------------------------------------------------------------- portfolio
    @app.post("/api/portfolio")
    def portfolio(payload: dict[str, Any]) -> dict[str, Any]:
        ids = payload.get("result_ids") or []
        components = []
        for rid in ids:
            try:
                row = db.get_result(rid)
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            p = row["payload"]
            components.append({
                "name": row["strategy_name"],
                "equity": p.get("equity", []),
                "timestamps": p.get("timestamps", []),
                "initial_capital": p.get("equity", [10_000.0])[0] if p.get("equity") else 10_000.0,
            })
        try:
            return build_portfolio(components, payload.get("weights"),
                                   float(payload.get("initial_capital", 10_000.0)))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ------------------------------------------------------------ strategies
    @app.get("/api/strategies")
    def list_strategies() -> list[dict[str, Any]]:
        return db.list_strategies()

    @app.post("/api/strategies")
    def save_strategy(payload: dict[str, Any]) -> dict[str, str]:
        spec = _spec(payload)
        # el contexto viaja tal cual lo mandó la UI: sin instrumento, timeframe
        # y costos, una estrategia guardada no se puede volver a exportar
        meta = dict(payload.get("meta") or {})
        if payload.get("dataset_id"):
            meta.setdefault("dataset_id", payload["dataset_id"])
            try:
                meta.setdefault("dataset_name", db.get_dataset(payload["dataset_id"])["name"])
            except KeyError:
                pass
        sid = db.save_strategy(str(payload.get("name") or spec.name), spec.to_dict(),
                               strategy_id=payload.get("id"),
                               notes=str(payload.get("notes", "")),
                               meta=meta)
        return {"id": sid}

    @app.delete("/api/strategies/{sid}")
    def delete_strategy(sid: str) -> dict[str, str]:
        db.delete_strategy(sid)
        return {"status": "deleted"}

    # --------------------------------------------------------------- results
    @app.get("/api/results")
    def list_results() -> list[dict[str, Any]]:
        return db.list_results()

    @app.get("/api/results/{rid}")
    def get_result(rid: str) -> dict[str, Any]:
        try:
            return db.get_result(rid)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.delete("/api/results/{rid}")
    def delete_result(rid: str) -> dict[str, str]:
        db.delete_result(rid)
        return {"status": "deleted"}

    # --------------------------------------------------------------- reports
    def _result_or_404(rid: str) -> dict[str, Any]:
        try:
            return db.get_result(rid)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/results/{rid}/report.html")
    def report_html(rid: str) -> HTMLResponse:
        row = _result_or_404(rid)
        return HTMLResponse(html_report(row["payload"], row["strategy_name"],
                                        row["dataset_name"]))

    @app.get("/api/results/{rid}/trades.csv")
    def report_trades(rid: str) -> PlainTextResponse:
        row = _result_or_404(rid)
        return PlainTextResponse(trades_csv(row["payload"]), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="trades_{rid}.csv"'})

    @app.get("/api/results/{rid}/metrics.csv")
    def report_metrics(rid: str) -> PlainTextResponse:
        row = _result_or_404(rid)
        return PlainTextResponse(metrics_csv(row["payload"]), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="metrics_{rid}.csv"'})

    @app.get("/api/results/{rid}/report.xlsx")
    def report_excel(rid: str) -> Response:
        row = _result_or_404(rid)
        data = excel_report(row["payload"], row["strategy_name"])
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="report_{rid}.xlsx"'})

    @app.post("/api/export/mql5")
    def export_mql5_endpoint(payload: dict[str, Any], request: Request) -> PlainTextResponse:
        """Render a mined strategy as a compilable MQL5 Expert Advisor.

        Minar y mirar resultados es libre; bajarse el archivo pide cuenta. Es
        el momento en que el usuario se lleva algo, y el unico donde la
        friccion del registro se justifica."""
        _exigir_para_descargar(request)
        spec = _spec(payload)
        name = str(payload.get("name") or "QF_Strategy").replace(" ", "_")
        ds_name = ""
        if payload.get("dataset_id"):
            try:
                ds_name = db.get_dataset(payload["dataset_id"])["name"]
            except KeyError:
                ds_name = ""
        code = export_mql5(spec, ea_name=name, symbol_hint=ds_name,
                           timeframe_hint=str(payload.get("timeframe") or ""),
                           metrics=payload.get("metrics") or None)
        return PlainTextResponse(code, media_type="text/plain",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="{name}.mq5"'})

    @app.post("/api/export/pine")
    def export_pine_endpoint(payload: dict[str, Any], request: Request) -> PlainTextResponse:
        """Render a mined strategy as a TradingView Pine Script v5 strategy."""
        _exigir_para_descargar(request)
        spec = _spec(payload)
        name = str(payload.get("name") or "QF Strategy")
        ds_name = ""
        if payload.get("dataset_id"):
            try:
                ds_name = db.get_dataset(payload["dataset_id"])["name"]
            except KeyError:
                ds_name = ""
        code = export_pine(spec, name=name, symbol_hint=ds_name,
                           timeframe_hint=str(payload.get("timeframe") or ""),
                           metrics=payload.get("metrics") or None)
        return PlainTextResponse(code, media_type="text/plain",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="{name.replace(" ", "_")}.pine"'})

    # ------------------------------------------------------------------- UI
    # The UI is edited in place and served locally, so a cached copy is always
    # wrong and never a win — a stale app.js silently shows an older QuantForge.
    # Asset URLs carry the file's mtime, which makes the browser refetch the
    # moment a file changes and cache it happily in between.
    _NO_CACHE = {"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"}

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        html = (UI_DIR / "index.html").read_text(encoding="utf-8")
        for asset in ("app.js", "charts.js", "styles.css"):
            path = UI_DIR / asset
            if path.exists():
                html = html.replace(f"/static/{asset}",
                                    f"/static/{asset}?v={int(path.stat().st_mtime)}")
        return HTMLResponse(html, headers=_NO_CACHE)

    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

    @app.exception_handler(Exception)
    async def unhandled(request, exc):  # pragma: no cover
        return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})

    return app


app = create_app()
