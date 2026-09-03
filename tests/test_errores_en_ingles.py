"""Todo mensaje de error que el servidor levanta tiene su versión en inglés.

La aplicación es bilingüe, pero los `raise HTTPException(...)` se escriben en
castellano y la traducción vive aparte, en una tabla. Nada obligaba a que la
tabla siguiera al código: una usuaria que la recorrió entera en inglés el 3 de
septiembre de 2026 encontró veinte mensajes que salían en castellano, entre
ellos "Ocho es el tope de bots a la vez." y "Pegá el texto de tu licencia.".

Esta prueba lee el archivo con el analizador sintáctico de Python —no con
expresiones regulares, que se pierden con las cadenas partidas en varias
líneas— y exige que cada mensaje en castellano tenga entrada. Si mañana
alguien agrega un `raise` nuevo, se entera acá y no lo descubre un usuario.
"""

from __future__ import annotations

import ast
import pathlib
import re

from botiquant.api.app import ERRORES_EN, ERRORES_EN_PREFIJO, traducir_error

APP = pathlib.Path(__file__).resolve().parents[1] / "botiquant" / "api" / "app.py"

#: Marcas de que la cadena está en castellano. Un mensaje como
#: "dataset_id is required" no necesita traducción.
CASTELLANO = re.compile(r"[áéíóúñ¿¡]|\b(el|la|los|las|una|que|hace falta|no se)\b")

#: Los que se arman con datos adentro. La tabla de prefijos los cubre, y el
#: analizador no puede resolver una f-string a texto fijo.
def _literales_de_httpexception(arbol: ast.AST) -> list[str]:
    salida: list[str] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        nombre = nodo.func.id if isinstance(nodo.func, ast.Name) else getattr(nodo.func, "attr", "")
        if nombre != "HTTPException":
            continue
        for arg in nodo.args[1:2]:
            # ast.Constant cubre las cadenas partidas en varias líneas: Python
            # ya las unió al parsear, que es justo lo que la regex no hacía.
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                salida.append(arg.value)
    return salida


def test_cada_error_en_castellano_tiene_su_ingles():
    arbol = ast.parse(APP.read_text(encoding="utf-8"))
    prefijos = tuple(a for a, _ in ERRORES_EN_PREFIJO)

    sin_traducir = []
    for msg in _literales_de_httpexception(arbol):
        if not CASTELLANO.search(msg):
            continue
        if msg in ERRORES_EN or msg.startswith(prefijos):
            continue
        sin_traducir.append(msg)

    assert not sin_traducir, (
        "estos mensajes salen en castellano con la aplicación en inglés; "
        "agregalos a ERRORES_EN:\n  - " + "\n  - ".join(sorted(set(sin_traducir))))


def test_la_traduccion_devuelve_ingles_de_verdad():
    """Que la clave esté no alcanza: tiene que salir el texto traducido."""
    muestras = [
        "Ocho es el tope de bots a la vez.",
        "Pegá el texto de tu licencia.",
        "Esta estrategia se compartió sólo para mirar.",
        "La porción tiene que ser un número.",
    ]
    for m in muestras:
        en = traducir_error(m, "en")
        assert en != m, f"{m!r} sigue saliendo en castellano"
        assert not CASTELLANO.search(en), f"la traducción de {m!r} tiene castellano: {en!r}"


def test_en_castellano_no_se_toca():
    assert traducir_error("Ocho es el tope de bots a la vez.", "es") == \
        "Ocho es el tope de bots a la vez."
