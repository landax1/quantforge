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
CREATE TABLE IF NOT EXISTS corridas (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    dataset_id TEXT NOT NULL DEFAULT '',
    dataset_name TEXT NOT NULL DEFAULT '',
    timeframe TEXT NOT NULL DEFAULT '',
    seed INTEGER,
    tested INTEGER NOT NULL DEFAULT 0,
    encontradas INTEGER NOT NULL DEFAULT 0,
    elapsed REAL NOT NULL DEFAULT 0,
    ended TEXT NOT NULL DEFAULT '',
    contexto TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS operaciones (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    cuando TEXT NOT NULL,
    accion TEXT NOT NULL DEFAULT '',
    lado INTEGER,
    cantidad REAL,
    precio REAL,
    ganancia REAL,
    motivo TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_operaciones_estrategia
    ON operaciones (strategy_id, cuando);
CREATE TABLE IF NOT EXISTS compartidas (
    codigo TEXT PRIMARY KEY,
    secreto TEXT NOT NULL,
    doc TEXT NOT NULL,
    created TEXT NOT NULL,
    apagada INTEGER NOT NULL DEFAULT 0,
    vistas INTEGER NOT NULL DEFAULT 0,
    ip TEXT NOT NULL DEFAULT ''
);
-- EL SECRETO NO PUEDE VIVIR SÓLO EN EL NAVEGADOR.
--
-- Un enlace compartido se apaga con su secreto, y el secreto se guardaba
-- únicamente en `localStorage`. Vaciar el navegador —o abrir la aplicación en
-- otro— dejaba una página PUBLICADA en internet que su propio autor ya no
-- podía bajar. Acá vive la copia que sobrevive a eso: el archivo del espacio
-- de trabajo, en la máquina de quien compartió (3 de septiembre de 2026).
CREATE TABLE IF NOT EXISTS enlaces_propios (
    codigo TEXT PRIMARY KEY,
    secreto TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    nombre TEXT NOT NULL DEFAULT '',
    nivel TEXT NOT NULL DEFAULT '',
    creado TEXT NOT NULL,
    apagado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS banco (
    id TEXT PRIMARY KEY,
    corrida_id TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    nombre TEXT NOT NULL,
    puesto INTEGER NOT NULL DEFAULT 0,
    spec TEXT NOT NULL,
    fila TEXT NOT NULL,
    score REAL, cagr REAL, pf REAL, dd REAL,
    trades INTEGER, months REAL, oos_ratio REAL,
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
        for tabla in ("strategies", "results", "corridas", "banco"):
            cur = self._exec(f"UPDATE {tabla} SET user_id=? WHERE user_id=''", (uid,))
            hecho[tabla] = cur.rowcount
        return hecho

    def _migrate(self) -> None:
        """Additive column migrations for workspaces created by older builds."""
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(datasets)")}
        if "last_close" not in have:
            self._conn.execute("ALTER TABLE datasets ADD COLUMN last_close REAL")
        # EN QUE RELOJ ESTAN LAS FECHAS DE ESTE HISTORICO.
        #
        # Hasta acá el reloj vivía en dos lugares que no se hablaban: una
        # constante para los datos de Dukascopy y un desplegable global que el
        # usuario elegía a mano para el EA. Si no coincidían, la estrategia se
        # minaba en una franja horaria y el robot operaba en otra — y eso no
        # falla en ningún lado, sólo hace que los números no se parezcan.
        #
        # Con dos fuentes deja de ser sostenible: las velas de MetaTrader
        # vienen en la hora del servidor de donde salieron (medido,
        # MetaQuotes-Demo va en UTC+3) y las de Dukascopy en UTC. El reloj es
        # una propiedad DEL HISTORICO, así que viaja con él.
        #
        # NULL significa "no se sabe", que no es lo mismo que 0. Los datasets
        # viejos quedan en NULL a propósito: nadie midió su reloj.
        if "utc_offset" not in have:
            self._conn.execute("ALTER TABLE datasets ADD COLUMN utc_offset REAL")
        # Una estrategia guardada sin su contexto no sirve para nada: el spec
        # dice qué reglas usa, pero no sobre qué instrumento se encontró, con
        # qué timeframe, qué costos ni qué rindió. Sin eso no se puede volver a
        # exportar ni comparar contra otra.
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(strategies)")}
        if "meta" not in have:
            self._conn.execute(
                "ALTER TABLE strategies ADD COLUMN meta TEXT NOT NULL DEFAULT '{}'")
        # El resultado de haberla puesto a prueba. Antes vivía en la pantalla:
        # se corría el walk-forward, salía un veredicto, y al cambiar de sección
        # se perdía. Así la lista de estrategias no podía decir cuáles están
        # probadas y cuáles no, que es justamente lo que le da un objetivo a la
        # aplicación. Guardado acá, el estado sobrevive a cerrar el programa.
        if "validacion" not in have:
            self._conn.execute(
                "ALTER TABLE strategies ADD COLUMN validacion TEXT NOT NULL DEFAULT '{}'")
        # EN QUE PUNTO DEL CAMINO ESTA. Hasta ahora todo lo guardado vivia en
        # la misma lista: la que acabas de encontrar, la que corriste seis
        # meses en demo y la que se fundio. Mezcladas no se puede decidir nada.
        #
        # El default es "nueva" y no vacio porque las que ya existian se
        # guardaron antes de que esto existiera: nadie las valido ni las
        # corrio, asi que nuevas es lo que son. Con eso no hay que migrar nada.
        if "estado" not in have:
            self._conn.execute(
                "ALTER TABLE strategies ADD COLUMN estado TEXT NOT NULL "
                "DEFAULT 'nueva'")
        # La autopsia: por que se retiro y de donde venia. Un cementerio sin
        # esto es una lista de nombres, y la proxima con el mismo problema se
        # enciende igual.
        if "retiro" not in have:
            self._conn.execute(
                "ALTER TABLE strategies ADD COLUMN retiro TEXT NOT NULL "
                "DEFAULT '{}'")
        # LO QUE EL SEMAFORO RECUERDA. Sin esto el ciclo no puede retirar
        # nada: la rama de retiro pregunta cuántas vueltas lleva en naranja, y
        # una racha no se puede contar si cada vuelta empieza de cero.
        if "vigilancia" not in have:
            self._conn.execute(
                "ALTER TABLE strategies ADD COLUMN vigilancia TEXT NOT NULL "
                "DEFAULT '{}'")
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
        # Cuántas encontró la corrida al archivarse. Sin esto no se puede
        # distinguir una búsqueda que no encontró nada de una cuyas filas se
        # borraron después, y son dos cosas muy distintas de leer en el banco.
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(corridas)")}
        if "encontradas" not in have:
            self._conn.execute(
                "ALTER TABLE corridas ADD COLUMN encontradas INTEGER NOT NULL DEFAULT 0")
        # El banco es la tabla que crece: miles de filas contra las decenas de
        # las otras. Se lee siempre por dueño y casi siempre por corrida.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_banco_corrida ON banco(user_id, corrida_id)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_corridas_user ON corridas(user_id, created DESC)")

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
                       user_id: str | None = None,
                       utc_offset: float | None = None) -> str:
        """`utc_offset` son las horas que el reloj de estas fechas adelanta
        respecto de UTC. None es "no se sabe", y no es lo mismo que 0."""
        ds_id = _new_id()
        self._exec(
            "INSERT INTO datasets (id, name, source, rows, start, end, timeframe,"
            " created, last_close, user_id, utc_offset)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ds_id, name, source, rows, start, end, timeframe, _now(), last_close,
             user_id or "", utc_offset),
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
        row["validacion"] = json.loads(row.get("validacion") or "{}")
        row["retiro"] = json.loads(row.get("retiro") or "{}") or None
        return row

    def list_strategies(self, user_id: str | None = None) -> list[dict[str, Any]]:
        cond, args = self._de(user_id)
        rows = self._rows(
            "SELECT id, name, notes, created, updated, spec, meta, validacion, "
            "estado, retiro, vigilancia "
            f"FROM strategies WHERE 1=1{cond} ORDER BY updated DESC", args)
        for r in rows:
            r["spec"] = json.loads(r["spec"])
            r["meta"] = json.loads(r.get("meta") or "{}")
            r["validacion"] = json.loads(r.get("validacion") or "{}")
            r["retiro"] = json.loads(r.get("retiro") or "{}") or None
            r["vigilancia"] = json.loads(r.get("vigilancia") or "{}")
        return rows

    # --------------------------------------------- lo que operó de verdad

    def anotar_operacion(self, sid: str, fila: dict[str, Any]) -> None:
        """Una línea del registro del bot, para que sobreviva a cerrar la app.

        ==================================================================
        SIN ESTO EL SEMAFORO NO PUEDE OPINAR MAÑANA SOBRE LO DE HOY.
        ==================================================================

        El registro del bot vive en memoria mientras corre. Al cerrar la
        aplicación se pierde, y con él la única evidencia de cómo le fue en
        vivo — que es exactamente lo que el semáforo compara contra el
        backtest. Guardado acá, una estrategia puede acumular sus treinta
        operaciones a lo largo de semanas y varias sesiones.

        NO FALLA SI NO PUEDE ESCRIBIR. Esto se llama desde el bucle del bot, y
        un error de base de datos no puede tumbar al que está operando: perder
        una línea del registro es malo, quedarse con una posición abierta
        porque el bot se murió anotando es peor.
        """
        try:
            self._exec(
                "INSERT INTO operaciones (id, strategy_id, cuando, accion, "
                "lado, cantidad, precio, ganancia, motivo, payload) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (_new_id(), sid, str(fila.get("cuando") or _now()),
                 str(fila.get("accion") or ""), fila.get("lado"),
                 fila.get("cantidad"), fila.get("precio"), fila.get("ganancia"),
                 str(fila.get("motivo") or ""), json.dumps(fila, default=str)))
        except Exception:                                      # noqa: BLE001
            pass

    def operaciones(self, sid: str, limite: int = 5_000) -> list[dict[str, Any]]:
        """El registro guardado de esa estrategia, de vieja a nueva.

        En ese orden porque el semáforo cuenta operaciones cerradas y compara
        contra la línea base: al revés daría el mismo profit factor, pero
        cualquier cosa que mire una racha leería la historia para atrás.
        """
        rows = self._rows(
            "SELECT cuando, accion, lado, cantidad, precio, ganancia, motivo "
            "FROM operaciones WHERE strategy_id=? ORDER BY cuando ASC, rowid ASC "
            "LIMIT ?", (sid, int(limite)))
        return rows

    def guardar_vigilancia(self, sid: str, datos: dict[str, Any],
                           user_id: str | None = None) -> None:
        """Lo que el semáforo recuerda de esa estrategia.

        No toca `updated`: que el semáforo opine no modifica la estrategia, y
        si lo tocara, cada vuelta del ciclo la mandaría al tope de la lista y
        el orden por fecha dejaría de significar cuándo la guardaste.
        """
        cond, args = self._de(user_id)
        self._exec(f"UPDATE strategies SET vigilancia=? WHERE id=?{cond}",
                   (json.dumps(datos), sid) + args)

    def guardar_validacion(self, sid: str, datos: dict[str, Any],
                           user_id: str | None = None) -> None:
        """Deja registrado cómo le fue a una estrategia en las pruebas.

        No toca `updated`: haber probado una estrategia no la modifica, y si
        lo tocara, cada prueba la mandaría al tope de la lista y el orden por
        fecha dejaría de significar cuándo la guardaste.
        """
        cond, args = self._de(user_id)
        cur = self._exec(f"UPDATE strategies SET validacion=? WHERE id=?{cond}",
                         (json.dumps(datos), sid) + args)
        if cur.rowcount == 0:
            raise KeyError(f"Strategy {sid} not found")

    def mover_estado(self, sid: str, cambio: dict[str, Any],
                     user_id: str | None = None) -> None:
        """Mueve una estrategia de estado. `cambio` viene de `estados.mover`.

        La VALIDACION del movimiento no vive acá: vive en `botiquant.estados`,
        que no sabe de bases de datos y por eso se puede probar entero sin
        una. Acá solo se guarda lo que aquel ya aprobo.

        Tampoco toca `updated`: mover de estado no modifica la estrategia, y
        si lo tocara, cada movimiento la mandaria al tope de la lista.
        """
        cond, args = self._de(user_id)
        cur = self._exec(
            f"UPDATE strategies SET estado=?, retiro=? WHERE id=?{cond}",
            (cambio["estado"], json.dumps(cambio.get("retiro") or {}), sid) + args)
        if cur.rowcount == 0:
            raise KeyError(f"Strategy {sid} not found")

    def borrar_validacion(self, sid: str, user_id: str | None = None) -> None:
        self.guardar_validacion(sid, {}, user_id)

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

    # ---------------------------------------------------------------- banco
    #: Tope de estrategias vivas en el banco. No es una cifra de rendimiento de
    #: SQLite —aguanta millones— sino de la persona: pasadas unas miles, el
    #: banco deja de ser una mesa de trabajo y pasa a ser un depósito que nadie
    #: revisa. Lo que valía la pena se copia a Mis estrategias, que no tiene
    #: tope y no se poda nunca.
    TOPE_BANCO = 2000
    #: Y de corridas, que es el eje por el que se navega.
    TOPE_CORRIDAS = 40

    #: Columnas por las que se puede ordenar, y hacia dónde va el primer clic.
    #: Ordenar en SQL y no en Python no es purismo: con el banco lleno, ordenar
    #: afuera obliga a traer las 2000 filas con su JSON entero para devolver 50.
    ORDENES = {
        "score": ("score", "DESC"), "cagr": ("cagr", "DESC"),
        "pf": ("pf", "DESC"), "dd": ("dd", "ASC"),
        "trades": ("trades", "DESC"), "months": ("months", "DESC"),
        "oos": ("oos_ratio", "DESC"), "puesto": ("puesto", "ASC"),
    }

    @staticmethod
    def _num(v: Any) -> float | None:
        """NaN e infinito no sobreviven a SQLite como números ordenables."""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f and abs(f) != float("inf") else None

    def guardar_corrida(self, *, dataset_id: str, dataset_name: str, timeframe: str,
                        seed: int | None, tested: int, elapsed: float, ended: str,
                        contexto: dict[str, Any], filas: list[dict[str, Any]],
                        user_id: str | None = None) -> dict[str, Any]:
        """Archiva una corrida terminada con todo su databank.

        Es lo que convierte el databank en un banco: hasta acá las estrategias
        vivían en el snapshot del trabajo en curso y arrancar otra búsqueda las
        borraba sin avisar.

        El ``contexto`` viaja entero a propósito. Una fila del banco sin su
        instrumento, su timeframe y su riesgo es un número sin unidad: 40% anual
        al 1% de riesgo y 40% al 3% no son la misma estrategia ni se comparan.
        """
        cid = _new_id()
        dueno = user_id or ""
        ahora = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO corridas (id, user_id, created, dataset_id, dataset_name,"
                " timeframe, seed, tested, encontradas, elapsed, ended, contexto)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, dueno, ahora, dataset_id, dataset_name, timeframe, seed,
                 int(tested), len(filas), float(elapsed), ended, json.dumps(contexto)))
            for i, fila in enumerate(filas):
                m = fila.get("metrics") or {}
                self._conn.execute(
                    "INSERT INTO banco (id, corrida_id, user_id, nombre, puesto, spec,"
                    " fila, score, cagr, pf, dd, trades, months, oos_ratio, created)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (_new_id(), cid, dueno, str(fila.get("name") or "—"), i,
                     json.dumps(fila.get("spec") or {}), json.dumps(fila),
                     self._num(fila.get("score")), self._num(m.get("cagr_pct")),
                     self._num(m.get("profit_factor")), self._num(m.get("max_drawdown_pct")),
                     self._num(m.get("trades")), self._num(m.get("months_positive_pct")),
                     self._num(fila.get("oos_ratio")), ahora))
            self._conn.commit()
        podadas = self._podar(dueno, proteger=cid)
        return {"id": cid, "guardadas": len(filas), "podadas": podadas}

    def _podar(self, user_id: str, proteger: str = "") -> int:
        """Deja el banco dentro del tope tirando las corridas más viejas.

        Se poda por corrida ENTERA y nunca por fila suelta. Media corrida es
        peor que ninguna: el puesto 1 de 25 significa algo, y el puesto 1 de las
        9 que sobrevivieron a una poda significa otra cosa que nadie pidió.
        """
        cond, args = self._de(user_id, "c.user_id")
        corridas = self._rows(
            "SELECT c.id, (SELECT COUNT(*) FROM banco b WHERE b.corrida_id=c.id) AS n"
            f" FROM corridas c WHERE 1=1{cond} ORDER BY c.created DESC, c.rowid DESC", args)
        total = sum(c["n"] for c in corridas)
        quedan = len(corridas)
        muertas: list[str] = []
        # de la más vieja hacia adelante, y la recién guardada nunca se toca
        for c in [x for x in reversed(corridas) if x["id"] != proteger]:
            if total <= self.TOPE_BANCO and quedan <= self.TOPE_CORRIDAS:
                break
            muertas.append(c["id"])
            total -= c["n"]
            quedan -= 1
        for cid in muertas:
            self._exec("DELETE FROM banco WHERE corrida_id=?", (cid,))
            self._exec("DELETE FROM corridas WHERE id=?", (cid,))
        return len(muertas)

    def list_corridas(self, user_id: str | None = None) -> list[dict[str, Any]]:
        cond, args = self._de(user_id, "c.user_id")
        filas = self._rows(
            "SELECT c.*, (SELECT COUNT(*) FROM banco b WHERE b.corrida_id=c.id) AS n"
            f" FROM corridas c WHERE 1=1{cond} ORDER BY c.created DESC, c.rowid DESC", args)
        for f in filas:
            f["contexto"] = json.loads(f.get("contexto") or "{}")
        return filas

    @staticmethod
    def _entre_corridas(corrida_ids) -> tuple[str, tuple]:
        """Recorte a un conjunto de corridas. `None` es "todas"; una lista
        vacía es "ninguna", y tiene que dar cero filas, no todas."""
        if corrida_ids is None:
            return "", ()
        ids = [str(c) for c in corrida_ids]
        if not ids:
            return " AND 0", ()
        marcas = ",".join("?" * len(ids))
        return f" AND corrida_id IN ({marcas})", tuple(ids)

    def contar_banco(self, user_id: str | None = None, *,
                     corrida_ids=None) -> int:
        cond, args = self._de(user_id)
        c2, a2 = self._entre_corridas(corrida_ids)
        return int(self._rows(
            f"SELECT COUNT(*) AS n FROM banco WHERE 1=1{cond}{c2}", args + a2)[0]["n"])

    def list_banco(self, *, corrida_id: str | None = None, orden: str = "puesto",
                   desc: bool | None = None, limite: int = 200, desde: int = 0,
                   user_id: str | None = None, corrida_ids=None) -> list[dict[str, Any]]:
        """Filas del banco, ordenadas en la base.

        ``corrida_ids`` recorta a un conjunto de corridas: es como la pantalla
        muestra sólo las de la sección elegida (CFDs o cripto) sin perder la
        paginación, que se hace acá y no en el navegador.

        Sin ``corrida_id`` devuelve el banco entero, que es la vista que permite
        comparar corridas — con el cuidado de que ahí las columnas que dependen
        del riesgo (anual, caída) no son comparables entre corridas de distinta
        configuración. Esa advertencia la da la UI; acá sólo se ordena.
        """
        col, natural = self.ORDENES.get(orden) or self.ORDENES["puesto"]
        sentido = natural if desc is None else ("DESC" if desc else "ASC")
        cond, args = self._de(user_id)
        if corrida_id:
            cond += " AND corrida_id=?"
            args = args + (corrida_id,)
        c2, a2 = self._entre_corridas(corrida_ids)
        cond, args = cond + c2, args + a2
        # Las filas sin dato van al fondo se ordene como se ordene: pedir "las
        # mejores por fuera de muestra" no puede arrancar con las que no tienen.
        filas = self._rows(
            f"SELECT * FROM banco WHERE 1=1{cond}"
            f" ORDER BY ({col} IS NULL), {col} {sentido}, puesto ASC"
            " LIMIT ? OFFSET ?", args + (max(1, limite), max(0, desde)))
        salida = []
        for f in filas:
            fila = json.loads(f["fila"])
            fila["banco_id"] = f["id"]
            fila["corrida_id"] = f["corrida_id"]
            fila["puesto"] = f["puesto"]
            salida.append(fila)
        return salida

    def get_banco(self, ids: list[str], user_id: str | None = None) -> list[dict[str, Any]]:
        """Filas puntuales por id, con su corrida al lado.

        Va junto porque quien guarda una fila necesita el contexto de su corrida
        para reconstruir el instrumento y los costos con los que se midió.
        """
        if not ids:
            return []
        cond, args = self._de(user_id, "b.user_id")
        marcas = ",".join("?" * len(ids))
        filas = self._rows(
            "SELECT b.*, c.dataset_id, c.dataset_name, c.timeframe, c.contexto"
            " FROM banco b LEFT JOIN corridas c ON c.id=b.corrida_id"
            f" WHERE b.id IN ({marcas}){cond} ORDER BY b.puesto ASC", tuple(ids) + args)
        for f in filas:
            f["fila"] = json.loads(f["fila"])
            f["contexto"] = json.loads(f.get("contexto") or "{}")
        return filas

    # ------------------------------------- los enlaces que compartió este equipo
    def anotar_enlace(self, codigo: str, secreto: str, url: str = "",
                      nombre: str = "", nivel: str = "") -> None:
        """Guarda el secreto de un enlace propio donde no lo borre el navegador.

        Volver a anotar el mismo código actualiza los datos pero conserva la
        fecha original y el estado de apagado: es el mismo enlace.
        """
        self._exec(
            "INSERT OR REPLACE INTO enlaces_propios "
            "(codigo, secreto, url, nombre, nivel, creado, apagado) "
            "VALUES (?, ?, ?, ?, ?, "
            "  COALESCE((SELECT creado FROM enlaces_propios WHERE codigo = ?), ?), "
            "  COALESCE((SELECT apagado FROM enlaces_propios WHERE codigo = ?), 0))",
            (codigo, secreto, url, nombre, nivel, codigo,
             datetime.now(timezone.utc).isoformat(timespec="seconds"), codigo))

    def enlaces_propios(self) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT codigo, secreto, url, nombre, nivel, creado, apagado "
            "FROM enlaces_propios ORDER BY creado DESC LIMIT 200")

    def marcar_enlace_apagado(self, codigo: str) -> None:
        self._exec("UPDATE enlaces_propios SET apagado = 1 WHERE codigo = ?", (codigo,))

    # ------------------------------------------------- estrategias compartidas
    def crear_compartida(self, doc: dict[str, Any], ip: str = "") -> tuple[str, str]:
        """Guarda una copia congelada de una estrategia y devuelve (código, secreto).

        El código va en el enlace; el secreto sólo lo recibe quien compartió y
        es lo único que permite apagar el enlace. Sin cuentas ni licencias:
        compartir es de cualquiera que tenga la aplicación.
        """
        import secrets as _secrets
        codigo = _secrets.token_urlsafe(6).replace("-", "a").replace("_", "b")[:8]
        secreto = _secrets.token_urlsafe(24)
        with self._lock:
            self._conn.execute(
                "INSERT INTO compartidas (codigo, secreto, doc, created, ip) VALUES (?,?,?,?,?)",
                (codigo, secreto, json.dumps(doc), datetime.now(timezone.utc).isoformat(timespec="seconds"), ip))
            self._conn.commit()
        return codigo, secreto

    def get_compartida(self, codigo: str, *, contar: bool = False) -> dict[str, Any] | None:
        filas = self._rows("SELECT * FROM compartidas WHERE codigo=?", (codigo,))
        if not filas:
            return None
        f = filas[0]
        if contar and not f["apagada"]:
            self._exec("UPDATE compartidas SET vistas=vistas+1 WHERE codigo=?", (codigo,))
        f["doc"] = json.loads(f["doc"])
        return f

    def apagar_compartida(self, codigo: str, secreto: str) -> bool:
        cur = self._exec("UPDATE compartidas SET apagada=1 WHERE codigo=? AND secreto=?",
                         (codigo, secreto))
        return cur.rowcount > 0

    def compartidas_hoy(self, ip: str) -> int:
        hoy = datetime.now(timezone.utc).date().isoformat()
        return int(self._rows(
            "SELECT COUNT(*) AS n FROM compartidas WHERE ip=? AND created LIKE ?",
            (ip, hoy + "%"))[0]["n"])

    def ids_banco_de(self, corrida_id: str, user_id: str | None = None) -> list[str]:
        """Los ids de las filas que dejó una corrida, en su orden de puesto.

        Es lo que el ciclo necesita para guardar lo que acaba de minar sin
        pasar por la pantalla: mina, archiva, y con estos ids las manda a Mis
        estrategias como nuevas.
        """
        cond, args = self._de(user_id, "user_id")
        filas = self._rows(
            f"SELECT id FROM banco WHERE corrida_id=?{cond} ORDER BY puesto ASC",
            (corrida_id,) + args)
        return [str(f["id"]) for f in filas]

    def borrar_banco(self, ids: list[str], user_id: str | None = None) -> int:
        if not ids:
            return 0
        cond, args = self._de(user_id)
        marcas = ",".join("?" * len(ids))
        cur = self._exec(f"DELETE FROM banco WHERE id IN ({marcas}){cond}",
                         tuple(ids) + args)
        return cur.rowcount

    def borrar_corrida(self, cid: str, user_id: str | None = None) -> int:
        cond, args = self._de(user_id)
        self._exec(f"DELETE FROM banco WHERE corrida_id=?{cond}", (cid,) + args)
        cur = self._exec(f"DELETE FROM corridas WHERE id=?{cond}", (cid,) + args)
        return cur.rowcount
