"""El servidor público no calcula nada.

Es la propiedad que sostiene todo el modelo de costos. Si botiquant.com pudiera
minar, la factura crecería con cada usuario y el trabajo de mover el cálculo a
la máquina del usuario no habría servido de nada.
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
def web(tmp_path, monkeypatch):
    """El servidor de botiquant.com: sólo web, con cuentas."""
    monkeypatch.setenv("BQ_SOLO_WEB", "1")
    monkeypatch.setenv("BQ_MULTIUSER", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id-123.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secreto")
    monkeypatch.setenv("OAUTH_REDIRECT_URI",
                       "https://botiquant.com/api/auth/google/callback")
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    import importlib
    importlib.reload(appmod)
    app = appmod.create_app(workdir=tmp_path)
    db = Database(tmp_path / "botiquant.sqlite")
    u = db.upsert_user("sub-1", "yo@example.com", "Yo")
    cliente = TestClient(app)
    cliente.cookies.set("bq_session", sign({"uid": u["id"]}, SECRET))
    with cliente:
        yield cliente
    # El orden acá importa y no es obvio. `SOLO_WEB` se lee UNA vez, al
    # importar el módulo, así que para volver al modo normal hay que
    # recargarlo — pero recargarlo con las variables todavía puestas lo deja
    # otra vez en modo web, y esta vez para el resto de la sesión de tests.
    # pytest deshace el monkeypatch recién DESPUÉS del fixture, así que hay
    # que deshacerlo a mano antes de recargar.
    monkeypatch.undo()
    importlib.reload(appmod)


@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("post", "/api/mine", {"dataset_id": "x"}),
    ("post", "/api/backtest", {"dataset_id": "x", "spec": _spec()}),
    ("post", "/api/generate", {}),
    ("post", "/api/evolve", {}),
    ("post", "/api/optimize", {}),
    ("post", "/api/walkforward", {}),
    ("post", "/api/montecarlo", {}),
    ("post", "/api/portfolio", {}),
    ("post", "/api/export/mql5", {"spec": _spec(), "name": "x"}),
    ("post", "/api/export/pine", {"spec": _spec(), "name": "x"}),
    ("get", "/api/jobs/loquesea", None),
])
def test_computing_is_gone_even_with_a_valid_account(web, metodo, ruta, cuerpo):
    """Tener cuenta no habilita a minar en el servidor. Ni la del dueño.

    Se prueba CON sesión válida a propósito: un test sin sesión daría 401 y
    pasaría igual aunque el endpoint siguiera existiendo.
    """
    r = getattr(web, metodo)(ruta, **({"json": cuerpo} if cuerpo is not None else {}))
    assert r.status_code == 404, f"{ruta} respondió {r.status_code}"
    assert "escritorio" in r.json()["detail"]


def test_the_app_screen_sends_you_to_your_account(web):
    r = web.get("/app", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/cuenta"


def test_what_the_website_is_for_still_works(web):
    """Registrarse y descargar es todo lo que la web tiene que hacer, y tiene
    que seguir haciéndolo."""
    assert web.get("/").status_code == 200
    assert web.get("/cuenta").status_code == 200
    assert web.get("/api/auth/me").status_code == 200
    assert web.get("/api/descarga").status_code == 200


def test_the_licence_is_still_issued(web, monkeypatch):
    """La licencia se firma en el servidor: es lo único de cálculo que queda, y
    es barato."""
    from botiquant.licencia import crear_par_de_claves
    priv, _ = crear_par_de_claves()
    monkeypatch.setenv("BQ_LICENCIA_PRIVADA", priv)

    r = web.get("/api/licencia")
    assert r.status_code == 200
    assert r.json()["token"]
