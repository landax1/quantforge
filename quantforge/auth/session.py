"""Sesiones en cookie firmada, sin dependencias externas.

El servidor no guarda sesiones: la cookie lleva el id de usuario y su
vencimiento, firmados con HMAC-SHA256. Si alguien edita un solo byte la firma
deja de coincidir y la cookie se descarta. Es lo que evita tener que consultar
la base en cada request para saber quién está del otro lado.

La cookie NO va cifrada, sólo firmada: el usuario puede leer su propio id, que
no es secreto. Lo que no puede es fabricarse uno ajeno.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any

COOKIE = "qf_session"
#: siete días. Más largo obliga a re-loguear seguido sin ganar seguridad real;
#: más corto molesta a quien entra todos los días.
MAX_AGE = 7 * 24 * 3600


class SessionError(Exception):
    """La cookie no existe, está vencida o su firma no cierra."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def sign(data: dict[str, Any], secret: str, max_age: int = MAX_AGE) -> str:
    """Serializa y firma. El vencimiento viaja adentro de lo firmado."""
    payload = {**data, "exp": int(time.time()) + max_age}
    cuerpo = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    firma = hmac.new(secret.encode(), cuerpo.encode(), hashlib.sha256).digest()
    return f"{cuerpo}.{_b64(firma)}"


def verify(token: str, secret: str) -> dict[str, Any]:
    """Devuelve el contenido, o levanta SessionError si algo no cierra."""
    if not token or "." not in token:
        raise SessionError("cookie ausente o malformada")
    cuerpo, firma = token.rsplit(".", 1)
    esperada = hmac.new(secret.encode(), cuerpo.encode(), hashlib.sha256).digest()
    # Toda cookie es entrada hostil: un base64 roto levanta binascii.Error, que
    # sin atrapar se convierte en un 500 en vez de un simple "no estás dentro".
    try:
        recibida = _unb64(firma)
    except (ValueError, binascii.Error) as exc:
        raise SessionError("firma ilegible") from exc
    # comparación en tiempo constante: un `==` filtraría, byte a byte, cuánto
    # de la firma acertó quien esté probando
    if not hmac.compare_digest(esperada, recibida):
        raise SessionError("firma inválida")
    try:
        data = json.loads(_unb64(cuerpo))
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise SessionError("contenido ilegible") from exc
    if not isinstance(data, dict) or "exp" not in data:
        raise SessionError("contenido inesperado")
    if int(data["exp"]) < time.time():
        raise SessionError("sesión vencida")
    return data


def set_cookie(response, token: str, *, secure: bool, max_age: int = MAX_AGE) -> None:
    """`httponly` la esconde del JavaScript de la página, que es lo que
    convierte un XSS en un robo de sesión. `samesite=lax` evita que otro sitio
    dispare acciones con la sesión del usuario."""
    response.set_cookie(
        COOKIE, token, max_age=max_age, httponly=True,
        samesite="lax", secure=secure, path="/",
    )


def read_cookie(request) -> str:
    return request.cookies.get(COOKIE, "")


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE, path="/")
