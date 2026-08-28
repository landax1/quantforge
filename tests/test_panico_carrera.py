"""El botón de pánico contra una vuelta que quedó trabada en la red.

ENCONTRADO porque dos pruebas del apagado se ponían rojas de vez en cuando bajo
la suite completa y verdes al correrlas solas. La intermitencia era la punta:
`Piloto.apagar` espera al hilo con un tope de diez segundos, así que una vuelta
trabada en una llamada de red le sobrevive.

Y eso rompía justo lo que el comentario de `panico` decía cuidar: se cerraba la
posición mientras la vuelta que venía en camino seguía viva, y esa vuelta
abría otra encima. El pánico dejaba al bot con una posición abierta.
"""

from __future__ import annotations

import threading

import pandas as pd
import pytest

from botiquant.vivo.piloto import Piloto
from botiquant.vivo.runner import Bot


class _AdaptadorTrabado:
    """Se queda esperando en `velas` hasta que la prueba lo suelta.

    Es el adaptador que hace visible el problema: cualquier llamada de red que
    tarde más que el tope de `apagar` produce exactamente esta situación.
    """

    def __init__(self):
        self.soltar = threading.Event()
        self.entro = threading.Event()
        self.abiertas = []
        self.cerradas = []

    def velas(self, simbolo, timeframe, cuantas):
        self.entro.set()
        self.soltar.wait(10)
        idx = pd.date_range("2024-01-01", periods=cuantas, freq="1h", tz="UTC")
        # ESTA SERIE DISPARA LA ENTRADA, y no es un detalle: la primera versión
        # de esta prueba usaba una serie que sube siempre, con la que la EMA
        # rápida nunca CRUZA a la lenta —ya está arriba— así que la estrategia
        # no abría nunca. La prueba pasaba con el arreglo y sin él.
        #
        # Baja durante toda la serie y repunta en la última vela: ahí sí cruza.
        # Comprobado: con esta serie `decidir` devuelve `abrir_largo`.
        base = pd.Series([200.0 - i * 0.2 for i in range(cuantas - 1)])
        base = pd.concat([base, pd.Series([float(base.iloc[-1]) + 5.0])],
                         ignore_index=True)
        return pd.DataFrame({"open": base.values, "high": base.values + 1,
                             "low": base.values - 1, "close": base.values,
                             "volume": 1.0}, index=idx)

    def posicion(self, simbolo):
        from botiquant.vivo.adaptador import Posicion
        return Posicion(lado=0, cantidad=0.0)

    def capital(self):
        return 10_000.0

    def contrato(self, simbolo):
        return {"minimo": 0.001, "paso": 0.001}

    def abrir(self, simbolo, lado, cantidad, stop, objetivo):
        self.abiertas.append((lado, cantidad))
        return {"ok": True}

    def cerrar(self, simbolo, pos):
        self.cerradas.append(pos)
        return {"ok": True}


def _bot(adaptador) -> Bot:
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    spec = {"name": "b", "direction": "long",
            "entry_long": [{"left": ema(2), "op": "cross_above", "right": ema(3)}],
            "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                     "stop_type": "atr", "stop_value": 2.0,
                     "target_type": "atr", "target_value": 4.0}}
    doc = {"nombre": "b", "estrategia": spec,
           "ejecucion": {"simbolo": "BTCUSDT", "timeframe": "1h"}}
    return Bot(doc=doc, adaptador=adaptador, modo="real")


def test_el_panico_frena_aunque_el_hilo_siga_trabado():
    """Lo que se defiende: después del pánico NO se abre nada.

    Sin el arreglo, la vuelta trabada se destrababa después de cerrar la
    posición y seguía hasta mandar la orden de apertura.
    """
    a = _AdaptadorTrabado()
    b = _bot(a)
    p = Piloto()
    p.encender(b)
    assert a.entro.wait(5), "el bot tendría que haber entrado a pedir velas"

    # el pánico llega con la vuelta trabada en la red
    p.panico()

    # ahora se destraba la vuelta que venía en camino
    a.soltar.set()
    if p.hilo:
        p.hilo.join(timeout=10)

    # LA ASERCIÓN QUE IMPORTA VA PRIMERO. Si se rompe el arreglo, tiene que
    # romperse ESTA y no una sobre una marca interna: lo que hace daño es la
    # orden, no el valor del campo.
    assert a.abiertas == [], "abrió una posición DESPUÉS del pánico"
    assert b.detenido is True
    assert b.motivo_detencion == "pánico"


def test_frenar_no_depende_de_que_el_hilo_conteste():
    """Es el punto del arreglo: `apagar` puede fallar en parar al hilo a
    tiempo, y el freno tiene que valer igual."""
    a = _AdaptadorTrabado()
    b = _bot(a)
    p = Piloto()
    p.encender(b)
    assert a.entro.wait(5)

    p.panico()
    assert b.detenido is True, "frenado sin esperar al hilo"
    a.soltar.set()
    if p.hilo:
        p.hilo.join(timeout=10)


def test_sin_bot_el_panico_no_revienta():
    assert Piloto().panico()["cerrado"] == "no había bot"
