"""Los parámetros con los que el programa se maneja solo, y qué hacer ahora.

La idea del producto es un software que mina, prueba, promueve, opera y retira
sin que nadie esté mirando. Todo eso ya existe por separado. Lo que falta es la
pieza que decide QUÉ TOCA HACER, y estos son los números con los que decide.

POR QUÉ ESTÁ ACÁ Y NO ADENTRO DEL ORQUESTADOR. Porque decidir es una cosa y
hacer es otra. Así se puede preguntar "¿qué harías ahora?" sin que haga nada —
que es como se prueba un sistema autónomo sin dejarlo suelto, y también cómo se
le muestra al usuario lo que va a pasar antes de que pase.

LOS VALORES POR DEFECTO SON DELIBERADAMENTE TÍMIDOS. Un ciclo que arranca
minando cada hora y promoviendo solo es un ciclo que nadie va a dejar prendido.
Los defaults tienen que producir un sistema del que uno se pueda ir tranquilo
la primera noche, y ya habrá tiempo de apretarlos.

LO QUE ESTE ARCHIVO NO DECIDE: encender con plata real. La promoción
automática llega hasta práctica y ahí se detiene. Que algo pase a operar con
plata de verdad es una decisión de una persona, aunque todo lo demás corra
solo. Si algún día se automatiza, se cambia acá y a propósito.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from botiquant import estados


@dataclass
class Parametros:
    """Con qué se maneja el ciclo. Todo esto lo define el usuario."""

    #: Si el ciclo corre. Apagado por defecto: nadie estrena un sistema
    #: autónomo prendiéndolo sin mirar qué hace.
    encendido: bool = False

    # ------------------------------------------------------------- minar
    #: Cada cuántas horas busca estrategias nuevas. Doce y no una: minar es
    #: lo más caro que hace la aplicación —veinte minutos con 1.500
    #: candidatas— y encontrar cosas más rápido no sirve de nada si el
    #: cuello de botella es probarlas.
    minar_cada_horas: int = 12
    candidatas_por_vuelta: int = 1500
    #: Qué instrumentos entran en la rotación. Vacío = los que estén bajados.
    instrumentos: list[str] = field(default_factory=list)

    #: Cuánto del histórico se reserva. Es lo que separa "encontré algo" de
    #: "aguantó donde no miré", y sin esto nada puede llegar a real.
    reservar_pct: int = 30

    # ------------------------------------------------------------ validar
    #: Cuántas guardadas valida por vuelta. Pocas a propósito: cada una es un
    #: backtest completo más mil simulaciones.
    validar_por_vuelta: int = 5

    # ----------------------------------------------------------- promover
    #: Cuántas estrategias puede tener corriendo a la vez. Es el número que
    #: más importa: cada una es una porción del capital, y el informe del que
    #: salió esto reparte 3-5% por bot.
    max_en_practica: int = 5
    #: Hasta dónde promueve solo. Ver el encabezado: llega hasta práctica.
    promover_hasta: str = estados.PRACTICA

    #: Cuántas estrategias del MISMO instrumento pueden correr a la vez.
    #:
    #: Es el filtro barato contra los gemelos ocultos. Medido sobre las cinco
    #: que el ciclo puso en práctica: dos de BTCUSDT correlacionan +0,71 y dos
    #: de S&P +0,64, mientras que entre instrumentos distintos va de -0,18 a
    #: +0,11. Nombres distintos, reglas distintas, y se mueven juntas.
    #:
    #: Dos y no una: dos estrategias sobre el mismo mercado PUEDEN ser
    #: opuestas —una de tendencia y una de reversión— y prohibirlo del todo
    #: dejaría afuera diversificación real. Dos es el punto donde todavía se
    #: puede argumentar y tres ya es concentración.
    max_por_instrumento: int = 2

    # ------------------------------------------------------------ retirar
    #: Con el semáforo en naranja, cuántas vueltas espera antes de retirar.
    #: No cero: un naranja puede volver a verde, y retirar de inmediato haría
    #: que el ciclo se coma sus propias estrategias en una racha mala.
    vueltas_en_naranja: int = 3

    #: Si el ciclo RETIRA solo, o sólo dice a quién retiraría.
    #:
    #: APAGADO POR OMISION, y el motivo lo escribe el propio semáforo: "hace
    #: falta que alguien vea el semáforo cambiar de color varias veces y decida
    #: si le cree". Hasta entonces el ciclo señala y no ejecuta.
    #:
    #: Es además la dirección segura del error. Apagado, el ciclo deja
    #: corriendo algo que habría que sacar — y eso lo ve una persona. Prendido
    #: y equivocado, retira estrategias buenas sin que nadie se entere.
    retirar_solo: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Parametros":
        d = d or {}
        base = cls()

        def entero(clave: str, minimo: int, maximo: int) -> int:
            try:
                return max(minimo, min(int(d.get(clave, getattr(base, clave))), maximo))
            except (TypeError, ValueError):
                return getattr(base, clave)

        destino = str(d.get("promover_hasta") or base.promover_hasta)
        return cls(
            encendido=bool(d.get("encendido", base.encendido)),
            minar_cada_horas=entero("minar_cada_horas", 1, 168),
            candidatas_por_vuelta=entero("candidatas_por_vuelta", 100, 50_000),
            instrumentos=[str(x) for x in (d.get("instrumentos") or [])][:20],
            reservar_pct=entero("reservar_pct", 0, 60),
            validar_por_vuelta=entero("validar_por_vuelta", 1, 50),
            max_por_instrumento=entero("max_por_instrumento", 1, 10),
            max_en_practica=entero("max_en_practica", 1, 20),
            # NO se acepta `produccion` aunque venga en el payload. La
            # promoción automática a plata real no es una preferencia que se
            # configura: es una decisión que se toma una vez, en el código, y
            # hoy la respuesta es no.
            promover_hasta=(destino if destino in (estados.VALIDADA, estados.PRACTICA)
                            else base.promover_hasta),
            vueltas_en_naranja=entero("vueltas_en_naranja", 1, 50),
            retirar_solo=bool(d.get("retirar_solo", base.retirar_solo)),
        )


# --------------------------------------------------------------- qué toca

MINAR = "minar"
VALIDAR = "validar"
PROMOVER = "promover"
RETIRAR = "retirar"
NADA = "nada"


@dataclass
class Tarea:
    """Lo que el ciclo haría ahora, y por qué. No lo hace: lo dice."""

    accion: str = NADA
    motivo: str = ""
    #: A quién le toca, cuando aplica.
    ids: list[str] = field(default_factory=list)
    #: Quiénes cumplen la condición de retiro, SE VAYAN A RETIRAR O NO.
    #:
    #: Va aparte de `ids` porque con el retiro automático apagado el ciclo
    #: sigue su camino —promueve, mina— y aun así tiene que poder decir "yo
    #: sacaría estas tres". Si eso viajara en `ids`, la pantalla no podría
    #: distinguir a quién le toca la acción de a quién se está señalando.
    retirables: list[str] = field(default_factory=list)


def que_toca(p: Parametros, *, estrategias: list[dict[str, Any]],
             horas_desde_el_ultimo_minado: float,
             en_practica: int = 0) -> Tarea:
    """Qué haría el ciclo en este momento. Sin efectos: sólo decide.

    EL ORDEN NO ES CASUAL. Va de lo que libera capital a lo que lo consume:
    primero se saca lo que está fallando, después se promueve lo que está
    listo, y recién al final se busca más. Al revés, el ciclo llena los
    lugares con estrategias nuevas y sin probar mientras deja corriendo las
    que ya se agotaron.
    """
    if not p.encendido:
        return Tarea(NADA, "el ciclo está apagado")

    # 1) retirar libera un lugar
    #
    # SE CALCULA SIEMPRE Y SE EJECUTA SOLO SI EL INTERRUPTOR ESTA PRENDIDO. Con
    # el retiro automático apagado el ciclo igual sabe a quién sacaría, y eso
    # es lo que le permite a una persona ver el semáforo cambiar de color
    # varias veces y decidir si le cree antes de dejarlo actuar.
    retirables = [e["id"] for e in estrategias
                  if e.get("vueltas_en_naranja", 0) >= p.vueltas_en_naranja]
    marca = dict(retirables=list(retirables))
    if retirables and p.retirar_solo:
        return Tarea(RETIRAR,
                     f"{len(retirables)} llevan {p.vueltas_en_naranja} vueltas "
                     f"en naranja", retirables, **marca)

    # 2) promover lo que ya está probado, si queda lugar
    if en_practica < p.max_en_practica:
        # CUANTAS DE CADA INSTRUMENTO YA ESTAN CORRIENDO. Sin esto el ciclo
        # promueve por orden de llegada, y si un dia encuentra tres estrategias
        # buenisimas de Bitcoin promueve las tres — y eso no es un portafolio
        # de tres, es una apuesta con tres nombres.
        corriendo = {}
        for e in estrategias:
            if estados.normalizar(e.get("estado")) in (estados.PRACTICA,
                                                       estados.PRODUCCION):
                inst = str(e.get("instrumento") or "")
                if inst:
                    corriendo[inst] = corriendo.get(inst, 0) + 1

        listas, llenos, inoperables = [], set(), 0
        for e in estrategias:
            if estados.normalizar(e.get("estado")) != estados.VALIDADA:
                continue
            if not (e.get("cantera") or {}).get("practica"):
                continue
            # LO QUE EL BOT NO PUEDE ENCENDER NO SE PROMUEVE. Pasó: el ciclo
            # promovió una con trailing, el bot la rechazó al arrancar y la
            # estrategia quedó en "práctica" sin operar, ocupando un lugar en
            # la pantalla y ninguno en la cuenta. Quien lee las filas dice si
            # es operable; si no lo dice, se asume que sí.
            if e.get("operable") is False:
                inoperables += 1
                continue
            inst = str(e.get("instrumento") or "")
            # Sin instrumento conocido no se puede juzgar la concentracion, y
            # frenarla por eso seria castigarla por un dato que falta.
            if inst and corriendo.get(inst, 0) >= p.max_por_instrumento:
                llenos.add(inst)
                continue
            listas.append(e["id"])
            if inst:
                corriendo[inst] = corriendo.get(inst, 0) + 1

        if listas:
            hueco = p.max_en_practica - en_practica
            motivo = (f"hay {hueco} lugar(es) libre(s) y {len(listas)} "
                      f"validada(s) esperando")
            if llenos:
                motivo += f"; {len(llenos)} instrumento(s) ya al tope"
            if inoperables:
                motivo += f"; {inoperables} que el bot no puede encender"
            return Tarea(PROMOVER, motivo, listas[:hueco], **marca)

    # 3) validar lo que se encontró y nadie probó
    sin_probar = [e["id"] for e in estrategias
                  if estados.normalizar(e.get("estado")) == estados.NUEVA]
    if sin_probar:
        return Tarea(VALIDAR, f"{len(sin_probar)} sin probar",
                     sin_probar[:p.validar_por_vuelta], **marca)

    # 4) y recién ahí, buscar más
    if horas_desde_el_ultimo_minado >= p.minar_cada_horas:
        return Tarea(MINAR,
                     f"pasaron {horas_desde_el_ultimo_minado:.0f} horas del "
                     f"último minado", **marca)

    faltan = p.minar_cada_horas - horas_desde_el_ultimo_minado
    return Tarea(NADA, f"nada que hacer; el próximo minado en {faltan:.0f} horas",
                 **marca)
