"""¿Sigue rindiendo como decía el backtest, o la ventaja se está agotando?

El vigilante mira CUÁNTO opera. Esto mira CÓMO LE VA, que es la otra mitad y
la que se puede contestar mucho más tarde: la frecuencia se estabiliza en
semanas y el rendimiento en meses.

TODA VENTAJA SE AGOTA. Un patrón que existió cinco años deja de existir cuando
suficiente gente lo opera, cuando cambia la estructura del mercado, o cuando
nunca existió y el backtest lo encontró por azar entre mil quinientas
candidatas. No hay forma de distinguir esos tres casos mirando el resultado —y
tampoco hace falta: la respuesta es la misma en los tres.

LA COMPARACIÓN ES CONTRA SU PROPIA LÍNEA BASE, no contra un número absoluto.
Una estrategia de 1,15 de profit factor que sigue en 1,15 está perfecta; una
de 1,80 que cayó a 1,20 se está agotando aunque 1,20 suene bien. El archivo
del bot lleva su `respaldo` adentro justamente para esto.

LOS TRES ESTADOS, y el cuarto que importa más:

    verde     rinde como se midió, o mejor. No se toca nada.
    amarillo  se desvió pero puede ser mala suerte. Se mira más seguido y se
              recomienda bajarle el tamaño a la mitad.
    naranja   perdió la ventaja. Se recomienda pasarlo a simulacro hasta que
              vuelva a demostrar que sirve.
    CALLADO   todavía no hay con qué opinar.

El cuarto es el que evita que esto se apague a la semana. Con doce operaciones
cerradas, un profit factor no dice nada: dos operaciones grandes lo mueven de
0,8 a 1,6. Opinar ahí es tirar una moneda con cara de análisis.

RECOMIENDA, NO APAGA. El informe del que salió esta idea baja el tamaño solo y
pasa bots a papel automáticamente. Con un bot y sin historial propio, actuar
solo sobre una muestra chica haría más daño que bien: lo que hace falta
primero es que alguien vea el semáforo cambiar de color varias veces y decida
si le cree. Cuando eso pase, actuar solo es cambiar una línea.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VERDE = "verde"
AMARILLO = "amarillo"
NARANJA = "naranja"
CALLADO = "callado"

#: Cuántas operaciones CERRADAS hacen falta antes de opinar.
#:
#: Treinta es el número que usa la referencia para readmitir un bot, y sirve
#: por el mismo motivo acá: con doce, dos operaciones grandes mueven el profit
#: factor de 0,8 a 1,6 y cualquier veredicto es una moneda con cara de
#: análisis.
CERRADAS_MINIMAS = 30

#: Qué fracción de su profit factor original tiene que conservar.
#:
#: La banda es ancha a propósito. Una estrategia real oscila: medido sobre las
#: cuatro de BTCUSDT, el profit factor fuera de muestra quedó entre 0,80 y
#: 0,90 del de adentro, y esas cuatro son las BUENAS — las que aguantaron. Un
#: umbral en 0,9 las habría marcado a todas en amarillo el primer mes.
AMARILLO_DESDE = 0.70
NARANJA_DESDE = 0.50


@dataclass
class Veredicto:
    estado: str = CALLADO
    motivo: str = ""
    #: Lo que se recomienda hacer, en palabras de quien va a leerlo.
    recomendacion: str = ""
    cerradas: int = 0
    pf_vivo: float | None = None
    pf_base: float | None = None
    #: Cuánto conserva de su ventaja original: 1,0 es igual que el backtest.
    conserva: float | None = None

    @property
    def hay_que_mirar(self) -> bool:
        return self.estado in (AMARILLO, NARANJA)


def _pf(cerradas: list[dict[str, Any]]) -> float | None:
    """Profit factor de lo operado en vivo: ganado sobre perdido.

    Devuelve None y no infinito cuando no hubo pérdidas: un profit factor
    infinito es exactamente la situación en la que no hay nada que medir, y
    tratarlo como un número altísimo pintaría de verde algo sin evaluar.
    """
    gano = sum(x for c in cerradas if (x := float(c.get("ganancia") or 0.0)) > 0)
    perdio = -sum(x for c in cerradas if (x := float(c.get("ganancia") or 0.0)) < 0)
    if perdio <= 1e-9:
        return None
    return gano / perdio


def revisar(registro: list[dict[str, Any]], respaldo: dict[str, Any]) -> Veredicto:
    """Compara lo operado en vivo contra la línea base del backtest.

    `registro` es el del bot entero —no las últimas filas que se muestran en
    pantalla— y `respaldo` son las métricas que viajan adentro del archivo.
    """
    cerradas = [f for f in (registro or [])
                if f.get("accion") == "cerrar" and f.get("ganancia") is not None]
    n = len(cerradas)

    pf_base = respaldo.get("profit_factor") if respaldo else None
    if not pf_base or pf_base <= 0:
        return Veredicto(CALLADO, "el backtest no dejó un profit factor con "
                                  "el que comparar", cerradas=n)

    if n < CERRADAS_MINIMAS:
        return Veredicto(
            CALLADO,
            f"{n} de {CERRADAS_MINIMAS} operaciones cerradas: todavía no "
            f"alcanza para opinar", cerradas=n, pf_base=pf_base)

    pf_vivo = _pf(cerradas)
    if pf_vivo is None:
        return Veredicto(CALLADO, "todavía no perdió ninguna: sin pérdidas no "
                                  "hay profit factor que comparar",
                         cerradas=n, pf_base=pf_base)

    conserva = pf_vivo / pf_base
    base = dict(cerradas=n, pf_vivo=round(pf_vivo, 3),
                pf_base=round(float(pf_base), 3), conserva=round(conserva, 3))
    pct = f"{conserva * 100:.0f}%"

    if conserva >= AMARILLO_DESDE:
        return Veredicto(
            VERDE, f"conserva el {pct} de su ventaja ({pf_vivo:.2f} contra "
                   f"{pf_base:.2f} del backtest)", "", **base)
    if conserva >= NARANJA_DESDE:
        return Veredicto(
            AMARILLO,
            f"bajó al {pct} de su ventaja ({pf_vivo:.2f} contra {pf_base:.2f})",
            "Puede ser mala suerte todavía. Conviene bajarle el tamaño a la "
            "mitad y mirarlo más seguido.", **base)
    return Veredicto(
        NARANJA,
        f"quedó en el {pct} de su ventaja ({pf_vivo:.2f} contra {pf_base:.2f})",
        "Pasalo a simulacro hasta que vuelva a demostrar que sirve. Treinta "
        "operaciones limpias, como cuando entró.", **base)


# ------------------------------------------------------------- la memoria

def actualizar(previa: dict[str, Any] | None, v: Veredicto, *,
               cuando: str = "") -> dict[str, Any]:
    """Lo que el semáforo RECUERDA entre vueltas. Sin esto no se retira nada.

    ==================================================================
    UN VEREDICTO SUELTO NO ALCANZA PARA DECIDIR: HACE FALTA UNA RACHA.
    ==================================================================

    `revisar` mira el momento y dice un color. Pero un naranja aislado puede
    ser una mala semana, y por eso el ciclo espera varias vueltas antes de
    sacar nada. Alguien tiene que contarlas, y ese alguien es esto.

    LAS CUATRO REGLAS, y la única que borra es la del verde:

        naranja   suma una vuelta. Es la que puede terminar en retiro.
        verde     RESETEA a cero. Volvió a rendir: la racha anterior ya no
                  describe a esta estrategia.
        amarillo  no suma y no borra. El semáforo dice de sí mismo que un
                  amarillo "puede ser mala suerte todavía": sumarlo retiraría
                  por ruido, y borrarlo dejaría que una caída real se limpie
                  sola cada vez que rebota un poco.
        callado   igual que el amarillo, y por otro motivo: no hay con qué
                  opinar. No opinar no es una opinión buena.

    SOLO EL VERDE BORRA, Y ES A PROPOSITO. Para limpiar la cuenta hay que
    demostrar que volvió a rendir, no simplemente dejar de estar mal.
    """
    previa = previa or {}
    vueltas = int(previa.get("vueltas_naranja") or 0)
    if v.estado == NARANJA:
        vueltas += 1
    elif v.estado == VERDE:
        vueltas = 0

    return {
        "color": v.estado,
        "vueltas_naranja": vueltas,
        "cerradas": v.cerradas,
        "motivo": v.motivo,
        "recomendacion": v.recomendacion,
        "conserva": v.conserva,
        "actualizado": cuando,
    }
