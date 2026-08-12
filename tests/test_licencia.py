"""Licencias firmadas.

Casi todo acá prueba que algo NO se puede. Una licencia que sólo sabe aceptar
las buenas no sirve de nada: lo que la hace valer es que rechace las demás.
"""

from __future__ import annotations

import json
import time

import pytest

from botiquant.licencia import (
    LicenciaError, crear_par_de_claves, firmar, verificar,
)
from botiquant.licencia.firma import _b64, _unb64

PRIV, PUB = crear_par_de_claves()


def _datos(**extra):
    base = {"user_id": "u1", "email": "yo@example.com", "plan": "pro",
            "expira": int(time.time()) + 30 * 86400}
    return {**base, **extra}


# ------------------------------------------------------------------ lo que anda
def test_a_signed_licence_round_trips():
    lic = verificar(firmar(_datos(), PRIV), PUB)
    assert lic.user_id == "u1"
    assert lic.plan == "pro"
    assert lic.dias_restantes in (29, 30)


def test_a_lifetime_licence_never_expires():
    lic = verificar(firmar(_datos(plan="lifetime", expira=0), PRIV), PUB)
    assert not lic.vencida
    assert lic.dias_restantes is None


# --------------------------------------------------- lo que NO tiene que andar
def test_the_public_key_cannot_mint_a_licence_that_verifies():
    """La propiedad que sostiene todo el esquema: la aplicación lleva la clave
    pública, así que puede verificar pero nunca fabricar. Con HMAC, quien abra
    el ejecutable se emitiría las licencias que quisiera.

    Ojo con cómo se prueba esto. Una clave pública Ed25519 son 32 bytes, igual
    que una privada, así que `firmar` la acepta como semilla y devuelve un
    token con buena pinta. Lo que importa no es que firmar falle sino que ese
    token NO verifique: un test que sólo comprobara la excepción daría por buena
    una implementación rota.
    """
    trucho = firmar(_datos(plan="lifetime", expira=0), PUB)
    assert trucho, "firmar con la pública igual devuelve algo: por eso hay que verificar"

    with pytest.raises(LicenciaError, match="firma"):
        verificar(trucho, PUB)


def test_another_key_pair_cannot_forge_one():
    otra_priv, _ = crear_par_de_claves()
    with pytest.raises(LicenciaError, match="firma"):
        verificar(firmar(_datos(), otra_priv), PUB)


def test_editing_the_payload_breaks_the_signature():
    """El archivo está en la máquina del usuario y es JSON legible: cambiarse
    el plan a mano es lo primero que alguien va a intentar."""
    token = firmar(_datos(plan="free"), PRIV)
    cuerpo, firma = token.rsplit(".", 1)
    datos = json.loads(_unb64(cuerpo))
    datos["plan"] = "lifetime"
    trucho = _b64(json.dumps(datos, separators=(",", ":"), sort_keys=True).encode())

    with pytest.raises(LicenciaError):
        verificar(f"{trucho}.{firma}", PUB)


def test_extending_the_expiry_breaks_the_signature():
    token = firmar(_datos(expira=int(time.time()) + 60), PRIV)
    cuerpo, firma = token.rsplit(".", 1)
    datos = json.loads(_unb64(cuerpo))
    datos["expira"] = int(time.time()) + 99 * 365 * 86400
    trucho = _b64(json.dumps(datos, separators=(",", ":"), sort_keys=True).encode())

    with pytest.raises(LicenciaError):
        verificar(f"{trucho}.{firma}", PUB)


def test_an_expired_licence_is_refused():
    token = firmar(_datos(expira=int(time.time()) - 1), PRIV)
    with pytest.raises(LicenciaError, match="vencida"):
        verificar(token, PUB)


def test_an_unknown_plan_is_refused_and_not_downgraded():
    """Un plan que no conocemos viene de otra versión. Tratarlo como 'free'
    le quita funciones a quien pagó; tratarlo como 'pro' las regala. Se
    rechaza."""
    with pytest.raises(LicenciaError, match="plan desconocido"):
        firmar(_datos(plan="enterprise"), PRIV)


@pytest.mark.parametrize("basura", [
    "", "sin-punto", "a.b", "....", "x." + "A" * 40, "@@@.###",
])
def test_garbage_never_passes(basura):
    """El archivo lo puede editar el usuario: la basura tiene que dar un
    rechazo limpio y no una excepción de la biblioteca de criptografía."""
    with pytest.raises(LicenciaError):
        verificar(basura, PUB)


def test_a_licence_missing_fields_is_refused():
    with pytest.raises(LicenciaError, match="faltan campos"):
        firmar({"user_id": "u1", "plan": "pro"}, PRIV)


def test_two_key_pairs_are_never_the_same():
    assert len({crear_par_de_claves()[1] for _ in range(20)}) == 20


def test_verification_needs_no_network(monkeypatch):
    """Hacer un backtest no puede depender de que el servidor conteste. Si
    alguien mete una llamada de red acá dentro, este test la caza."""
    import socket

    def prohibido(*a, **k):
        raise AssertionError("la verificación intentó salir a la red")

    monkeypatch.setattr(socket, "socket", prohibido)
    monkeypatch.setattr(socket, "create_connection", prohibido)

    lic = verificar(firmar(_datos(), PRIV), PUB)
    assert lic.plan == "pro"
