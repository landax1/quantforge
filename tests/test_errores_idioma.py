"""Los errores del servidor salen en el idioma de la interfaz.

Habia 42 mensajes escritos solo en espanol. La aplicacion abre en ingles por
defecto, asi que cualquier fallo mostraba espanol en medio de una pantalla en
ingles — y para quien no lee espanol, el error dejaba de explicar nada.

Se traduce en un solo lugar y no en los 42 `raise`: pasar el idioma por
parametro obligaria a que todas las funciones internas lo arrastren hasta el
fondo, incluidas las que no saben que existe una peticion.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import (
    ERRORES_EN, ERRORES_EN_PREFIJO, create_app, traducir_error,
)


@pytest.fixture()
def cliente(tmp_path):
    with TestClient(create_app(workdir=tmp_path)) as c:
        yield c


def test_traduce_lo_que_esta_en_la_tabla():
    assert traducir_error("Seleccionar al menos una estrategia.", "en") == "Select at least one strategy."


def test_los_mensajes_con_datos_conservan_los_datos():
    """El texto cambia; las fechas, rutas y cantidades no se tocan."""
    assert traducir_error("Fecha inválida: 2020-13-01", "en") == "Invalid date: 2020-13-01"
    assert traducir_error("No existe el archivo: C:/x.csv", "en") == "No such file: C:/x.csv"


def test_en_espanol_no_cambia_nada():
    """El comportamiento anterior se conserva entero."""
    for msg in list(ERRORES_EN)[:5]:
        assert traducir_error(msg, "es") == msg
        assert traducir_error(msg, "") == msg


def test_lo_que_no_esta_en_la_tabla_viaja_tal_cual():
    """Un mensaje sin traducción se ve en español, que es peor que en inglés
    pero muchísimo mejor que un error genérico o que ninguno."""
    assert traducir_error("Algo que nadie tradujo", "en") == "Algo que nadie tradujo"


def test_el_endpoint_responde_en_el_idioma_pedido(cliente):
    r = cliente.post("/api/robustez", json={"estrategias": []},
                     headers={"X-Idioma": "en"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Select at least one strategy."


def test_sin_cabecera_sigue_en_espanol(cliente):
    r = cliente.post("/api/robustez", json={"estrategias": []})
    assert r.status_code == 400
    assert "Seleccionar" in r.json()["detail"]


def test_el_codigo_de_estado_no_se_pierde(cliente):
    """Traducir no puede convertir un 404 en un 200 ni tragarse el estado."""
    r = cliente.get("/api/results/no-existe", headers={"X-Idioma": "en"})
    assert r.status_code == 404


def test_ninguna_traduccion_quedo_vacia():
    for es, en in ERRORES_EN.items():
        assert en.strip(), f"traducción vacía para {es!r}"
    for es, en in ERRORES_EN_PREFIJO:
        assert es.strip() and en.strip()
