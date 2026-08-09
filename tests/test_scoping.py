"""Cada cuenta ve lo suyo y sólo lo suyo.

Casi todo acá prueba que algo NO se puede: un test que sólo comprueba que un
usuario ve sus cosas pasaría igual si viera también las del vecino.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import botiquant.api.app as appmod
from botiquant.auth import sign
from botiquant.database.db import Database

SECRET = "un-secreto-de-prueba-suficientemente-largo-para-hmac"


def _spec() -> dict:
    return {"name": "t", "direction": "long",
            "entry_long": [{"left": {"type": "indicator", "name": "EMA",
                                     "params": {"period": 12}},
                            "op": "cross_above",
                            "right": {"type": "indicator", "name": "EMA",
                                      "params": {"period": 26}}}],
            "entry_short": [], "risk": {"stop_type": "atr", "stop_value": 2}}


@pytest.fixture()
def servidor(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id-123.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secreto-de-prueba")
    monkeypatch.setenv("OAUTH_REDIRECT_URI",
                       "http://localhost:8791/api/auth/google/callback")
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    app = appmod.create_app(workdir=tmp_path)
    db = Database(tmp_path / "botiquant.sqlite")
    ana = db.upsert_user("sub-ana", "ana@example.com", "Ana")
    beto = db.upsert_user("sub-beto", "beto@example.com", "Beto")

    def como(u):
        c = TestClient(app)
        c.cookies.set("bq_session", sign({"uid": u["id"]}, SECRET))
        return c

    with TestClient(app):
        yield como(ana), como(beto), db


def test_one_account_never_sees_another_s_strategies(servidor):
    ana, beto, _ = servidor
    ana.post("/api/strategies", json={"name": "de-ana", "spec": _spec()})

    assert [s["name"] for s in ana.get("/api/strategies").json()] == ["de-ana"]
    assert beto.get("/api/strategies").json() == []


def test_a_known_id_is_not_enough_to_read_someone_else_s_work(servidor):
    """El filtro tiene que estar en la consulta, no en el listado. Si sólo se
    recortara la lista, pedir la fila por id seguiría devolviéndola."""
    ana, beto, db = servidor
    sid = ana.post("/api/strategies",
                   json={"name": "de-ana", "spec": _spec()}).json()["id"]

    with pytest.raises(KeyError):
        db.get_strategy(sid, user_id="el-id-de-beto")
    assert db.get_strategy(sid, user_id=None)["name"] == "de-ana"


def test_deleting_someone_else_s_strategy_does_nothing(servidor):
    ana, beto, db = servidor
    sid = ana.post("/api/strategies",
                   json={"name": "de-ana", "spec": _spec()}).json()["id"]

    beto.delete(f"/api/strategies/{sid}")

    assert [s["name"] for s in ana.get("/api/strategies").json()] == ["de-ana"]


def test_overwriting_someone_else_s_strategy_is_refused(servidor):
    """Guardar con el id de otro es la vía silenciosa: no borra nada, pero le
    reemplaza el contenido."""
    ana, beto, db = servidor
    sid = ana.post("/api/strategies",
                   json={"name": "de-ana", "spec": _spec()}).json()["id"]

    beto.post("/api/strategies",
              json={"id": sid, "name": "secuestrada", "spec": _spec()})

    assert ana.get("/api/strategies").json()[0]["name"] == "de-ana"


def test_results_are_private_too(servidor):
    ana, beto, db = servidor
    ana.post("/api/datasets/sample", json={"symbol": "TEST", "bars": 900})
    ds = ana.get("/api/datasets").json()[0]["id"]
    ana.post("/api/backtest", json={"dataset_id": ds, "spec": _spec(), "save": True})

    assert len(ana.get("/api/results").json()) == 1
    assert beto.get("/api/results").json() == []


def test_an_uploaded_instrument_belongs_to_whoever_uploaded_it(servidor):
    ana, beto, _ = servidor
    ana.post("/api/datasets/sample", json={"symbol": "SOLO-ANA", "bars": 900})

    assert [d["name"] for d in ana.get("/api/datasets").json()] == ["SOLO-ANA (sample)"]
    assert beto.get("/api/datasets").json() == []


def test_catalogue_instruments_stay_shared(servidor, tmp_path):
    """Los 22 millones de velas de Dukascopy son los mismos para todos:
    duplicarlos por cuenta sería absurdo, y esconderlos dejaría a la app sin
    con qué minar."""
    ana, beto, db = servidor
    db.insert_dataset(name="SP500 M1", source="dukascopy", rows=1000,
                      start="2020-01-01", end="2021-01-01", timeframe="1m")

    assert [d["name"] for d in ana.get("/api/datasets").json()] == ["SP500 M1"]
    assert [d["name"] for d in beto.get("/api/datasets").json()] == ["SP500 M1"]


def test_nobody_can_delete_a_shared_instrument(servidor):
    """Un clic de cualquiera dejaría al resto sin el S&P 500: 4,6 millones de
    velas que hay que volver a bajar de Dukascopy."""
    ana, _, db = servidor
    db.insert_dataset(name="SP500 M1", source="dukascopy", rows=1000,
                      start="2020-01-01", end="2021-01-01", timeframe="1m")
    ds = ana.get("/api/datasets").json()[0]["id"]

    r = ana.delete(f"/api/datasets/{ds}")

    assert r.status_code == 403
    assert len(ana.get("/api/datasets").json()) == 1


def test_the_shared_csv_survives_a_refused_delete(servidor, tmp_path):
    """El 403 tiene que cortar ANTES de tocar el disco: si la fila queda y el
    archivo no, el instrumento aparece en la lista y no se puede abrir."""
    ana, _, db = servidor
    ana.post("/api/datasets/sample", json={"symbol": "COMPARTIDO", "bars": 900})
    ds = ana.get("/api/datasets").json()[0]["id"]
    csv = tmp_path / "datasets" / f"{ds}.csv"
    assert csv.exists()
    db._exec("UPDATE datasets SET user_id='' WHERE id=?", (ds,))   # pasa a compartido

    assert ana.delete(f"/api/datasets/{ds}").status_code == 403
    assert csv.exists()


def test_the_sole_account_adopts_what_predates_accounts(tmp_path, monkeypatch):
    """Quien venía usando esto sin login tiene estrategias sin dueño. Al activar
    el registro quedarían invisibles para siempre."""
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    db = Database(tmp_path / "botiquant.sqlite")
    db.save_strategy("vieja", _spec())                    # sin dueño
    db.save_result("vieja", "ds", "DS", {"metrics": {}})

    u = db.upsert_user("sub-1", "yo@example.com", "Yo")
    movido = db.adoptar_huerfanos(u["id"])

    assert movido == {"strategies": 1, "results": 1}
    assert [s["name"] for s in db.list_strategies(u["id"])] == ["vieja"]


def test_an_account_that_predates_the_scoping_still_adopts(tmp_path):
    """El caso real que se llevó puesto el primer intento.

    La condición no puede ser "es el primer login": en la máquina de quien ya
    venía usando esto, la cuenta se creó ANTES de que existiera el scoping, así
    que ese momento ya pasó y no vuelve. Lo que decide es que haya una sola
    cuenta, que es cuando no hay ninguna duda de quién es lo que había.
    """
    db = Database(tmp_path / "botiquant.sqlite")
    u = db.upsert_user("sub-1", "yo@example.com", "Yo")   # la cuenta existe desde antes
    db.save_strategy("vieja", _spec())                    # y esto quedó sin dueño

    assert db.count_users() == 1
    db.adoptar_huerfanos(u["id"])

    assert [s["name"] for s in db.list_strategies(u["id"])] == ["vieja"]


def test_the_second_account_inherits_nothing(tmp_path):
    """La adopción corre sólo con el primero. Si corriera siempre, el segundo
    que entra se llevaría lo del primero."""
    db = Database(tmp_path / "botiquant.sqlite")
    uno = db.upsert_user("sub-1", "uno@example.com", "Uno")
    db.save_strategy("de-uno", _spec(), user_id=uno["id"])

    dos = db.upsert_user("sub-2", "dos@example.com", "Dos")
    assert db.adoptar_huerfanos(dos["id"]) == {"strategies": 0, "results": 0}
    assert db.list_strategies(dos["id"]) == []
    assert [s["name"] for s in db.list_strategies(uno["id"])] == ["de-uno"]


def test_a_local_install_still_sees_everything(tmp_path):
    """Sin cuentas, `None` significa "sin dueños" y nada se filtra: es lo que
    mantiene la instalación local igual que siempre."""
    db = Database(tmp_path / "botiquant.sqlite")
    db.save_strategy("una", _spec())
    db.save_strategy("otra", _spec(), user_id="alguien")

    assert len(db.list_strategies(None)) == 2
