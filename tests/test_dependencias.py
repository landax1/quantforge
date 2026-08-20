"""Que `requirements.txt` alcance para arrancar en una máquina limpia.

Existe por un despliegue que falló. El servicio no levantó con
``ModuleNotFoundError: No module named 'httpx'``: el paquete lo importa para
hablar con Google durante el login, pero no estaba declarado. En la máquina de
desarrollo venía de arrastre —lo instala el ``TestClient`` de FastAPI— así que
todo funcionaba, los 526 tests pasaban, y el problema apareció recién en un
Ubuntu recién creado a las nueve de la noche.

Esa clase de error no la agarra ninguna prueba de comportamiento, porque en la
máquina donde corren las pruebas el módulo está. Lo único que la agarra es
comparar lo que el código importa contra lo que el archivo declara.
"""

from __future__ import annotations

import ast
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PAQUETE = RAIZ / "botiquant"

#: Nombre del módulo → nombre en PyPI, para los que no coinciden.
EN_PYPI = {
    "yaml": "pyyaml",
    "dateutil": "python-dateutil",
    "PIL": "pillow",
}

#: Lo que sólo se usa en el escritorio y por eso vive en el otro archivo.
SOLO_ESCRITORIO = {"webview"}


def _importados() -> set[str]:
    """Los módulos de terceros que importa el paquete."""
    fuera = set()
    for archivo in PAQUETE.rglob("*.py"):
        try:
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    fuera.add(alias.name.split(".")[0])
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                fuera.add(nodo.module.split(".")[0])
    return fuera - set(sys.stdlib_module_names) - {"botiquant"} - SOLO_ESCRITORIO


def test_todo_lo_que_se_importa_esta_declarado():
    """Si esto falla, el servidor no va a arrancar. No es un aviso de estilo."""
    declarado = (RAIZ / "requirements.txt").read_text(encoding="utf-8").lower()
    # sin los comentarios: un módulo nombrado en una explicación no cuenta como
    # declarado, y justamente httpx aparece nombrado en el comentario que lo agrega
    declarado = "\n".join(l for l in declarado.splitlines()
                          if l.strip() and not l.strip().startswith("#"))

    faltan = sorted(m for m in _importados()
                    if EN_PYPI.get(m, m).lower() not in declarado)

    assert not faltan, (
        "el paquete importa esto y requirements.txt no lo declara, así que una "
        f"instalación limpia no va a arrancar: {faltan}")


def test_el_de_escritorio_incluye_al_del_servidor():
    """El escritorio suma cosas, nunca reemplaza."""
    escritorio = (RAIZ / "requirements-desktop.txt").read_text(encoding="utf-8")
    assert "-r requirements.txt" in escritorio, (
        "requirements-desktop.txt tiene que arrastrar al común, o el ejecutable "
        "se empaqueta sin la mitad de las dependencias")


def test_el_servidor_no_arrastra_la_interfaz_grafica():
    """Meter pywebview en el común obligaría a instalar una biblioteca de
    ventanas en una máquina sin pantalla."""
    servidor = (RAIZ / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pywebview" not in servidor
