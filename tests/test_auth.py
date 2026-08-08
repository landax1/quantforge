"""Sesiones firmadas y candado de descarga.

Código de seguridad: se prueba lo que tiene que fallar, no sólo lo que tiene
que andar.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import botiquant.api.app as appmod
from botiquant.auth import SessionError, sign, verify
from botiquant.auth.google import GoogleConfig, authorize_url, new_state

SECRET = "un-secreto-de-prueba-suficientemente-largo-para-hmac"


# ------------------------------------------------------------------ sesiones
def test_a_signed_session_round_trips():
    token = sign({"uid": "abc123"}, SECRET)
    assert verify(token, SECRET)["uid"] == "abc123"


def test_tampering_with_the_payload_is_rejected():
    """Cambiar el id de usuario invalida la firma: es lo único que impide que
    cualquiera se declare otro."""
    token = sign({"uid": "abc123"}, SECRET)
    cuerpo, firma = token.rsplit(".", 1)
    otro = sign({"uid": "victima"}, SECRET).rsplit(".", 1)[0]
    with pytest.raises(SessionError):
        verify(f"{otro}.{firma}", SECRET)


def test_another_secret_cannot_forge_a_session():
    token = sign({"uid": "abc123"}, "secreto-del-atacante")
    with pytest.raises(SessionError):
        verify(token, SECRET)


def test_an_expired_session_is_rejected():
    token = sign({"uid": "abc123"}, SECRET, max_age=-1)
    with pytest.raises(SessionError):
        verify(token, SECRET)


@pytest.mark.parametrize("basura", ["", "sin-punto", "a.b", "....", "x." + "A" * 40])
def test_garbage_never_passes(basura):
    with pytest.raises(SessionError):
        verify(basura, SECRET)


# --------------------------------------------------------------- URL de Google
def test_the_authorize_url_carries_what_google_needs():
    cfg = GoogleConfig("id-123.apps.googleusercontent.com", "secreto",
                       "http://localhost:8791/api/auth/google/callback")
    url = authorize_url(cfg, "estado-abc")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=id-123" in url
    assert "state=estado-abc" in url
    assert "scope=openid+email+profile" in url
    # el secreto NUNCA viaja en la URL del navegador
    assert "secreto" not in url


def test_states_are_unique():
    assert len({new_state() for _ in range(200)}) == 200


# ------------------------------------------------------------------ endpoints
@pytest.fixture()
def sin_auth(tmp_path, monkeypatch):
    """Instalación local: sin credenciales configuradas."""
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OAUTH_REDIRECT_URI",
              "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        yield c


@pytest.fixture()
def con_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id-123.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secreto-de-prueba")
    monkeypatch.setenv("OAUTH_REDIRECT_URI",
                       "http://localhost:8791/api/auth/google/callback")
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        yield c


def _spec() -> dict:
    return {"name": "t", "direction": "long",
            "entry_long": [{"left": {"type": "indicator", "name": "EMA",
                                     "params": {"period": 12}},
                            "op": "cross_above",
                            "right": {"type": "indicator", "name": "EMA",
                                      "params": {"period": 26}}}],
            "entry_short": [], "risk": {"stop_type": "atr", "stop_value": 2}}


def test_local_install_never_asks_for_an_account(sin_auth):
    """Sin login configurado, la app se comporta como siempre."""
    assert sin_auth.get("/api/auth/me").json() == {"configurado": False, "usuario": None}
    r = sin_auth.post("/api/export/mql5", json={"spec": _spec(), "name": "BQ_T"})
    assert r.status_code == 200
    assert "OnTick" in r.text


def test_downloads_require_an_account_when_login_is_on(con_auth):
    r = con_auth.post("/api/export/mql5", json={"spec": _spec(), "name": "BQ_T"})
    assert r.status_code == 401
    assert "cuenta" in r.json()["detail"]
    # y el de TradingView igual
    assert con_auth.post("/api/export/pine",
                         json={"spec": _spec(), "name": "BQ_T"}).status_code == 401


def test_mining_and_results_stay_free(con_auth):
    """El candado va sólo en la descarga: probar la app no pide registro."""
    con_auth.post("/api/datasets/sample", json={"symbol": "TEST", "bars": 900})
    ds = con_auth.get("/api/datasets").json()[0]["id"]
    r = con_auth.post("/api/backtest", json={"dataset_id": ds, "spec": _spec()})
    assert r.status_code == 200
    assert "metrics" in r.json()["result"]


def test_a_forged_cookie_does_not_open_the_door(con_auth):
    con_auth.cookies.set("bq_session", sign({"uid": "cualquiera"}, "otro-secreto"))
    r = con_auth.post("/api/export/mql5", json={"spec": _spec(), "name": "BQ_T"})
    assert r.status_code == 401


def test_a_real_session_can_download(con_auth, tmp_path):
    """Con una sesión válida de un usuario que existe, la descarga sale."""
    from botiquant.database.db import Database

    db = Database(tmp_path / "botiquant.sqlite")
    u = db.upsert_user("sub-google-1", "yo@example.com", "Yo")
    con_auth.cookies.set("bq_session", sign({"uid": u["id"]}, SECRET))
    r = con_auth.post("/api/export/mql5", json={"spec": _spec(), "name": "BQ_T"})
    assert r.status_code == 200, r.text
    assert "OnTick" in r.text


def test_the_callback_refuses_a_mismatched_state(con_auth):
    """Sin el state que salió de acá, la vuelta no se acepta: es lo que corta
    el CSRF de inicio de sesión."""
    r = con_auth.get("/api/auth/google/callback?code=abc&state=inventado",
                     follow_redirects=False)
    assert r.status_code == 303
    assert "login=" in r.headers["location"]
    assert "bq_session" not in r.headers.get("set-cookie", "")


def test_start_redirects_to_google_with_a_state_cookie(con_auth):
    r = con_auth.get("/api/auth/google/start", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://accounts.google.com/")
    assert "bq_oauth_state" in r.headers.get("set-cookie", "")


def test_start_is_unavailable_when_not_configured(sin_auth):
    assert sin_auth.get("/api/auth/google/start",
                        follow_redirects=False).status_code == 503


# --------------------------------------------------------- destino del login
def _estado_firmado(cliente, destino: str) -> str:
    """Corre la ida del login y devuelve el `state` que se generó."""
    r = cliente.get(f"/api/auth/google/start?next={destino}", follow_redirects=False)
    return r.headers["location"].split("state=")[1].split("&")[0]


@pytest.mark.parametrize("hostil", [
    "https://sitio-falso.example/login",     # otro dominio
    "//sitio-falso.example",                 # sin esquema, el navegador lo completa
    "/api/datasets/download",                # interno pero no es una pantalla
    "/app/../../etc",                        # travesía
])
def test_the_login_never_redirects_off_site(con_auth, hostil, monkeypatch):
    """Un login que vuelve a donde le digan es un redirector abierto: el enlace
    sale del dominio real y termina en otro. Es la pieza que hace creíble un
    phishing, así que sólo se aceptan destinos de una lista blanca."""
    estado = _estado_firmado(con_auth, hostil)

    monkeypatch.setattr(appmod, "exchange_code", lambda cfg, code: {"access_token": "t"})
    monkeypatch.setattr(appmod, "fetch_profile", lambda tok: {
        "sub": "sub-1", "email": "yo@example.com", "name": "Yo", "picture": ""})

    r = con_auth.get(f"/api/auth/google/callback?code=abc&state={estado}",
                     follow_redirects=False)
    assert r.headers["location"] == "/?login=ok"


def test_the_login_comes_back_to_the_app_when_it_started_there(con_auth, monkeypatch):
    """Si el usuario entró desde el candado de descarga, devolverlo a la
    portada le hace perder lo que estaba haciendo."""
    estado = _estado_firmado(con_auth, "/app")

    monkeypatch.setattr(appmod, "exchange_code", lambda cfg, code: {"access_token": "t"})
    monkeypatch.setattr(appmod, "fetch_profile", lambda tok: {
        "sub": "sub-2", "email": "yo@example.com", "name": "Yo", "picture": ""})

    r = con_auth.get(f"/api/auth/google/callback?code=abc&state={estado}",
                     follow_redirects=False)
    assert r.headers["location"] == "/app?login=ok"


# ------------------------------------------------------------------ portada
def test_the_landing_is_served_at_the_root(sin_auth):
    r = sin_auth.get("/")
    assert r.status_code == 200
    assert "Botiquant" in r.text
    # la portada, no la aplicación: la aplicación carga su bundle
    assert "/static/app.js" not in r.text


def test_the_app_lives_under_slash_app(sin_auth):
    r = sin_auth.get("/app")
    assert r.status_code == 200
    assert "/static/app.js" in r.text
