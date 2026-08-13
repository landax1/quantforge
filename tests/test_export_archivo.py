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
def test_solo_se_abren_carpetas_de_la_aplicacion(client, salida, monkeypatch):
    """La ruta que llega no se usa como ruta: se busca en la lista de carpetas
    que la aplicación calculó. Si no está, no se abre. Un endpoint que abre lo
    que le manden ejecuta lo que le manden."""
    abiertas = []
    monkeypatch.setattr("os.startfile", lambda p: abiertas.append(str(p)), raising=False)
    monkeypatch.setattr("sys.platform", "win32")

    assert client.post("/api/abrir-carpeta",
                       json={"ruta": "C:/Windows/System32"}).status_code == 403
    assert abiertas == []

    # sin ruta abre la propia, que es el caso normal
    assert client.post("/api/abrir-carpeta", json={}).status_code == 200
    assert abiertas == [str(salida)]


def test_solo_se_abren_archivos_que_exporto_la_aplicacion(client, salida, monkeypatch, tmp_path):
    """Abrir por asociación es ejecutar lo que el sistema tenga configurado
    para esa extensión. Se comprueban dos cosas: la extensión Y la carpeta."""
    abiertos = []
    monkeypatch.setattr("os.startfile", lambda p: abiertos.append(str(p)), raising=False)
    monkeypatch.setattr("sys.platform", "win32")

    mio = Path(client.post("/api/export/mql5/archivo",
                           json={"spec": _spec(), "name": "BQ_Mio"}).json()["ruta"])

    # uno de afuera, aunque tenga la extensión correcta
    ajeno = tmp_path / "ajeno.mq5"
    ajeno.write_text("// no es nuestro", encoding="utf-8")
    assert client.post("/api/abrir-archivo", json={"ruta": str(ajeno)}).status_code == 403

    # y algo nuestro pero que no es una estrategia
    otro = salida / "notas.txt"
    otro.write_text("x", encoding="utf-8")
    assert client.post("/api/abrir-archivo", json={"ruta": str(otro)}).status_code == 400

    assert abiertos == []
    assert client.post("/api/abrir-archivo", json={"ruta": str(mio)}).status_code == 200
    assert abiertos == [str(mio)]


def test_el_robot_va_a_la_carpeta_de_metatrader(client, salida, tmp_path, monkeypatch):
    """El paso que sobraba: copiar el .mq5 a mano hasta MQL5/Experts.

    Compilado desde Descargas, el .ex5 queda al lado del .mq5 y el terminal no
    lo ve nunca — se compila sin errores y el robot no aparece en el Probador.
    """
    terminal = tmp_path / "MetaQuotes" / "ABC123"
    (terminal / "MQL5" / "Experts").mkdir(parents=True)
    (terminal / "origin.txt").write_bytes(
        "C:\\Program Files\\Vantage MetaTrader 5".encode("utf-16"))
    monkeypatch.setenv("BQ_METAQUOTES", str(tmp_path / "MetaQuotes"))

    encontrados = client.get("/api/metatrader").json()["terminales"]
    assert [t["nombre"] for t in encontrados] == ["Vantage MetaTrader 5"]

    r = client.post("/api/export/mql5/archivo", json={
        "spec": _spec(), "name": "BQ_Robot", "terminal": encontrados[0]["id"]}).json()

    assert r["terminal"] == "Vantage MetaTrader 5"
    destino = terminal / "MQL5" / "Experts" / "BQ_Robot.mq5"
    assert destino.exists()
    assert str(destino) == r["ruta"]
    assert not (salida / "BQ_Robot.mq5").exists()   # no quedó también en Descargas


def test_un_metatrader_inventado_no_escribe_en_ningun_lado(client, salida, tmp_path, monkeypatch):
    """El id llega de afuera: si se concatenara a una ruta base, mandar
    `..\\..\\Windows` escribiría fuera de la carpeta prevista."""
    monkeypatch.setenv("BQ_METAQUOTES", str(tmp_path / "vacio"))

    for falso in ("no-existe", "..", "../../Windows/System32"):
        r = client.post("/api/export/mql5/archivo",
                        json={"spec": _spec(), "name": "X", "terminal": falso})
        assert r.status_code == 404, falso
    assert not salida.exists()


def test_el_pine_nunca_va_a_metatrader(client, salida, tmp_path, monkeypatch):
    """MetaTrader no sabe qué hacer con un Pine. Aunque se mande un terminal,
    el .pine va a Descargas."""
    terminal = tmp_path / "MetaQuotes" / "ABC123"
    (terminal / "MQL5" / "Experts").mkdir(parents=True)
    monkeypatch.setenv("BQ_METAQUOTES", str(tmp_path / "MetaQuotes"))
    tid = client.get("/api/metatrader").json()["terminales"][0]["id"]

    r = client.post("/api/export/pine/archivo",
                    json={"spec": _spec(), "name": "X", "terminal": tid}).json()

    assert Path(r["ruta"]).parent == salida
    assert r["terminal"] == ""


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
