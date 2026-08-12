"""Licencias: se firman en el servidor, se verifican sin conexión.

La regla de oro del modelo híbrido es que hacer un backtest NO puede depender
de que el servidor conteste. Si dependiera, volveríamos al problema que
queríamos evitar: el trabajo pesado corre en la máquina del usuario, pero el
producto se cae cuando el servidor se cae.

Por eso la licencia es un papel firmado que el usuario lleva encima. La app lo
verifica sola, sin red.

FIRMA ASIMÉTRICA, NO HMAC. Es la decisión de seguridad del asunto. Con HMAC la
aplicación necesitaría el secreto para comprobar la firma, y cualquiera que
abra el ejecutable lo extrae y se fabrica licencias infinitas. Con Ed25519 el
ejecutable lleva sólo la clave pública: puede verificar, nunca falsificar. La
privada no sale del servidor.

Lo que esto NO impide: alguien que modifique el binario para saltearse la
comprobación. Ninguna licencia de software puede impedirlo, y perseguirlo es
tirar plata. Esto frena la copia casual —pasarle el archivo a un amigo— que es
el 99% del caso real.
"""

from __future__ import annotations

from .firma import (
    Licencia,
    LicenciaError,
    crear_par_de_claves,
    firmar,
    verificar,
)

__all__ = ["Licencia", "LicenciaError", "crear_par_de_claves", "firmar", "verificar"]
