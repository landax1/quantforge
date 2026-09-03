"""Encender y apagar los bots, que es lo único que faltaba para que operen.

El `Bot` de `runner.py` sabe dar UNA vuelta. Esto es lo que lo despierta cuando
cierra cada vela, lo apaga cuando alguien lo pide, y lo apaga solo cuando algo
sale mal. Vive acá y no en el `JobManager` porque aquél está hecho para
trabajos que terminan: un minado corre, entrega un resultado y libera el cupo.
Un bot no termina nunca, y meterlo en esa cola le sacaría el lugar a las
búsquedas de la persona hasta que lo apague.

===========================================================================
VARIOS BOTS, PERO UNO POR SIMBOLO
===========================================================================

Antes era uno solo, y el motivo era bueno: dos bots sobre la misma cuenta se
pelean por la misma posición — uno abre, el otro ve una posición que él no
abrió, se detiene, y el primero sigue creyendo que está solo.

Pero ese choque no es de la CUENTA sino del SIMBOLO. En una cuenta de futuros
hay una posición neta por símbolo, así que:

    dos bots en símbolos distintos   no chocan: sólo comparten margen
    dos bots en el MISMO símbolo     chocan de raíz, y no hay vuelta

Por eso ahora se permiten varios y se rechaza el segundo del mismo símbolo. Un
portafolio de verdad —repartir el capital entre estrategias y mirar el
conjunto— es justo lo que el webhook de un exchange no puede hacer, y era la
razón de operar por API en vez de por alerta.

LO QUE SI COMPARTEN ES EL CAPITAL, y por eso cada bot lleva su `porcion`. Sin
eso, cinco bots se creen dueños del 100% cada uno y entre todos arriesgan cinco
veces lo pedido. Las porciones no pueden sumar más que la cuenta, y se
comprueba acá: es el único lugar que ve a todos a la vez.

NO SE REANUDA SOLO AL ABRIR LA APLICACIÓN. Es el alcance elegido para esta
primera versión: opera mientras la aplicación está abierta y, si se cerró con
una posición viva, al volver lo dice y espera una decisión. La reanudación
automática es donde nacen las órdenes duplicadas, y duplicar una orden con
plata real cuesta el doble que no operar un rato.

EL DESPERTADOR NO ES UN `sleep`. Espera sobre un evento, así apagar es
inmediato: con `sleep(3600)` el botón de apagar tardaría hasta una hora en
hacer efecto, que es exactamente el momento en que a alguien más le urge.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from botiquant.data.bingx import BingXError
from botiquant.data.binance_trade import TRANSITORIOS, BinanceError
from botiquant.vivo import semaforo, vigilante
from botiquant.vivo.nucleo import DURACION
from botiquant.vivo.runner import Bot

#: Cuánto se espera después de que cierra la vela antes de mirar. El exchange
#: tarda un instante en publicar la vela cerrada, y preguntar en el segundo
#: exacto devuelve todavía la que se está formando.
GRACIA = 5.0

#: Techo de la espera entre vueltas. Con velas diarias, dormir 24 horas de un
#: saque deja al bot sin poder notar que se cayó la red hasta el día siguiente.
MAXIMA_ESPERA = 300.0

#: Cuántos bots a la vez, como mucho.
#:
#: No es un límite técnico sino de atención: cada bot es una posición que
#: alguien tiene que poder mirar, y una pantalla con quince es una pantalla que
#: no se mira. El ciclo ya tiene su propio tope de cuántas promueve.
#: Cuántos tropiezos SEGUIDOS del exchange se toleran antes de apagar el bot.
TROPIEZOS_MAXIMOS = 3
#: Cuánto se espera tras un tropiezo antes de volver a intentar (segundos):
#: corto, para no perder la vela; no tan corto como para martillar.
ESPERA_TRAS_TROPIEZO = 20.0

MAXIMO_VUELOS = 8


@dataclass
class Vuelo:
    """Un bot en el aire: su hilo, sus señales y cuándo arrancó.

    Cada uno con los suyos y no compartidos: con un solo evento de parada,
    apagar un bot apagaría los cinco.
    """

    bot: Bot
    hilo: threading.Thread | None = None
    parar: threading.Event = field(default_factory=threading.Event)
    despertar: threading.Event = field(default_factory=threading.Event)
    error: str = ""
    arrancado: str = ""
    #: Tropiezos SEGUIDOS del exchange (reloj, tiempo agotado, sobrecarga).
    #: Se vuelve a cero con cada vuelta buena; al tercero el bot se apaga.
    tropiezos: int = 0

    @property
    def encendido(self) -> bool:
        return bool(self.hilo and self.hilo.is_alive())


@dataclass
class Piloto:
    """Mantiene los bots corriendo, y los apaga cuando hay que apagarlos."""

    vuelos: dict[str, Vuelo] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------- consultar
    @property
    def encendido(self) -> bool:
        """Si hay AL MENOS uno volando."""
        return any(v.encendido for v in self.vuelos.values())

    @property
    def cuantos(self) -> int:
        return sum(1 for v in self.vuelos.values() if v.encendido)

    @property
    def porcion_usada(self) -> float:
        """Cuánto de la cuenta está comprometido por los que vuelan."""
        return round(sum(v.bot.porcion for v in self.vuelos.values()
                         if v.encendido), 4)

    def estado(self) -> dict[str, Any]:
        """Lo que la pantalla necesita saber. Nunca incluye una credencial."""
        return {
            "encendido": self.encendido,
            "hay_bot": bool(self.vuelos),
            "cuantos": self.cuantos,
            "porcion_usada": self.porcion_usada,
            "porcion_libre": round(max(0.0, 1.0 - self.porcion_usada), 4),
            "maximo": MAXIMO_VUELOS,
            "vuelos": [self._estado_de(v) for v in self.vuelos.values()],
        }

    def _estado_de(self, v: Vuelo) -> dict[str, Any]:
        b = v.bot
        return {
            "encendido": v.encendido,
            "nombre": b.doc.get("nombre", ""),
            "simbolo": b.simbolo,
            "timeframe": b.timeframe,
            "modo": b.modo,
            "porcion": b.porcion,
            "manda_ordenes": b.manda_ordenes,
            "detenido": b.detenido,
            "motivo_detencion": b.motivo_detencion,
            # SI TIENE UNA POSICIÓN SUYA ABIERTA, en una palabra: es lo primero
            # que uno quiere saber de un robot y había que deducirlo del registro.
            "en_posicion": bool(getattr(b.estado, "posicion_propia", False)),
            # CUÁNTO ARRIESGA Y CON QUÉ RED: lo que hace falta para dejarlo
            # corriendo tranquilo. El riesgo es el % de SU porción por
            # operación; el stop siempre va al exchange; el tope diario es el
            # que se le puso al encender (0 = sin tope).
            "riesgo_pct": self._riesgo_pct(b),
            "tope_diario": float(getattr(b, "perdida_maxima_diaria", 0.0) or 0.0),
            "arrancado": v.arrancado,
            "error": v.error,
            # CUANTO SE ESPERA QUE OPERE, según su propio backtest. Es lo que
            # convierte "hace una hora que no hace nada" de una duda en un
            # dato: una estrategia de once operaciones al mes entra cada dos o
            # tres días, y verla callada una tarde es lo normal, no un error.
            "esperado_mes": self._esperado_mes(b),
            # Las últimas vueltas, de la más nueva a la más vieja: es como se
            # lee un registro cuando uno quiere saber qué acaba de pasar.
            "registro": list(reversed(b.registro[-40:])),

            # ¿Está operando como decía que iba a operar? Se calcula sobre el
            # registro ENTERO y no sobre las últimas cuarenta: recortar la
            # ventana haría que un bot viejo pareciera que nunca opera.
            "vigilante": self._vigilar(b, v),

            # Y CÓMO LE VA, que es la otra mitad. El vigilante mira cuánto
            # opera; esto mira si sigue rindiendo como decía el backtest.
            # Van separados porque se contestan en momentos distintos: la
            # frecuencia se estabiliza en semanas y el rendimiento en meses.
            "semaforo": self._semaforo(b),
        }

    @staticmethod
    def _riesgo_pct(b: Bot) -> float | None:
        try:
            r = b.spec.risk
            if getattr(r, "size_mode", "") == "risk_pct":
                return round(float(r.size_value), 2)
        except Exception:  # noqa: BLE001 — un doc viejo sin riesgo no rompe el estado
            return None
        return None

    @staticmethod
    def _esperado_mes(b: Bot) -> float | None:
        m = b.doc.get("respaldo") or {}
        tpm = m.get("trades_per_month")
        if tpm:
            return round(float(tpm), 1)
        trades, years = m.get("trades"), m.get("years")
        if trades and years:
            return round(float(trades) / (float(years) * 12.0), 1)
        return None

    def _vigilar(self, b: Bot, v: Vuelo) -> dict[str, Any]:
        r = vigilante.revisar(b.doc.get("respaldo") or {}, b.registro,
                              v.arrancado or None)
        return {"estado": r.estado, "razon": r.razon,
                "esperadas": round(r.esperadas, 2), "observadas": r.observadas}

    def _semaforo(self, b: Bot) -> dict[str, Any]:
        r = semaforo.revisar(b.registro, b.doc.get("respaldo") or {})
        return {"estado": r.estado, "motivo": r.motivo,
                "recomendacion": r.recomendacion, "cerradas": r.cerradas,
                "pf_vivo": r.pf_vivo, "pf_base": r.pf_base,
                "conserva": r.conserva}

    # -------------------------------------------------------------- encender
    def encender(self, bot: Bot) -> dict[str, Any]:
        """Pone un bot en el aire, si el símbolo está libre y la cuenta alcanza."""
        with self._lock:
            simbolo = bot.simbolo
            self._limpiar()

            # EL CHOQUE ES POR SIMBOLO Y NO POR CUENTA. Ver el encabezado.
            vivo = self.vuelos.get(simbolo)
            if vivo is not None and vivo.encendido:
                raise RuntimeError(
                    f"Ya hay un bot operando {simbolo}. Dos bots sobre el "
                    f"mismo símbolo se pelean por la misma posición: el cierre "
                    f"de uno es la apertura del otro. Podés encender otro en "
                    f"un símbolo distinto.")

            if self.cuantos >= MAXIMO_VUELOS:
                raise RuntimeError(
                    f"Ya hay {MAXIMO_VUELOS} bots operando, que es el tope. No "
                    f"es un límite técnico: cada bot es una posición que "
                    f"alguien tiene que poder mirar.")

            # LAS PORCIONES NO PUEDEN SUMAR MAS QUE LA CUENTA, y este es el
            # único lugar que las ve a todas. Cada bot solo no puede saberlo.
            usada = self.porcion_usada
            if usada + bot.porcion > 1.0 + 1e-9:
                raise RuntimeError(
                    f"Las porciones no entran en la cuenta: los bots que ya "
                    f"están operando usan el {usada * 100:.0f}% y este pide el "
                    f"{bot.porcion * 100:.0f}%. Entre todos arriesgarían más "
                    f"de lo que hay.")

            v = Vuelo(bot=bot)
            v.arrancado = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
            v.hilo = threading.Thread(target=self._bucle, args=(v,), daemon=True,
                                      name=f"piloto-{simbolo}")
            self.vuelos[simbolo] = v
            v.hilo.start()
        return self.estado()

    def _limpiar(self) -> None:
        """Saca los que ya no vuelan y no tienen nada que contar.

        Se queda con los que murieron por un ERROR: ese estado es justamente lo
        que alguien va a querer leer cuando pregunte por qué se apagó.
        """
        for s, v in list(self.vuelos.items()):
            if not v.encendido and not v.error and not v.bot.detenido:
                del self.vuelos[s]

    # ---------------------------------------------------------------- apagar
    def apagar(self, simbolo: str | None = None,
               espera: float = 10.0) -> dict[str, Any]:
        """Deja de operar. NO cierra la posición que haya abierta.

        Es a propósito y hay que decirlo en la pantalla: apagar el bot y cerrar
        la posición son dos decisiones distintas. Alguien que apaga porque se
        va a dormir quiere que el stop del exchange siga cuidando la posición,
        no que se cierre a mercado en el peor momento.

        Sin símbolo apaga TODOS. Es el botón de "me voy", y que exista uno solo
        para todo evita el caso peor: apagar cuatro de cinco creyendo que se
        apagaron los cinco.
        """
        for v in self._elegidos(simbolo):
            v.parar.set()
            v.despertar.set()
        for v in self._elegidos(simbolo):
            if v.hilo and v.hilo.is_alive():
                v.hilo.join(timeout=espera)
        return self.estado()

    def _elegidos(self, simbolo: str | None) -> list[Vuelo]:
        if simbolo is None:
            return list(self.vuelos.values())
        v = self.vuelos.get(simbolo)
        return [v] if v is not None else []

    def panico(self, simbolo: str | None = None) -> dict[str, Any]:
        """Apaga Y cierra lo que haya abierto. El botón para cuando algo pasa.

        EL ORDEN ES LO ÚNICO QUE IMPORTA ACÁ, y la primera versión lo tenía a
        medias. Decía —con razón— que hay que apagar antes de cerrar, porque al
        revés el bucle podría ver la posición cerrada y abrir otra. Pero apagar
        espera al hilo con un tope de diez segundos, y una vuelta trabada en
        una llamada de red le sobrevive: seguía viva, cerrábamos la posición, y
        esa vuelta abría otra encima.

        Por eso ahora primero se FRENA el bot —una marca que `paso` mira otra
        vez justo antes de mandar la orden— y después se apaga y se cierra.
        Frenar es instantáneo y no depende de que ningún hilo conteste.

        SE FRENAN TODOS ANTES DE CERRAR NINGUNO. Con varios bots, cerrar el
        primero mientras el quinto sigue vivo le da a ese quinto una vuelta
        entera para abrir algo nuevo mientras uno cree que está vaciando la
        cuenta.
        """
        elegidos = self._elegidos(simbolo)
        for v in elegidos:
            v.bot.detenido = True
            v.bot.motivo_detencion = "pánico"
        self.apagar(simbolo)

        cerrados: dict[str, Any] = {}
        for v in elegidos:
            b = v.bot
            try:
                pos = b.adaptador.posicion(b.simbolo)
                cerrado = (b.adaptador.cerrar(b.simbolo, pos) if pos.abierta
                           else "no había posición abierta")
            except Exception as exc:                          # noqa: BLE001
                cerrado = f"no se pudo cerrar: {exc}"
            b.registro.append({"cuando": pd.Timestamp.now(tz="UTC").isoformat(),
                               "accion": "panico", "resultado": cerrado})
            cerrados[b.simbolo] = cerrado

        e = self.estado()
        e["cerrado"] = cerrados or "no había bot"
        return e

    # ----------------------------------------------------------- el bucle
    def _espera(self, b: Bot) -> float:
        """Cuántos segundos hasta mirar de nuevo.

        Se calcula desde el reloj y no desde el arranque: si una vuelta tardó
        cuarenta segundos, la siguiente no se corre cuarenta segundos: se
        alinea igual con el cierre de la vela.
        """
        dur = DURACION.get(b.timeframe, 3600)
        ahora = pd.Timestamp.now(tz="UTC").timestamp()
        falta = dur - (ahora % dur) + GRACIA
        return min(max(falta, 1.0), MAXIMA_ESPERA)

    def _bucle(self, v: Vuelo) -> None:
        b = v.bot
        while not v.parar.is_set():
            try:
                b.paso()
                v.tropiezos = 0
            except BinanceError as exc:
                # UN TROPIEZO DEL EXCHANGE NO APAGA EL BOT A LA PRIMERA.
                #
                # Pasó de verdad: Binance rechazó un pedido con -1021 —el
                # reloj de la PC iba cuatro segundos atrás— y dos bots se
                # apagaron en plena vela por un error que un segundo después
                # ya no estaba. Apagarse ante lo transitorio es dejar la
                # cartera a medias cada vez que la red parpadea.
                #
                # Tres seguidos sí apagan: a esa altura no es un parpadeo, y
                # seguir insistiendo contra algo que rechaza es la forma de
                # mandar órdenes malas en fila. Lo que no es transitorio
                # —clave, permisos, símbolo— apaga a la primera, como antes.
                transitorio = (exc.codigo in TRANSITORIOS
                               or str(exc).startswith("No se pudo conectar"))
                v.tropiezos += 1
                if transitorio and v.tropiezos < TROPIEZOS_MAXIMOS:
                    b.registro.append({
                        "cuando": pd.Timestamp.now(tz="UTC").isoformat(),
                        "accion": "reintento",
                        "motivo": f"{exc.del_exchange} ({v.tropiezos} de "
                                  f"{TROPIEZOS_MAXIMOS})"})
                    v.despertar.wait(ESPERA_TRAS_TROPIEZO)
                    v.despertar.clear()
                    continue
                v.error = exc.del_exchange
                b.registro.append({
                    "cuando": pd.Timestamp.now(tz="UTC").isoformat(),
                    "accion": "apagado por el exchange", "motivo": v.error})
                return
            except BingXError as exc:
                # El exchange rechazo algo y DIJO por que. Es el caso mas
                # probable de todos —la clave mal, vencida, o sin permiso de
                # trading— y merece el mensaje del exchange y no un traceback:
                # quien lo lea tiene que poder arreglarlo, no adivinar.
                v.error = exc.del_exchange
                b.registro.append({
                    "cuando": pd.Timestamp.now(tz="UTC").isoformat(),
                    "accion": "apagado por el exchange", "motivo": v.error})
                return
            except Exception:                                 # noqa: BLE001
                # Un error inesperado APAGA el bot en vez de reintentar en
                # bucle. Reintentar a ciegas contra un exchange que rechaza
                # algo es la forma de mandar cien órdenes malas en un minuto.
                #
                # Se guarda el traceback ENTERO y no un resumen: si llego
                # hasta aca es algo que no previmos, y recortarlo tira justo
                # lo que hace falta para entenderlo.
                v.error = traceback.format_exc(limit=5)
                b.registro.append({
                    "cuando": pd.Timestamp.now(tz="UTC").isoformat(),
                    "accion": "apagado por error", "motivo": v.error[-300:]})
                return
            if b.detenido:
                # Una guarda pidió detenerse: se sale del bucle y hace falta una
                # persona. Seguir dando vueltas sólo llenaría el registro.
                return
            v.despertar.wait(self._espera(b))
            v.despertar.clear()


#: El piloto del proceso. Uno solo, y adentro los vuelos que haya.
PILOTO = Piloto()
