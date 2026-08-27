"""Encender y apagar el bot, que es lo único que faltaba para que opere.

El `Bot` de `runner.py` sabe dar UNA vuelta. Esto es lo que lo despierta cuando
cierra cada vela, lo apaga cuando alguien lo pide, y lo apaga solo cuando algo
sale mal. Vive acá y no en el `JobManager` porque aquél está hecho para
trabajos que terminan: un minado corre, entrega un resultado y libera el cupo.
Un bot no termina nunca, y meterlo en esa cola le sacaría el lugar a las
búsquedas de la persona hasta que lo apague.

UN SOLO BOT A LA VEZ, Y NO ES UNA LIMITACIÓN TÉCNICA. Dos bots sobre la misma
cuenta se pelean por la misma posición: uno abre, el otro ve una posición que
él no abrió, se detiene, y el primero sigue creyendo que está solo. Peor si los
dos operan el mismo símbolo — el cierre de uno es la apertura del otro. Hasta
que exista una idea clara de cómo repartir el capital entre estrategias, uno.

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


@dataclass
class Piloto:
    """Mantiene un bot corriendo, y lo apaga cuando hay que apagarlo."""

    bot: Bot | None = None
    hilo: threading.Thread | None = None
    _parar: threading.Event = field(default_factory=threading.Event)
    _despertar: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    error: str = ""
    arrancado: str = ""

    # ------------------------------------------------------------- consultar
    @property
    def encendido(self) -> bool:
        return bool(self.hilo and self.hilo.is_alive())

    def estado(self) -> dict[str, Any]:
        """Lo que la pantalla necesita saber. Nunca incluye una credencial."""
        b = self.bot
        if b is None:
            return {"encendido": False, "hay_bot": False}
        return {
            "encendido": self.encendido,
            "hay_bot": True,
            "nombre": b.doc.get("nombre", ""),
            "simbolo": b.simbolo,
            "timeframe": b.timeframe,
            "modo": b.modo,
            "manda_ordenes": b.manda_ordenes,
            "detenido": b.detenido,
            "motivo_detencion": b.motivo_detencion,
            "arrancado": self.arrancado,
            "error": self.error,
            # Las últimas vueltas, de la más nueva a la más vieja: es como se
            # lee un registro cuando uno quiere saber qué acaba de pasar.
            "registro": list(reversed(b.registro[-40:])),

            # ¿Está operando como decía que iba a operar? Se calcula sobre el
            # registro ENTERO y no sobre las últimas cuarenta: recortar la
            # ventana haría que un bot viejo pareciera que nunca opera.
            "vigilante": self._vigilar(),

            # Y CÓMO LE VA, que es la otra mitad. El vigilante mira cuánto
            # opera; esto mira si sigue rindiendo como decía el backtest.
            # Van separados porque se contestan en momentos distintos: la
            # frecuencia se estabiliza en semanas y el rendimiento en meses.
            "semaforo": self._semaforo(),
        }

    def _vigilar(self) -> dict[str, Any]:
        b = self.bot
        if b is None:
            return {"estado": vigilante.CALLADO, "razon": ""}
        v = vigilante.revisar(b.doc.get("respaldo") or {}, b.registro,
                              self.arrancado or None)
        return {"estado": v.estado, "razon": v.razon,
                "esperadas": round(v.esperadas, 2), "observadas": v.observadas}

    def _semaforo(self) -> dict[str, Any]:
        b = self.bot
        if b is None:
            return {"estado": semaforo.CALLADO, "motivo": ""}
        v = semaforo.revisar(b.registro, b.doc.get("respaldo") or {})
        return {"estado": v.estado, "motivo": v.motivo,
                "recomendacion": v.recomendacion, "cerradas": v.cerradas,
                "pf_vivo": v.pf_vivo, "pf_base": v.pf_base,
                "conserva": v.conserva}

    # -------------------------------------------------------------- encender
    def encender(self, bot: Bot) -> dict[str, Any]:
        with self._lock:
            if self.encendido:
                raise RuntimeError(
                    "Ya hay un bot encendido. Apagalo antes de encender otro: "
                    "dos bots sobre la misma cuenta se pelean por la misma "
                    "posición.")
            self.bot = bot
            self.error = ""
            self.arrancado = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
            self._parar.clear()
            self._despertar.clear()
            self.hilo = threading.Thread(target=self._bucle, daemon=True,
                                         name="piloto")
            self.hilo.start()
        return self.estado()

    def apagar(self, espera: float = 10.0) -> dict[str, Any]:
        """Deja de operar. NO cierra la posición que haya abierta.

        Es a propósito y hay que decirlo en la pantalla: apagar el bot y cerrar
        la posición son dos decisiones distintas. Alguien que apaga porque se
        va a dormir quiere que el stop del exchange siga cuidando la posición,
        no que se cierre a mercado en el peor momento.
        """
        self._parar.set()
        self._despertar.set()
        h = self.hilo
        if h and h.is_alive():
            h.join(timeout=espera)
        return self.estado()

    def panico(self) -> dict[str, Any]:
        """Apaga Y cierra lo que haya abierto. El botón para cuando algo pasa.

        Se apaga PRIMERO y se cierra después: al revés, el bucle podría
        despertarse entre las dos cosas, ver la posición cerrada y abrir otra.
        """
        self.apagar()
        b = self.bot
        cerrado: Any = "no había bot"
        if b is not None:
            try:
                pos = b.adaptador.posicion(b.simbolo)
                cerrado = (b.adaptador.cerrar(b.simbolo, pos) if pos.abierta
                           else "no había posición abierta")
            except Exception as exc:                          # noqa: BLE001
                cerrado = f"no se pudo cerrar: {exc}"
            b.registro.append({"cuando": pd.Timestamp.now(tz="UTC").isoformat(),
                               "accion": "panico", "resultado": cerrado})
        e = self.estado()
        e["cerrado"] = cerrado
        return e

    # ----------------------------------------------------------- el bucle
    def _espera(self) -> float:
        """Cuántos segundos hasta mirar de nuevo.

        Se calcula desde el reloj y no desde el arranque: si una vuelta tardó
        cuarenta segundos, la siguiente no se corre cuarenta segundos: se
        alinea igual con el cierre de la vela.
        """
        b = self.bot
        dur = DURACION.get(b.timeframe if b else "1h", 3600)
        ahora = pd.Timestamp.now(tz="UTC").timestamp()
        falta = dur - (ahora % dur) + GRACIA
        return min(max(falta, 1.0), MAXIMA_ESPERA)

    def _bucle(self) -> None:
        b = self.bot
        assert b is not None
        while not self._parar.is_set():
            try:
                b.paso()
            except BingXError as exc:
                # El exchange rechazo algo y DIJO por que. Es el caso mas
                # probable de todos —la clave mal, vencida, o sin permiso de
                # trading— y merece el mensaje del exchange y no un traceback:
                # quien lo lea tiene que poder arreglarlo, no adivinar.
                self.error = exc.del_exchange
                b.registro.append({
                    "cuando": pd.Timestamp.now(tz="UTC").isoformat(),
                    "accion": "apagado por el exchange", "motivo": self.error})
                return
            except Exception:                                 # noqa: BLE001
                # Un error inesperado APAGA el bot en vez de reintentar en
                # bucle. Reintentar a ciegas contra un exchange que rechaza
                # algo es la forma de mandar cien órdenes malas en un minuto.
                #
                # Se guarda el traceback ENTERO y no un resumen: si llego
                # hasta aca es algo que no previmos, y recortarlo tira justo
                # lo que hace falta para entenderlo.
                self.error = traceback.format_exc(limit=5)
                b.registro.append({
                    "cuando": pd.Timestamp.now(tz="UTC").isoformat(),
                    "accion": "apagado por error", "motivo": self.error[-300:]})
                return
            if b.detenido:
                # Una guarda pidió detenerse: se sale del bucle y hace falta una
                # persona. Seguir dando vueltas sólo llenaría el registro.
                return
            self._despertar.wait(self._espera())
            self._despertar.clear()


#: El piloto del proceso. Uno solo, por la razón del encabezado.
PILOTO = Piloto()
