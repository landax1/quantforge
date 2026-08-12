"""Firmar y verificar licencias con Ed25519.

El formato es `cuerpo.firma`, ambos en base64 sin relleno, igual que las
cookies de sesión. El cuerpo es JSON legible a propósito: el usuario puede
abrir su licencia y ver qué dice. No hay nada que esconder ahí — lo que la hace
infalsificable es la firma, no el secreto del contenido.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

#: Planes que la aplicación reconoce. Uno desconocido se trata como inválido y
#: no como "gratis": una licencia con un plan que no entendemos es una licencia
#: de otra versión, y adivinar qué habilitar sería regalar funciones o quitarlas.
PLANES = ("free", "pro", "lifetime")


class LicenciaError(Exception):
    """La licencia falta, está vencida, es de otro o su firma no cierra."""


@dataclass(frozen=True)
class Licencia:
    """Lo que la aplicación necesita saber de quién la está usando."""

    user_id: str
    email: str
    plan: str
    #: epoch en segundos; 0 = no vence (lifetime)
    expira: int
    emitida: int

    @property
    def vencida(self) -> bool:
        return self.expira != 0 and self.expira < time.time()

    @property
    def dias_restantes(self) -> int | None:
        if self.expira == 0:
            return None
        return max(0, int((self.expira - time.time()) // 86400))

    def to_dict(self) -> dict[str, Any]:
        return {"user_id": self.user_id, "email": self.email, "plan": self.plan,
                "expira": self.expira, "emitida": self.emitida}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def crear_par_de_claves() -> tuple[str, str]:
    """Devuelve (privada, publica) en base64, para guardar en el entorno.

    Se corre UNA vez al montar el servidor. La privada va al servidor y no sale
    de ahí; la pública se incrusta en la aplicación de escritorio.
    """
    priv = ed25519.Ed25519PrivateKey.generate()
    crudo_priv = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    crudo_pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64(crudo_priv), _b64(crudo_pub)


def firmar(datos: dict[str, Any], clave_privada_b64: str) -> str:
    """Emite una licencia. Sólo el servidor puede hacer esto."""
    faltan = {"user_id", "email", "plan", "expira"} - set(datos)
    if faltan:
        raise LicenciaError(f"faltan campos: {sorted(faltan)}")
    if datos["plan"] not in PLANES:
        raise LicenciaError(f"plan desconocido: {datos['plan']!r}")

    payload = {**datos, "emitida": int(time.time())}
    cuerpo = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    priv = ed25519.Ed25519PrivateKey.from_private_bytes(_unb64(clave_privada_b64))
    return f"{cuerpo}.{_b64(priv.sign(cuerpo.encode()))}"


def verificar(token: str, clave_publica_b64: str) -> Licencia:
    """Comprueba la firma y devuelve la licencia. Sin red.

    Levanta LicenciaError ante cualquier problema, incluida una licencia
    vencida: quien llama decide qué hacer, pero nunca recibe una licencia rota
    creyendo que es buena.
    """
    if not token or "." not in token:
        raise LicenciaError("licencia ausente o malformada")
    cuerpo, firma = token.rsplit(".", 1)

    # Toda licencia es un archivo que el usuario puede editar: base64 roto tiene
    # que dar un rechazo limpio y no una excepción de la biblioteca.
    try:
        firma_bytes = _unb64(firma)
        pub = ed25519.Ed25519PublicKey.from_public_bytes(_unb64(clave_publica_b64))
    except (ValueError, binascii.Error) as exc:
        raise LicenciaError("licencia ilegible") from exc

    try:
        pub.verify(firma_bytes, cuerpo.encode())
    except InvalidSignature as exc:
        raise LicenciaError("la firma no corresponde") from exc

    try:
        datos = json.loads(_unb64(cuerpo))
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise LicenciaError("contenido ilegible") from exc
    if not isinstance(datos, dict):
        raise LicenciaError("contenido inesperado")

    try:
        lic = Licencia(
            user_id=str(datos["user_id"]), email=str(datos["email"]),
            plan=str(datos["plan"]), expira=int(datos["expira"]),
            emitida=int(datos.get("emitida", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LicenciaError("faltan campos en la licencia") from exc

    # Un plan que no conocemos es de otra versión. Tratarlo como "free" sería
    # quitarle funciones a quien pagó; tratarlo como "pro", regalarlas.
    if lic.plan not in PLANES:
        raise LicenciaError(f"plan desconocido: {lic.plan!r}")
    if lic.vencida:
        raise LicenciaError("licencia vencida")
    return lic
