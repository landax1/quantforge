"""Operar en vivo lo que el backtest encontró.

El paquete está partido en tres por una razón concreta y no por prolijidad:

  * `nucleo`   decide qué hacer. No sabe qué exchange existe, no toca la red y
               no tiene estado. Se puede probar entero sin plata y sin internet.
  * `adaptador` habla con un exchange. Es lo ÚNICO que cambia entre BingX y
               Binance, y es como el 20% del trabajo.
  * `runner`   el bucle: cada vez que cierra una vela le pregunta al núcleo qué
               hacer y se lo pide al adaptador. Tiene tres modos, y el primero
               no manda ninguna orden.

La razón de esta separación es que la parte que puede perder plata sea la más
chica posible y esté rodeada de partes que ya se probaron.
"""
