"""Todo lo que index.html enlaza tiene que ir con versión en la URL.

Esta prueba nace de un fallo real. Al agregar `i18n.js` nadie lo sumó a la
lista de assets que `_html_de_la_app` versiona, así que era el único archivo
que el navegador servía desde su caché. El resultado: la aplicación nueva
corriendo el diccionario viejo. No falla, no avisa, no rompe nada — sólo
muestra claves crudas y funciones que no existen, y se ve igual que si la
actualización no hubiera llegado.

Por eso la prueba no comprueba una lista escrita a mano: lee los enlaces del
propio index.html. Un archivo nuevo entra en el examen solo.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from botiquant.api.app import UI_DIR, create_app


def _enlaces(html: str) -> set[str]:
    """Los /static/... que pide el documento, sin su cadena de versión."""
    return {m.split("?")[0] for m in re.findall(r'/static/[\w.\-/]+(?:\?v=\d+)?', html)}


def test_cada_asset_de_la_interfaz_va_versionado(tmp_path):
    with TestClient(create_app(workdir=tmp_path)) as c:
        html = c.get("/app").text

    sin_version = []
    for enlace in _enlaces(html):
        archivo = UI_DIR / enlace.removeprefix("/static/")
        # sólo se exige de lo que realmente existe en disco: un enlace roto es
        # otro problema, y confundirlos haría ilegible el fallo de éste
        if archivo.is_file() and f"{enlace}?v=" not in html:
            sin_version.append(enlace)

    assert not sin_version, (
        "estos archivos se sirven sin versión y el navegador los va a cachear "
        f"entre actualizaciones: {sorted(sin_version)}")


def test_el_diccionario_de_idiomas_esta_entre_ellos(tmp_path):
    """Guardia explícita sobre el archivo que provocó el fallo."""
    with TestClient(create_app(workdir=tmp_path)) as c:
        html = c.get("/app").text
    assert re.search(r"/static/i18n\.js\?v=\d+", html), \
        "i18n.js volvió a quedar fuera del versionado"


def test_la_interfaz_se_revalida_y_las_tipografias_no(tmp_path):
    """no-cache en el código; caché larga en las fuentes, que no cambian."""
    with TestClient(create_app(workdir=tmp_path)) as c:
        assert c.get("/static/app.js").headers["cache-control"] == "no-cache"
        fuente = UI_DIR / "fuentes" / "inter-var.woff2"
        if fuente.is_file():
            r = c.get("/static/fuentes/inter-var.woff2")
            assert "immutable" in r.headers["cache-control"]
