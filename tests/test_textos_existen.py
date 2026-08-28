"""Toda clave de texto que la interfaz pide tiene que existir.

ENCONTRADO por casualidad, buscando dónde poner una pantalla nueva: la pantalla
de Operar pide `op.tab_bot` y `op.tab_claves` para sus dos pestañas, y ninguna
de las dos está en el diccionario. Las pestañas dicen literalmente "op.tab_bot".

Es la peor forma de fallar que tiene un texto: `t()` devuelve la clave cuando no
la encuentra, así que la aplicación no rompe, no avisa —salvo un `console.warn`
que nadie mira— y la pantalla sale con el nombre interno donde iba la palabra.

Sólo se revisan las claves ESCRITAS ENTERAS. Las armadas —`t("cat." + x)`— no
se pueden verificar así, y para ésas están las pruebas por catálogo.
"""

from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui"

#: `t("una.clave")` o `t("una.clave", {vars})`.
#:
#: El `(?=\s*[,)])` es lo que separa una clave entera de un PREFIJO: en
#: `t("cat." + x)` a la comilla la sigue un `+`, y sin esa condición el examen
#: reclamaba "cat." como si fuera una clave faltante. Las armadas no se pueden
#: verificar así —para eso están las pruebas por catálogo— y dejarlas
#: reclamando ruido haría que el examen se ignore, que es peor que no tenerlo.
USO = re.compile(r"""\bt\(\s*(["'])([A-Za-z0-9_.]+)\1(?=\s*[,)])""")


def _claves_usadas() -> set[str]:
    usadas: set[str] = set()
    for archivo in ("app.js",):
        texto = (UI / archivo).read_text(encoding="utf-8")
        usadas |= {m.group(2) for m in USO.finditer(texto)}
    return usadas


def _claves_definidas() -> set[str]:
    texto = (UI / "i18n.js").read_text(encoding="utf-8")
    return set(re.findall(r'^\s*"([A-Za-z0-9_.]+)"\s*:\s*\[', texto, re.M))


def test_no_falta_ninguna_clave_de_texto():
    faltan = sorted(_claves_usadas() - _claves_definidas())
    assert not faltan, (
        f"{len(faltan)} clave(s) que la interfaz pide y el diccionario no "
        f"tiene; se dibujan en crudo: {faltan}")
