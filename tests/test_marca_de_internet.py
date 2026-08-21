"""Que la aplicación se quite la Marca de la Web antes de que .NET la rechace.

Esta prueba existe por el peor error que tuvo el producto: **la aplicación
publicada no abría en la máquina de nadie**. No en un caso raro — en el camino
normal, el único que todos hacen:

    bajar el ZIP de botiquant.com
    extraerlo con el Explorador de Windows
    abrir Botiquant.exe
    → ventana de error con ochenta líneas de Traceback

Windows marca el ZIP descargado y el Explorador propaga esa marca a los 877
archivos que extrae. .NET Framework se niega a cargar un ensamblado marcado, y
``Python.Runtime.dll`` es justo lo que pywebview necesita para dibujar la
ventana. Medido: mismos archivos, misma carpeta, con marca muere y sin marca
abre.

Y no lo agarró ninguna de las 529 pruebas que estaban en verde, porque todas
corren sobre el código fuente y el problema sólo existe en el binario
descargado. Lo único que lo habría agarrado es abrir el ZIP como lo abre un
usuario, que es lo que ahora está escrito acá abajo como recordatorio.

Lo que sí se puede comprobar automáticamente es el ORDEN, que es donde vive
todo el arreglo: la limpieza tiene que pasar **antes** del ``import webview``.
Después de esa línea ya es tarde — el import falla y se lleva el proceso.
"""

from __future__ import annotations

import ast
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DESKTOP = RAIZ / "desktop.py"

LIMPIEZA = "soltar_la_marca_de_internet"


def test_la_limpieza_existe():
    assert LIMPIEZA in DESKTOP.read_text(encoding="utf-8"), (
        "sin esto la aplicación descargada no abre en ninguna máquina")


def test_la_limpieza_corre_antes_de_importar_webview():
    """El orden ES el arreglo.

    Si alguien mueve la llamada debajo del import, la aplicación vuelve a no
    abrir para nadie y todo lo demás sigue pasando.
    """
    arbol = ast.parse(DESKTOP.read_text(encoding="utf-8"))

    main = next(n for n in ast.walk(arbol)
                if isinstance(n, ast.FunctionDef) and n.name == "main")

    linea_limpieza = linea_import = None
    for nodo in ast.walk(main):
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and nodo.func.id == LIMPIEZA):
            linea_limpieza = nodo.lineno
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name == "webview":
                    linea_import = nodo.lineno

    assert linea_limpieza is not None, f"{LIMPIEZA}() no se llama en main()"
    assert linea_import is not None, "no se importa webview en main()"
    assert linea_limpieza < linea_import, (
        f"{LIMPIEZA}() está en la línea {linea_limpieza} y el import de webview "
        f"en la {linea_import}. Tiene que ir ANTES: después del import ya falló "
        "y se llevó el proceso.")


def test_el_import_de_webview_esta_protegido():
    """Si aun así falla, el usuario merece una frase y no un Traceback."""
    fuente = DESKTOP.read_text(encoding="utf-8")
    assert "import webview" in fuente
    i = fuente.index("import webview")
    alrededor = fuente[max(0, i - 200): i + 700]
    assert "try:" in alrededor, "el import de webview tiene que ir en un try"
    assert "Extraé" in alrededor or "extra" in alrededor.lower(), (
        "el mensaje de error tiene que decirle al usuario qué hacer "
        "(extraer la carpeta), no sólo que algo falló")


def test_en_desarrollo_no_hace_nada():
    """Sin empaquetar no hay nada descargado que limpiar, y recorrer el árbol
    del proyecto entero en cada arranque sería trabajo al pedo."""
    import sys

    sys.path.insert(0, str(RAIZ))
    import desktop

    assert not getattr(sys, "frozen", False), "esta prueba corre sin empaquetar"
    assert desktop.soltar_la_marca_de_internet() == 0
