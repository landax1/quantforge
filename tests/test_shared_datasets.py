"""Los instrumentos del catálogo son infraestructura compartida.

En una instalación de un solo usuario, borrar un dataset es asunto suyo. En
una servida a terceros, un clic en "Borrar" deja al resto sin 4,6 millones de
velas que hay que volver a bajar de Dukascopy. Y "Descargar" dispararía esa
bajada desde el servidor a pedido de cualquiera.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import quantforge.api.app as appmod


@pytest.fixture()
def multiuser(tmp_path, monkeypatch):
    """Cliente con la app en modo compartido y un instrumento del catálogo."""
    monkeypatch.setattr(appmod, "MULTIUSER", True)
    app = appmod.create_app(workdir=tmp_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "MULTIUSER", False)
    app = appmod.create_app(workdir=tmp_path)
    with TestClient(app) as c:
        yield c


# el importador exige 100 velas como mínimo, así que se generan 150
CSV = (b"time,open,high,low,close,volume\n" + b"".join(
    (f"2024-01-{1 + i // 24:02d} {i % 24:02d}:00:00,"
     f"{100 + i},{101 + i},{99 + i},{100.5 + i},10\n").encode()
    for i in range(150)))


def _subir(c) -> str:
    r = c.post("/api/datasets/upload",
               files={"file": ("mio.csv", io.BytesIO(CSV), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_meta_announces_shared_mode(multiuser):
    assert multiuser.get("/api/meta").json()["multiuser"] is True


def test_meta_announces_local_mode(local):
    """La UI lo lee para no dibujar botones que van a dar 403."""
    assert local.get("/api/meta").json()["multiuser"] is False


def test_a_shared_instrument_cannot_be_deleted(multiuser, tmp_path):
    """Un dataset que no subió el usuario es de todos."""
    # se fabrica uno como si viniera del catálogo
    r = multiuser.post("/api/datasets/sample", json={"symbol": "SP500", "bars": 600})
    assert r.status_code == 200
    ds_id = r.json()["id"]

    borrado = multiuser.delete(f"/api/datasets/{ds_id}")
    assert borrado.status_code == 403
    assert "compartido" in borrado.json()["detail"]
    # y sigue estando
    assert any(d["id"] == ds_id for d in multiuser.get("/api/datasets").json())


def test_users_can_delete_their_own_upload(multiuser):
    ds_id = _subir(multiuser)
    r = multiuser.delete(f"/api/datasets/{ds_id}")
    assert r.status_code == 200
    assert not any(d["id"] == ds_id for d in multiuser.get("/api/datasets").json())


def test_downloading_from_dukascopy_is_refused_when_shared(multiuser):
    r = multiuser.post("/api/datasets/download", json={"key": "sp500"})
    assert r.status_code == 403
    assert "compartido" in r.json()["detail"]


def test_local_mode_keeps_every_permission(local):
    """En una instalación propia no cambia nada: son tus datos."""
    r = local.post("/api/datasets/sample", json={"symbol": "SP500", "bars": 600})
    ds_id = r.json()["id"]
    assert local.delete(f"/api/datasets/{ds_id}").status_code == 200
