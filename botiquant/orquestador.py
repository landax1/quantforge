"""El que ejecuta lo que el ciclo decide. Es la pieza que lo hace correr solo.

`ciclo.que_toca` decide y no hace nada. Esto hace, y no decide nada. Están
separados porque un sistema autónomo hay que poder probarlo entero sin dejarlo
suelto: se le pregunta qué haría y se comprueba la respuesta, sin que toque una
sola estrategia.

CORRE EN SU PROPIO HILO Y NO EN EL JOBMANAGER. Aquel está hecho para trabajos
que terminan: un minado corre, entrega un resultado y libera el cupo. El ciclo
no termina nunca, y meterlo en esa cola le sacaría el lugar a las búsquedas de
la persona hasta que lo apague.

UNA VUELTA HACE UNA COSA SOLA. Es deliberado y va contra la intuición: parece
más eficiente encadenar validar-promover-minar en una pasada. Pero cada acción
cambia el estado del mundo, y la decisión siguiente tiene que tomarse sobre el
mundo nuevo. Encadenando, el ciclo promueve sobre una foto vieja — y con un
tope de cinco en práctica eso significa promover seis.

LO QUE NUNCA HACE, aunque esté encendido:

  * encender algo con plata real
  * retirar sin dejar el motivo escrito
  * saltearse la cantera

Las tres son de `estados` y `ciclo`, y este archivo no las puede eludir porque
no las conoce: le pide a esos módulos que decidan y ejecuta lo que digan.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from botiquant import ciclo, estados

#: Cada cuánto se despierta a mirar si hay algo que hacer. No es cada cuánto
#: mina: eso lo dice `minar_cada_horas`. Un minuto es suficiente —las
#: decisiones se miden en horas— y hace que apagar el ciclo tenga efecto
#: enseguida.
LATIDO_SEGUNDOS = 60


@dataclass
class Vuelta:
    """Qué hizo el ciclo en una pasada, para el registro."""

    cuando: str
    accion: str
    motivo: str
    ids: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {"cuando": self.cuando, "accion": self.accion, "motivo": self.motivo}
        if self.ids:
            d["ids"] = self.ids
        if self.error:
            d["error"] = self.error
        return d


class Orquestador:
    """Corre el ciclo. Una vuelta por minuto, una acción por vuelta."""

    def __init__(self, *, leer_estado: Callable[[], dict[str, Any]],
                 acciones: dict[str, Callable[[list[str]], Any]]):
        """
        `leer_estado` devuelve lo que hace falta para decidir: las estrategias,
        cuántas horas pasaron del último minado y cuántas están en práctica.
        `acciones` son las funciones que hacen cada cosa.

        Se reciben de afuera y no se importan acá para que el orquestador se
        pueda probar sin base de datos, sin red y sin esperar una hora: se le
        pasan funciones de mentira y se comprueba a cuáles llamó.
        """
        self.leer_estado = leer_estado
        self.acciones = acciones
        self.params = ciclo.Parametros()
        self.registro: list[Vuelta] = []
        self.error = ""
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._despertar = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------- consulta
    @property
    def corriendo(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def que_haria(self, *, aunque_este_apagado: bool = False) -> ciclo.Tarea:
        """Qué haría ahora, sin hacerlo.

        Es lo que se le muestra al usuario antes de dejarlo suelto, y lo que
        permite probar el ciclo entero sin que toque nada.

        `aunque_este_apagado` existe porque `encendido` significa "corre
        SOLO", no "puede decidir". Sin esto, el paso a mano —que existe justo
        para verlo actuar sin dejarlo suelto— no hacía nada mientras el ciclo
        estuviera apagado, que es exactamente cuando uno lo quiere usar.
        Encontrado usándolo.
        """
        p = self.params
        if aunque_este_apagado and not p.encendido:
            p = ciclo.Parametros.from_dict({**p.to_dict(), "encendido": True})
        e = self.leer_estado()
        return ciclo.que_toca(
            p,
            estrategias=e.get("estrategias") or [],
            horas_desde_el_ultimo_minado=float(e.get("horas_desde_minado") or 0.0),
            en_practica=int(e.get("en_practica") or 0))

    def estado(self) -> dict[str, Any]:
        tarea = self.que_haria()
        return {
            "corriendo": self.corriendo,
            "params": self.params.to_dict(),
            "proxima": {"accion": tarea.accion, "motivo": tarea.motivo,
                        "ids": tarea.ids},
            "error": self.error,
            # Las últimas cuarenta alcanzan para entender qué viene haciendo;
            # el registro entero crece sin límite mientras el ciclo corra.
            "registro": [v.to_dict() for v in self.registro[-40:]][::-1],
        }

    # ------------------------------------------------------------- ejecución
    def una_vuelta(self, *, a_mano: bool = False) -> Vuelta:
        """Decide y ejecuta UNA acción. Devuelve qué hizo.

        `a_mano` es un pedido explícito de una persona y por eso ignora el
        interruptor: apagar el ciclo detiene el bucle automático, no la
        capacidad de darle un paso mirando.
        """
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tarea = self.que_haria(aunque_este_apagado=a_mano)
        v = Vuelta(ahora, tarea.accion, tarea.motivo, list(tarea.ids))

        if tarea.accion == ciclo.NADA:
            return v

        hacer = self.acciones.get(tarea.accion)
        if hacer is None:
            # Una acción sin quien la haga NO se anota como hecha. Si no, el
            # registro diría que promovió algo que sigue donde estaba.
            v.error = f"no hay quién haga «{tarea.accion}»"
            self.registro.append(v)
            return v

        try:
            hacer(tarea.ids)
        except Exception:                                     # noqa: BLE001
            # Un error NO apaga el ciclo, a diferencia del bot: acá una vuelta
            # que falla es una estrategia que no se validó, no una orden que
            # no salió. Se anota y se sigue, porque el problema puede ser de
            # una sola estrategia y apagar todo por eso sería peor.
            v.error = traceback.format_exc(limit=3)[-400:]
        self.registro.append(v)
        return v

    # -------------------------------------------------------------- encender
    def encender(self, params: ciclo.Parametros | None = None) -> None:
        with self._lock:
            if params is not None:
                self.params = params
            if self.corriendo:
                return
            self.error = ""
            self._parar.clear()
            self._hilo = threading.Thread(target=self._bucle, daemon=True,
                                          name="botiquant-ciclo")
            self._hilo.start()

    def apagar(self) -> None:
        self._parar.set()
        # Se lo despierta para que el apagado tenga efecto ya y no dentro de
        # un minuto: quien aprieta apagar quiere que pare ahora.
        self._despertar.set()
        h = self._hilo
        if h is not None and h.is_alive():
            h.join(timeout=5)
        self._hilo = None

    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                self.una_vuelta()
            except Exception:                                 # noqa: BLE001
                # Sólo llega acá lo que ni `una_vuelta` pudo manejar: leer el
                # estado falló. Eso sí apaga, porque sin poder leer no hay
                # decisión posible y seguir sería girar en el vacío.
                self.error = traceback.format_exc(limit=3)
                return
            self._despertar.wait(LATIDO_SEGUNDOS)
            self._despertar.clear()


#: El ciclo del proceso. Uno solo, como el piloto: dos orquestadores sobre las
#: mismas estrategias se pisarían promoviendo y retirando lo mismo.
ORQUESTADOR: Orquestador | None = None
