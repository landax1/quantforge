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

    def adoptar_huerfanos(self, uid: str) -> dict[str, int]:
        """Lo que se guardó antes de que existieran las cuentas pasa a ser del
        primer usuario que entra.

        Es para la máquina de quien venía usando esto sin login: sus estrategias
        y sus resultados no tienen dueño y, al activar el registro, quedarían
        invisibles para siempre.

        Sólo corre con el PRIMER usuario, y por eso en un servidor nuevo no hace
        nada: ahí no hay filas viejas que adoptar, y el segundo en entrar nunca
        hereda lo del primero.

        Los instrumentos quedan afuera adrede: sin dueño ya son los compartidos,
        y dárselos a alguien se los sacaría a todos los demás.
        """
        hecho = {}
        for tabla in ("strategies", "results"):
            cur = self._exec(f"UPDATE {tabla} SET user_id=? WHERE user_id=''", (uid,))
            hecho[tabla] = cur.rowcount
        return hecho

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
        # De quién es cada cosa. Cadena vacía = de nadie en particular, que es
        # lo que corresponde en una instalación local: ahí no hay cuentas y todo
        # es del que está sentado adelante. Servido a varios, cada fila lleva el
        # id de su dueño y nadie ve lo del otro.
        for tabla in ("strategies", "results", "datasets"):
            have = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({tabla})")}
            if "user_id" not in have:
                self._conn.execute(
                    f"ALTER TABLE {tabla} ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        # Sin índice, cada listado recorre la tabla entera filtrando por dueño.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_strategies_user ON strategies(user_id)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_results_user ON results(user_id)")

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
    #: Los instrumentos siguen otra regla que las estrategias. Los del catálogo
    #: —22 millones de velas de Dukascopy— son los mismos para todos y no tiene
    #: sentido duplicarlos por cuenta: quedan con dueño vacío y los ve
    #: cualquiera. Lo que sube un usuario es suyo y sólo suyo.
    _VISIBLE = " AND (user_id='' OR user_id=?)"

    def insert_dataset(self, name: str, source: str, rows: int,
                       start: str, end: str, timeframe: str,
                       last_close: float | None = None,
                       user_id: str | None = None) -> str:
        ds_id = _new_id()
        self._exec(
            "INSERT INTO datasets (id, name, source, rows, start, end, timeframe,"
            " created, last_close, user_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ds_id, name, source, rows, start, end, timeframe, _now(), last_close,
             user_id or ""),
        )
        return ds_id

    def get_dataset(self, ds_id: str, user_id: str | None = None) -> dict[str, Any]:
        cond, args = ("", ()) if user_id is None else (self._VISIBLE, (user_id,))
        rows = self._rows(f"SELECT * FROM datasets WHERE id=?{cond}", (ds_id,) + args)
        if not rows:
            raise KeyError(f"Dataset {ds_id} not found")
        return rows[0]

    def list_datasets(self, user_id: str | None = None) -> list[dict[str, Any]]:
        cond, args = ("", ()) if user_id is None else (self._VISIBLE, (user_id,))
        return self._rows(
            f"SELECT * FROM datasets WHERE 1=1{cond} ORDER BY created DESC", args)

    def delete_dataset(self, ds_id: str, user_id: str | None = None) -> None:
        # Acá NO se usa _VISIBLE: ver un instrumento compartido es una cosa y
        # borrárselo a todo el mundo es otra. Sin dueño propio, no se borra.
        cond, args = self._de(user_id)
        self._exec(f"DELETE FROM datasets WHERE id=?{cond}", (ds_id,) + args)

    # ----------------------------------------------------------- strategies
    @staticmethod
    def _de(user_id: str | None, campo: str = "user_id") -> tuple[str, tuple]:
        """Trozo de WHERE que limita una consulta a su dueño.

        ``None`` significa "sin dueños": la instalación local, donde no hay
        cuentas. Cualquier otro valor filtra.

        El filtro va en el SQL y no después de leer a propósito. Filtrar en
        Python funciona para un listado, pero deja pasar el caso que importa:
        pedir una fila por id. Ahí no hay lista que recortar y se devolvería lo
        ajeno.
        """
        if user_id is None:
            return "", ()
        return f" AND {campo}=?", (user_id,)

    def save_strategy(self, name: str, spec: dict[str, Any],
                      strategy_id: str | None = None, notes: str = "",
                      meta: dict[str, Any] | None = None,
                      user_id: str | None = None) -> str:
        """``meta`` guarda el contexto: instrumento, timeframe, costos, riesgo
        y las métricas que tenía al guardarla. Es lo que permite re-exportarla
        o compararla meses después sin volver a minar."""
        blob = json.dumps(meta or {})
        if strategy_id:
            # El dueño va en el WHERE del UPDATE: si no, mandando un id ajeno se
            # le pisa la estrategia a otro.
            cond, args = self._de(user_id)
            cur = self._exec(
                "UPDATE strategies SET name=?, spec=?, notes=?, meta=?, updated=? "
                f"WHERE id=?{cond}",
                (name, json.dumps(spec), notes, blob, _now(), strategy_id) + args,
            )
            if cur.rowcount == 0:
                raise KeyError(f"Strategy {strategy_id} not found")
            return strategy_id
        sid = _new_id()
        self._exec(
            "INSERT INTO strategies (id, name, spec, notes, created, updated, meta, user_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (sid, name, json.dumps(spec), notes, _now(), _now(), blob, user_id or ""),
        )
        return sid

    def get_strategy(self, sid: str, user_id: str | None = None) -> dict[str, Any]:
        cond, args = self._de(user_id)
        rows = self._rows(f"SELECT * FROM strategies WHERE id=?{cond}", (sid,) + args)
        if not rows:
            raise KeyError(f"Strategy {sid} not found")
        row = rows[0]
        row["spec"] = json.loads(row["spec"])
        row["meta"] = json.loads(row.get("meta") or "{}")
        return row

    def list_strategies(self, user_id: str | None = None) -> list[dict[str, Any]]:
        cond, args = self._de(user_id)
        rows = self._rows(
            "SELECT id, name, notes, created, updated, spec, meta "
            f"FROM strategies WHERE 1=1{cond} ORDER BY updated DESC", args)
        for r in rows:
            r["spec"] = json.loads(r["spec"])
            r["meta"] = json.loads(r.get("meta") or "{}")
        return rows

    def delete_strategy(self, sid: str, user_id: str | None = None) -> None:
        cond, args = self._de(user_id)
        self._exec(f"DELETE FROM strategies WHERE id=?{cond}", (sid,) + args)

    # -------------------------------------------------------------- results
    def save_result(self, strategy_name: str, dataset_id: str, dataset_name: str,
                    payload: dict[str, Any], kind: str = "backtest",
                    strategy_id: str | None = None,
                    user_id: str | None = None) -> str:
        rid = _new_id()
        # columnas explícitas: con `VALUES (?,...)` a secas, agregar user_id al
        # esquema rompía el orden en silencio
        self._exec(
            "INSERT INTO results (id, strategy_id, strategy_name, dataset_id, "
            "dataset_name, kind, payload, created, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, strategy_id, strategy_name, dataset_id, dataset_name,
             kind, json.dumps(payload), _now(), user_id or ""),
        )
        return rid

    def get_result(self, rid: str, user_id: str | None = None) -> dict[str, Any]:
        cond, args = self._de(user_id)
        rows = self._rows(f"SELECT * FROM results WHERE id=?{cond}", (rid,) + args)
        if not rows:
            raise KeyError(f"Result {rid} not found")
        row = rows[0]
        row["payload"] = json.loads(row["payload"])
        return row

    def list_results(self, kind: str | None = None, limit: int = 100,
                     user_id: str | None = None) -> list[dict[str, Any]]:
        cond, args = self._de(user_id)
        sql = ("SELECT id, strategy_id, strategy_name, dataset_id, dataset_name, kind, created "
               f"FROM results WHERE 1=1{cond}")
        if kind:
            sql += " AND kind=?"
            args = args + (kind,)
        return self._rows(sql + " ORDER BY created DESC LIMIT ?", args + (limit,))

    def delete_result(self, rid: str, user_id: str | None = None) -> None:
        cond, args = self._de(user_id)
        self._exec(f"DELETE FROM results WHERE id=?{cond}", (rid,) + args)
