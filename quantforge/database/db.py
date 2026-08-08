"""SQLite persistence for datasets, strategies and backtest results.

Specs and results are stored as JSON blobs — the schema stays trivial and the
domain models remain the single source of truth.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    rows INTEGER NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    google_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    picture TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    spec TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    strategy_id TEXT,
    strategy_name TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'backtest',
    payload TEXT NOT NULL,
    created TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Database:
    """Thread-safe wrapper around a single SQLite file."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    # ---------------------------------------------------------------- usuarios
    def upsert_user(self, sub: str, email: str, name: str = "",
                    picture: str = "") -> dict[str, Any]:
        """Busca por el `sub` de Google y actualiza, o crea si es la primera vez.

        La clave es el `sub`, nunca el mail: un usuario puede cambiar su
        dirección, y una dirección liberada puede terminar en otra cuenta.
        """
        filas = self._rows("SELECT * FROM users WHERE google_sub=?", (sub,))
        if filas:
            uid = filas[0]["id"]
            self._exec(
                "UPDATE users SET email=?, name=?, picture=?, last_seen=? WHERE id=?",
                (email, name, picture, _now(), uid))
        else:
            uid = _new_id()
            self._exec(
                "INSERT INTO users (id, google_sub, email, name, picture, created, last_seen) "
                "VALUES (?,?,?,?,?,?,?)",
                (uid, sub, email, name, picture, _now(), _now()))
        return self.get_user(uid)

    def get_user(self, uid: str) -> dict[str, Any]:
        filas = self._rows("SELECT * FROM users WHERE id=?", (uid,))
        if not filas:
            raise KeyError(f"User {uid} not found")
        return filas[0]

    def count_users(self) -> int:
        return int(self._rows("SELECT COUNT(*) AS n FROM users")[0]["n"])

    def _migrate(self) -> None:
        """Additive column migrations for workspaces created by older builds."""
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(datasets)")}
        if "last_close" not in have:
            self._conn.execute("ALTER TABLE datasets ADD COLUMN last_close REAL")
        # Una estrategia guardada sin su contexto no sirve para nada: el spec
        # dice qué reglas usa, pero no sobre qué instrumento se encontró, con
        # qué timeframe, qué costos ni qué rindió. Sin eso no se puede volver a
        # exportar ni comparar contra otra.
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(strategies)")}
        if "meta" not in have:
            self._conn.execute(
                "ALTER TABLE strategies ADD COLUMN meta TEXT NOT NULL DEFAULT '{}'")

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _rows(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------- datasets
    def insert_dataset(self, name: str, source: str, rows: int,
                       start: str, end: str, timeframe: str,
                       last_close: float | None = None) -> str:
        ds_id = _new_id()
        self._exec(
            "INSERT INTO datasets (id, name, source, rows, start, end, timeframe,"
            " created, last_close) VALUES (?,?,?,?,?,?,?,?,?)",
            (ds_id, name, source, rows, start, end, timeframe, _now(), last_close),
        )
        return ds_id

    def get_dataset(self, ds_id: str) -> dict[str, Any]:
        rows = self._rows("SELECT * FROM datasets WHERE id=?", (ds_id,))
        if not rows:
            raise KeyError(f"Dataset {ds_id} not found")
        return rows[0]

    def list_datasets(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM datasets ORDER BY created DESC")

    def delete_dataset(self, ds_id: str) -> None:
        self._exec("DELETE FROM datasets WHERE id=?", (ds_id,))

    # ----------------------------------------------------------- strategies
    def save_strategy(self, name: str, spec: dict[str, Any],
                      strategy_id: str | None = None, notes: str = "",
                      meta: dict[str, Any] | None = None) -> str:
        """``meta`` guarda el contexto: instrumento, timeframe, costos, riesgo
        y las métricas que tenía al guardarla. Es lo que permite re-exportarla
        o compararla meses después sin volver a minar."""
        blob = json.dumps(meta or {})
        if strategy_id:
            self._exec(
                "UPDATE strategies SET name=?, spec=?, notes=?, meta=?, updated=? WHERE id=?",
                (name, json.dumps(spec), notes, blob, _now(), strategy_id),
            )
            return strategy_id
        sid = _new_id()
        self._exec(
            "INSERT INTO strategies (id, name, spec, notes, created, updated, meta) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, name, json.dumps(spec), notes, _now(), _now(), blob),
        )
        return sid

    def get_strategy(self, sid: str) -> dict[str, Any]:
        rows = self._rows("SELECT * FROM strategies WHERE id=?", (sid,))
        if not rows:
            raise KeyError(f"Strategy {sid} not found")
        row = rows[0]
        row["spec"] = json.loads(row["spec"])
        row["meta"] = json.loads(row.get("meta") or "{}")
        return row

    def list_strategies(self) -> list[dict[str, Any]]:
        rows = self._rows(
            "SELECT id, name, notes, created, updated, spec, meta "
            "FROM strategies ORDER BY updated DESC")
        for r in rows:
            r["spec"] = json.loads(r["spec"])
            r["meta"] = json.loads(r.get("meta") or "{}")
        return rows

    def delete_strategy(self, sid: str) -> None:
        self._exec("DELETE FROM strategies WHERE id=?", (sid,))

    # -------------------------------------------------------------- results
    def save_result(self, strategy_name: str, dataset_id: str, dataset_name: str,
                    payload: dict[str, Any], kind: str = "backtest",
                    strategy_id: str | None = None) -> str:
        rid = _new_id()
        self._exec(
            "INSERT INTO results VALUES (?,?,?,?,?,?,?,?)",
            (rid, strategy_id, strategy_name, dataset_id, dataset_name,
             kind, json.dumps(payload), _now()),
        )
        return rid

    def get_result(self, rid: str) -> dict[str, Any]:
        rows = self._rows("SELECT * FROM results WHERE id=?", (rid,))
        if not rows:
            raise KeyError(f"Result {rid} not found")
        row = rows[0]
        row["payload"] = json.loads(row["payload"])
        return row

    def list_results(self, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if kind:
            rows = self._rows(
                "SELECT id, strategy_id, strategy_name, dataset_id, dataset_name, kind, created "
                "FROM results WHERE kind=? ORDER BY created DESC LIMIT ?", (kind, limit))
        else:
            rows = self._rows(
                "SELECT id, strategy_id, strategy_name, dataset_id, dataset_name, kind, created "
                "FROM results ORDER BY created DESC LIMIT ?", (limit,))
        return rows

    def delete_result(self, rid: str) -> None:
        self._exec("DELETE FROM results WHERE id=?", (rid,))
