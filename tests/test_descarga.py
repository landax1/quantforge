"""La entrega del instalador: quién lo manda y con qué permiso.

El ZIP son cincuenta megas y el servicio corre con UN worker a propósito: el
estado de los logins de Google vive en memoria del proceso, y con dos workers
falla uno de cada dos sin patrón. Servir el archivo desde Python significa que
las descargas compiten con los logins.

``nginx.conf`` ya describía la solución —``X-Accel-Redirect`` y un bloque
``location /interno/``— pero el código nunca emitía esa cabecera. Era
configuración muerta: nginx tenía la puerta y nadie la usaba nunca.

Se prueba acá porque es de las cosas que no se notan hasta que hay gente. Con
tres usuarios anda igual de las dos formas; el día del video, no.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    """Un servidor con un instalador falso ya publicado."""
    monkeypatch.setenv("BQ_WORKSPACE", str(tmp_path / "workspace"))

    def construir(xaccel: str = ""):
        if xaccel:
            monkeypatch.setenv("BQ_XACCEL", xaccel)
        else:
            monkeypatch.delenv("BQ_XACCEL", raising=False)
        import botiquant.api.app as modulo

        importlib.reload(modulo)
        # el instalador vive junto al proyecto; se apunta al temporal
        dist = tmp_path / "dist"
        dist.mkdir(exist_ok=True)
        (dist / modulo.INSTALADOR).write_bytes(b"PK\x03\x04" + b"0" * 2048)
        monkeypatch.setattr(modulo, "BUILD_DIR", dist, raising=False)
        return TestClient(modulo.app), modulo

    return construir


def test_sin_nginx_el_archivo_lo_manda_python(servidor):
    """En el escritorio y en desarrollo no hay nginx que interprete nada.

    Si se emitiera la cabecera igual, el navegador recibiría una respuesta
    vacía y el usuario un archivo de cero bytes.
    """
    c, mod = servidor()
    r = c.get("/descargar")
    if r.status_code == 401:
        pytest.skip("este servidor pide cuenta para descargar")
    assert r.status_code == 200
    assert "x-accel-redirect" not in {k.lower() for k in r.headers}
    assert len(r.content) > 1000, "el archivo viaja de verdad"


def test_con_nginx_python_solo_da_el_permiso(servidor):
    """El cuerpo va vacío a propósito: nginx lo reemplaza por el archivo."""
    c, mod = servidor(xaccel="/interno/")
    r = c.get("/descargar")
    if r.status_code == 401:
        pytest.skip("este servidor pide cuenta para descargar")
    assert r.status_code == 200
    destino = r.headers.get("x-accel-redirect")
    assert destino == f"/interno/{mod.INSTALADOR}", (
        "la ruta interna tiene que coincidir con el bloque location de nginx.conf")
    # el nombre sí viaja, para que el navegador lo guarde en vez de mostrarlo
    assert mod.INSTALADOR in r.headers.get("content-disposition", "")
    assert r.content == b"", "el cuerpo lo pone nginx, no Python"


def test_la_barra_final_no_duplica_la_ruta(servidor):
    """`/interno/` y `/interno` tienen que dar lo mismo.

    Es el error tipográfico más fácil de cometer editando un .env a mano, y
    produce un 404 de nginx que no dice nada útil.
    """
    c, mod = servidor(xaccel="/interno")
    r = c.get("/descargar")
    if r.status_code == 401:
        pytest.skip("este servidor pide cuenta para descargar")
    assert r.headers.get("x-accel-redirect") == f"/interno/{mod.INSTALADOR}"


def test_sin_instalador_se_dice_que_todavia_no_esta(servidor, tmp_path):
    """Ofrecer una descarga que devuelve 404 hace creer que el producto está
    roto, en vez de que todavía no salió."""
    c, mod = servidor(xaccel="/interno/")
    (tmp_path / "dist" / mod.INSTALADOR).unlink()
    r = c.get("/descargar")
    if r.status_code == 401:
        pytest.skip("este servidor pide cuenta para descargar")
    assert r.status_code == 503
    assert "x-accel-redirect" not in {k.lower() for k in r.headers}


def test_la_ruta_interna_esta_declarada_en_nginx():
    """Que el .env y el nginx.conf hablen del mismo prefijo.

    Son dos archivos distintos que tienen que coincidir en una cadena, y no hay
    nada que los ate salvo esto.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    nginx = (raiz / "despliegue" / "nginx.conf").read_text(encoding="utf-8")
    instalar = (raiz / "despliegue" / "instalar.sh").read_text(encoding="utf-8")

    assert "location /interno/" in nginx, "nginx tiene que exponer la ruta interna"
    assert "internal;" in nginx, "y sólo alcanzable por X-Accel-Redirect"
    assert "BQ_XACCEL=/interno/" in instalar, (
        "el .env que genera el instalador tiene que activar la entrega por nginx "
        "con el mismo prefijo que declara nginx.conf")
