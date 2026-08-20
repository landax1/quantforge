"""La clave pública con la que la aplicación verifica licencias.

Está en el repositorio a propósito. Una clave pública sirve para COMPROBAR
firmas, no para hacerlas: quien la tenga puede verificar que una licencia es
auténtica y nada más. La que hay que cuidar es la privada, que vive sólo en
el ``.env`` del servidor y no sale de ahí.

Vive en un archivo de código y no en una variable de entorno porque el
ejecutable de escritorio no tiene ``.env``: se descarga, se descomprime y se
abre. La clave viaja adentro del binario o no viaja.

SI ALGUNA VEZ SE ROTA EL PAR, hay que actualizar esto y volver a publicar la
aplicación. Las licencias firmadas con la clave vieja dejan de verificar. Hay
una prueba que comprueba que esta constante corresponde a la privada del
``.env``, así que un olvido se nota al correr los tests y no en producción.
"""

from __future__ import annotations

#: Ed25519, base64 sin relleno. Pareja de ``BQ_LICENCIA_PRIVADA``.
CLAVE_PUBLICA = "z1fF0F3VatdII3Lahg7109Y--jGJgMUv8xT5CukmwlA"
