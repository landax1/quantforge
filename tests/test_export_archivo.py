"""Que el archivo llegue de verdad al disco del usuario.

La falla que motivó esto no era un error: era el silencio. La ventana nativa
(pywebview) cancela TODAS las descargas del navegador por defecto —su
manejador pone ``args.Cancel = True``— así que apretar "bajar el Expert
Advisor" no producía archivo, ni error, ni aviso. Los tests que había pasaban
todos, porque probaban que el endpoint devolviera el texto correcto: nadie
probaba que el texto terminara siendo un archivo.

Por eso la aplicación ahora lo escribe ella misma. El servidor corre en la
máquina del usuario y no necesita pedirle permiso al navegador para nada.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app
from botiquant.rutas import carpeta_de_estrategias


def _spec() -> dict:
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return {
        "name": "export test", "direction": "long",
        "entry_long": [{"left": ema(15), "op": "cross_above", "right": ema(60)}],
        "risk": {"stop_type": "atr", "stop_value": 2, "target_type": "atr",
                 "target_value": 3},
    }


@pytest.fixture()
def salida(tmp_path, monkeypatch) -> Path:
    """La carpeta de estrategias, redirigida para no ensuciar Descargas."""
    destino = tmp_path / "salida"
    monkeypatch.setenv("BQ_EXPORTS", str(destino))
    return destino


@pytest.fixture()
def client(tmp_path):
    app = create_app(workdir=tmp_path / "ws")
    with TestClient(app) as c:
        c.post("/api/datasets/sample", json={"symbol": "EURUSD", "bars": 900})
        yield c


# ------------------------------------------------------------------ el disco
def test_el_mq5_termina_siendo_un_archivo(client, salida):
    """Lo que no se probaba: que exista el archivo."""
    r = client.post("/api/export/mql5/archivo",
                    json={"spec": _spec(), "name": "BQ_Prueba"})
    assert r.status_code == 200
    cuerpo = r.json()

    destino = Path(cuerpo["ruta"])
    assert destino.exists()
    assert destino.name == "BQ_Prueba.mq5"
    assert destino.parent == salida
    assert cuerpo["carpeta"] == str(salida)

    codigo = destino.read_text(encoding="utf-8")
    assert "OnTick" in codigo                     # es un EA de verdad
    assert len(codigo) > 500


def test_el_pine_tambien(client, salida):
    r = client.post("/api/export/pine/archivo",
                    json={"spec": _spec(), "name": "BQ Prueba"})
    destino = Path(r.json()["ruta"])

    assert destino.exists()
    assert destino.suffix == ".pine"
    assert "strategy(" in destino.read_text(encoding="utf-8")


def test_la_carpeta_se_crea_sola(client, salida):
    """Primera exportación en una instalación nueva: no existe todavía."""
    assert not salida.exists()
    client.post("/api/export/mql5/archivo", json={"spec": _spec(), "name": "X"})
    assert salida.is_dir()


def test_guardar_dos_veces_pisa_y_no_acumula(client, salida):
    """Exportar la misma estrategia después de tocar algo tiene que dejar UN
    archivo, no X.mq5, X(1).mq5, X(2).mq5 como haría el navegador."""
    for _ in range(3):
        client.post("/api/export/mql5/archivo", json={"spec": _spec(), "name": "X"})

    assert [p.name for p in salida.iterdir()] == ["X.mq5"]


def test_el_texto_del_archivo_es_el_mismo_que_el_de_la_descarga(client, salida):
    """Los dos caminos comparten el renderizado. Si se separan, un día el
    archivo guardado y el descargado dejan de ser la misma estrategia."""
    cuerpo = {"spec": _spec(), "name": "BQ_Igual"}
    bajado = client.post("/api/export/mql5", json=cuerpo).text
    guardado = Path(client.post("/api/export/mql5/archivo", json=cuerpo).json()["ruta"])

    assert guardado.read_text(encoding="utf-8") == bajado


def test_un_formato_inventado_no_escribe_nada(client, salida):
    assert client.post("/api/export/exe/archivo",
                       json={"spec": _spec(), "name": "X"}).status_code == 404
    assert not salida.exists()


def test_sin_spec_no_hay_archivo(client, salida):
    assert client.post("/api/export/mql5/archivo", json={"name": "X"}).status_code == 400
    assert not salida.exists()


# ---------------------------------------------------------------- la carpeta
def test_abrir_la_carpeta_no_recibe_ninguna_ruta(client, salida, monkeypatch):
    """Un endpoint que abre lo que le manden ejecuta lo que le manden. El
    destino se calcula del lado del servidor y no se puede influir desde afuera.
    """
    abiertas = []
    monkeypatch.setattr("os.startfile", lambda p: abiertas.append(str(p)), raising=False)
    monkeypatch.setattr("sys.platform", "win32")

    r = client.post("/api/abrir-carpeta", json={"carpeta": "C:/Windows/System32"})
    assert r.status_code == 200
    assert abiertas == [str(salida)]              # la suya, no la que mandaron


def test_abrir_la_carpeta_no_existe_en_el_servidor_publico(tmp_path, monkeypatch):
    """En un servidor compartido abriría una ventana en la máquina del
    servidor: nadie la ve y nadie la pidió."""
    monkeypatch.setenv("BQ_MULTIUSER", "1")
    import importlib

    from botiquant.api import app as modulo
    importlib.reload(modulo)
    try:
        with TestClient(modulo.create_app(workdir=tmp_path / "ws")) as c:
            assert c.post("/api/abrir-carpeta", json={}).status_code == 404
    finally:
        monkeypatch.delenv("BQ_MULTIUSER", raising=False)
        importlib.reload(modulo)


# ------------------------------------------------------------------ la causa
def test_la_ventana_nativa_permite_descargar():
    """La causa raíz, fijada.

    pywebview trae ``ALLOW_DOWNLOADS`` en False y cancela toda descarga sin
    decir nada. La aplicación guarda sus estrategias por su cuenta, pero los
    informes en HTML, el Excel y los CSV de operaciones sí bajan por el
    navegador, y sin esto tampoco funcionan.
    """
    desktop = Path(__file__).resolve().parent.parent / "desktop.py"
    fuente = desktop.read_text(encoding="utf-8")

    assert 'webview.settings["ALLOW_DOWNLOADS"] = True' in fuente
    # y antes de abrir la ventana, o la configuración llega tarde
    assert (fuente.index('ALLOW_DOWNLOADS')
            < fuente.index("webview.create_window"))
