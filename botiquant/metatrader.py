"""Dónde tiene MetaTrader sus Expert Advisors, en esta máquina.

Un .mq5 guardado en Descargas se puede abrir con MetaEditor y hasta compilar,
pero el .ex5 queda al lado del .mq5 y el terminal no lo ve: MetaTrader sólo
lista lo que está bajo ``MQL5/Experts`` de SU carpeta de datos. El usuario
compila sin errores, va al Probador de estrategias, no encuentra el robot y no
tiene forma de saber por qué.

Por eso la aplicación busca esa carpeta y escribe ahí directamente. El paso
manual de copiar el archivo deja de existir, y con él el error que produce.

La carpeta de datos NO es donde está instalado el programa: MetaTrader guarda
lo que el usuario escribe en %APPDATA%, con un nombre que es un hash de la
instalación. Adentro, ``origin.txt`` dice de qué instalación es.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _raiz() -> Path:
    """La carpeta que agrupa todas las instalaciones de MetaTrader."""
    forzada = os.environ.get("BQ_METAQUOTES", "").strip()
    if forzada:
        return Path(forzada)
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "MetaQuotes" / "Terminal"
    return Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"


def _nombre(carpeta: Path) -> str:
    """Un nombre legible para el terminal.

    ``origin.txt`` guarda la ruta de instalación en UTF-16, que es lo único que
    distingue un MetaTrader de otro cuando hay varios: el de siempre, el de una
    prop firm, el de otro broker. Sin esto, la lista serían tres hashes de
    treinta y dos caracteres y nadie sabría cuál elegir.
    """
    archivo = carpeta / "origin.txt"
    if archivo.exists():
        crudo = archivo.read_bytes()
        for codificacion in ("utf-16", "utf-8-sig", "utf-8"):
            try:
                ruta = crudo.decode(codificacion).strip().strip("\ufeff").strip()
            except (UnicodeDecodeError, UnicodeError):
                continue
            if ruta:
                # la última parte de la ruta es el nombre de la instalación:
                # "C:\Program Files\FTMO MetaTrader 5" -> "FTMO MetaTrader 5"
                return _ultimo_tramo(ruta)
    return carpeta.name[:8]


def _ultimo_tramo(ruta: str) -> str:
    """El último tramo de una ruta de Windows, sin depender del separador
    del sistema donde corre esto."""
    limpio = ruta.replace("/", "\\").rstrip("\\")
    return limpio.rsplit("\\", 1)[-1] or limpio


def _ultimo_uso(carpeta: Path) -> float:
    """Cuándo se usó por última vez, para poner primero el que está en uso.

    Se mira el log más nuevo y no la fecha de la carpeta: la carpeta se toca
    al instalar y no vuelve a cambiar, así que ordenaría por antigüedad de
    instalación en vez de por uso.
    """
    logs = carpeta / "logs"
    if logs.is_dir():
        fechas = [f.stat().st_mtime for f in logs.glob("*.log")]
        if fechas:
            return max(fechas)
    try:
        return carpeta.stat().st_mtime
    except OSError:
        return 0.0


def terminales() -> list[dict[str, Any]]:
    """Los MetaTrader 5 instalados que pueden recibir un Expert Advisor.

    Ordenados por uso, el más reciente primero: con varios instalados, el que
    el usuario tiene abierto ahora es casi siempre el que quiere.

    Sólo MQL5. Un MetaTrader 4 tiene su carpeta ``MQL4`` y no compila un .mq5,
    así que ofrecerlo como destino sería mandar el archivo a un lugar donde no
    va a funcionar.
    """
    raiz = _raiz()
    if not raiz.is_dir():
        return []
    encontrados: list[dict[str, Any]] = []
    try:
        candidatos = sorted(raiz.iterdir())
    except OSError:
        return []
    for carpeta in candidatos:
        experts = carpeta / "MQL5" / "Experts"
        if not experts.is_dir():
            continue
        encontrados.append({
            "id": carpeta.name,
            "nombre": _nombre(carpeta),
            "experts": str(experts),
            "usado": _ultimo_uso(carpeta),
        })
    encontrados.sort(key=lambda t: t["usado"], reverse=True)
    return encontrados


def experts_de(terminal_id: str) -> Path | None:
    """La carpeta Experts de un terminal, buscándolo por id en la lista real.

    Se busca en la lista y no se arma la ruta con el id que llega de afuera:
    concatenar un identificador recibido a una ruta base es exactamente cómo se
    escribe fuera de la carpeta prevista.
    """
    for t in terminales():
        if t["id"] == terminal_id:
            return Path(t["experts"])
    return None
