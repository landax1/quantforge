"""Flujo OAuth 2.0 con Google, sin librerías de terceros.

Son tres pasos y ninguno necesita más que httpx:

  1. se manda al usuario a Google con un `state` firmado por nosotros;
  2. Google lo devuelve al callback con un `code` de un solo uso;
  3. se canjea ese code por un token y con él se pide quién es.

El `state` es el que evita el CSRF: si alguien induce a un usuario logueado a
visitar el callback con un code ajeno, el state no va a validar.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

#: lo mínimo para saber quién entró. Pedir más obliga a pasar la verificación
#: de Google, que son semanas de trámite.
SCOPES = "openid email profile"


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    @classmethod
    def from_env(cls) -> "GoogleConfig":
        return cls(
            client_id=os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
            redirect_uri=os.environ.get("OAUTH_REDIRECT_URI", "").strip(),
        )


def new_state() -> str:
    return secrets.token_urlsafe(24)


def authorize_url(cfg: GoogleConfig, state: str) -> str:
    """A dónde mandar al usuario para que Google le pida permiso."""
    return AUTH_URL + "?" + urlencode({
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        # `select_account` evita que quien tenga varias cuentas entre siempre
        # con la primera sin poder elegir
        "prompt": "select_account",
        "access_type": "online",
    })


def exchange_code(cfg: GoogleConfig, code: str, *, client: httpx.Client | None = None
                  ) -> dict[str, Any]:
    """Canjea el code por un access token. El code sirve una sola vez."""
    propio = client is None
    client = client or httpx.Client(timeout=15)
    try:
        r = client.post(TOKEN_URL, data={
            "code": code,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "redirect_uri": cfg.redirect_uri,
            "grant_type": "authorization_code",
        })
        r.raise_for_status()
        return r.json()
    finally:
        if propio:
            client.close()


def fetch_profile(access_token: str, *, client: httpx.Client | None = None
                  ) -> dict[str, Any]:
    """Quién es el usuario. Se le pregunta a Google por TLS en vez de confiar
    en el id_token sin validar su firma."""
    propio = client is None
    client = client or httpx.Client(timeout=15)
    try:
        r = client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        r.raise_for_status()
        datos = r.json()
        if not datos.get("sub"):
            raise ValueError("Google no devolvió el identificador de la cuenta")
        return {
            # `sub` es el id estable de la cuenta. El mail NO sirve de clave:
            # se puede cambiar, y dos cuentas distintas pueden haberlo tenido.
            "sub": str(datos["sub"]),
            "email": str(datos.get("email", "")),
            "email_verified": bool(datos.get("email_verified", False)),
            "name": str(datos.get("name", "")),
            "picture": str(datos.get("picture", "")),
        }
    finally:
        if propio:
            client.close()
