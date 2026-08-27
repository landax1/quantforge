"""Las claves del exchange, cifradas y atadas a la cuenta de Windows.

TRES COSAS QUE ESTE ARCHIVO NO HACE, Y NO POR OLVIDO:

  * No manda las claves a ningún lado. Viven en el disco del usuario y nunca
    tocan nuestro servidor. Es lo que se puede decir en la portada sin mentir:
    "tus claves y tus estrategias se quedan en tu computadora".
  * No las escribe en ningún registro, ni siquiera enmascaradas. Lo que sale
    hacia una pantalla o un archivo de eventos son los últimos cuatro
    caracteres de la clave PÚBLICA y nada más. El secreto no sale nunca.
  * No las guarda en texto plano ni "por ahora". Un archivo de configuración
    con un secreto adentro es exactamente lo que busca cualquier cosa que
    entre a la máquina.

POR QUÉ DPAPI Y NO UNA CONTRASEÑA. Windows cifra con `CryptProtectData` usando
la credencial de la sesión: lo que guarda un usuario no lo puede leer otro
usuario de la misma máquina, ni nadie que se lleve el disco. Y no hay que
inventar una contraseña más — una que se olvida deja la cuenta operando sin que
nadie pueda apagarla desde la aplicación.

Se llega por `ctypes`, sin sumar dependencias: la aplicación ya pesa 54 MB y
`pywin32` para dos llamadas no se justifica.

FUERA DE WINDOWS se usa Fernet con una clave guardada al lado, y eso es
DEBILMENTE cifrado: protege de una mirada casual, no de alguien con acceso al
disco. Se dice en pantalla en vez de aparentar lo que no es. Hoy la aplicación
sólo se distribuye para Windows, así que es el camino de nadie — pero el día
que exista la versión de Mac, esto tiene que cambiar a Keychain y no quedarse
así por inercia.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

ES_WINDOWS = sys.platform == "win32"

#: Lo que se puede configurar. Se valida contra esta lista porque el nombre
#: viaja hasta un nombre de archivo.
EXCHANGES = ("bingx",)
ENTORNOS = ("practica", "real")


class ClaveError(RuntimeError):
    """Algo salió mal guardando o leyendo, con un texto que se puede mostrar."""


# --------------------------------------------------------------------- DPAPI

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(datos: bytes) -> _BLOB:
    buf = ctypes.create_string_buffer(datos, len(datos))
    return _BLOB(len(datos), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _leer_blob(b: _BLOB) -> bytes:
    return ctypes.string_at(b.pbData, b.cbData)


def _dpapi_cifrar(datos: bytes) -> bytes:
    entrada, salida = _blob(datos), _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(entrada), None, None, None, None, 0,
            ctypes.byref(salida)):
        raise ClaveError("Windows no pudo cifrar la clave.")
    try:
        return _leer_blob(salida)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def _dpapi_descifrar(datos: bytes) -> bytes:
    entrada, salida = _blob(datos), _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(entrada), None, None, None, None, 0,
            ctypes.byref(salida)):
        raise ClaveError(
            "Windows no pudo descifrar la clave. Pasa cuando el archivo se "
            "copió de otra máquina o de otro usuario: las claves están atadas "
            "a esta sesión de Windows. Cargala de nuevo.")
    try:
        return _leer_blob(salida)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


# ------------------------------------------------------------------- Fernet

def _fernet(carpeta: Path):
    from cryptography.fernet import Fernet
    llave = carpeta / ".llave"
    if not llave.exists():
        llave.write_bytes(Fernet.generate_key())
        _solo_para_mi(llave)
    return Fernet(llave.read_bytes())


def _solo_para_mi(ruta: Path) -> None:
    """Permisos de lectura sólo para el dueño, donde el sistema lo permita."""
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass


# -------------------------------------------------------------------- la API

def _ruta(carpeta: Path, exchange: str, entorno: str) -> Path:
    if exchange not in EXCHANGES:
        raise ClaveError(f"Exchange desconocido: {exchange}")
    if entorno not in ENTORNOS:
        raise ClaveError(f"Entorno desconocido: {entorno}")
    return Path(carpeta) / f"claves-{exchange}-{entorno}.bin"


def guardar(carpeta: Path, exchange: str, entorno: str, *,
            api_key: str, secret: str) -> dict[str, Any]:
    """Cifra y guarda. Devuelve lo que se puede mostrar, nunca el secreto."""
    api_key, secret = api_key.strip(), secret.strip()
    if not api_key or not secret:
        raise ClaveError("Faltan la clave o el secreto.")

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    crudo = json.dumps({"api_key": api_key, "secret": secret}).encode()
    cifrado = _dpapi_cifrar(crudo) if ES_WINDOWS else _fernet(carpeta).encrypt(crudo)

    destino = _ruta(carpeta, exchange, entorno)
    destino.write_bytes(cifrado)
    _solo_para_mi(destino)
    return describir(carpeta, exchange, entorno)


def leer(carpeta: Path, exchange: str, entorno: str) -> tuple[str, str]:
    """Devuelve (api_key, secret). Sólo lo llama quien va a firmar un pedido."""
    ruta = _ruta(Path(carpeta), exchange, entorno)
    if not ruta.exists():
        raise ClaveError(
            f"No hay claves guardadas para {exchange} en {entorno}.")
    crudo = (_dpapi_descifrar(ruta.read_bytes()) if ES_WINDOWS
             else _fernet(Path(carpeta)).decrypt(ruta.read_bytes()))
    d = json.loads(crudo)
    return d["api_key"], d["secret"]


def describir(carpeta: Path, exchange: str, entorno: str) -> dict[str, Any]:
    """Lo que se puede mostrar en pantalla: si hay clave y sus últimos cuatro.

    Los últimos cuatro alcanzan para reconocer CUÁL clave está cargada cuando
    alguien tiene varias, y no alcanzan para usarla. El secreto no aparece
    nunca, ni siquiera enmascarado: un secreto enmascarado sigue siendo una
    pista sobre su longitud y su formato.
    """
    ruta = _ruta(Path(carpeta), exchange, entorno)
    if not ruta.exists():
        return {"exchange": exchange, "entorno": entorno, "configurada": False}
    try:
        api_key, _ = leer(carpeta, exchange, entorno)
        cola = api_key[-4:] if len(api_key) >= 4 else "····"
    except ClaveError as exc:
        return {"exchange": exchange, "entorno": entorno, "configurada": True,
                "ilegible": str(exc)}
    return {"exchange": exchange, "entorno": entorno, "configurada": True,
            "termina_en": cola,
            "guardada": ruta.stat().st_mtime,
            "cifrado": "windows" if ES_WINDOWS else "archivo"}


def borrar(carpeta: Path, exchange: str, entorno: str) -> bool:
    """Saca la clave de la máquina. Devuelve si había algo que sacar."""
    ruta = _ruta(Path(carpeta), exchange, entorno)
    if not ruta.exists():
        return False
    # Se sobreescribe antes de borrar. No es garantía en un SSD —el controlador
    # decide dónde escribe— pero cuesta nada y en un disco común sirve.
    try:
        ruta.write_bytes(b"\0" * max(ruta.stat().st_size, 64))
    except OSError:
        pass
    ruta.unlink()
    return True


def listar(carpeta: Path) -> list[dict[str, Any]]:
    """El estado de todas las combinaciones, sin ningún secreto adentro."""
    return [describir(carpeta, ex, en) for ex in EXCHANGES for en in ENTORNOS]
