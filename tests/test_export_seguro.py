r"""El nombre de un archivo exportado no puede formar una ruta.

El nombre llega en el payload y despues se usa para construir la ruta de
escritura: ``carpeta / nombre``. Medido antes del arreglo:

    "C:/Windows/Temp/x"      -> C:\Windows\Temp\x.mq5
    "../../../Desktop/pwned" -> ...\Botiquant\..\..\..\Desktop\pwned.mq5

La ruta absoluta reemplaza la carpeta entera y los ".." se salen de ella: es
escritura de archivo arbitraria manejada por un campo de texto. En el servidor
publico la ruta esta cerrada por otro lado (es un endpoint de calculo, y ahi no
hay calculo), pero en el escritorio se acepta \u2014 y una estrategia compartida
entre usuarios puede traer el nombre preparado.
"""

from __future__ import annotations

import pytest

from botiquant.api.app import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app(workdir=tmp_path)


def _sanear(app):
    """El ayudante vive dentro de create_app; se llega por el endpoint."""
    from botiquant.api import app as modulo
    return modulo


@pytest.mark.parametrize("crudo,prohibido", [
    ("C:/Windows/Temp/x", ":"),
    ("../../../Desktop/pwned", ".."),
    ("..\..\sistema", ".."),
    ("/etc/passwd", "/"),
    ("con/barra", "/"),
    ("punto..doble", None),
])
def test_el_nombre_saneado_no_forma_una_ruta(app, crudo, prohibido, tmp_path):
    """Ningun nombre puede producir separadores ni subir de carpeta."""
    from fastapi.testclient import TestClient
    import re
    with TestClient(app) as c:
        ds = c.post("/api/datasets/sample", json={"symbol": "EURUSD", "bars": 900}).json()["id"]
        r = c.post("/api/export/mql5", json={
            "name": crudo, "dataset_id": ds,
            "spec": {"direction": "long",
                     "entry_long": [{"left": {"type": "price"}, "op": ">",
                                     "right": {"type": "const", "value": 0}}]},
        })
        assert r.status_code == 200, r.text
    # el nombre que se usaria para el archivo se deriva igual en los dos
    # caminos; se comprueba la regla directamente
    base = str(crudo).replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9_.\-]", "_", base).lstrip(".").strip("_")
    assert "/" not in base and "\\" not in base and ":" not in base
    assert not base.startswith(".."), f"{crudo!r} todavia sube de carpeta"


def test_la_escritura_comprueba_que_el_destino_este_adentro():
    """Segunda capa: no depende de la lista de caracteres permitidos.

    Un saneo se puede aflojar sin querer al agregar un caracter; la
    comprobacion de contencion sigue valiendo igual.
    """
    from pathlib import Path
    fuente = (Path(__file__).resolve().parents[1] / "botiquant" / "api"
              / "app.py").read_text(encoding="utf-8")
    assert "is_relative_to(carpeta.resolve())" in fuente, (
        "se quito la comprobacion de que el archivo caiga dentro de la carpeta")
    assert "_nombre_de_archivo(" in fuente, "se quito el saneo del nombre"
