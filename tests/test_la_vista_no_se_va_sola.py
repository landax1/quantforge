"""Que la vista no se vaya sola mientras el minado repinta.

EL SÍNTOMA, reportado por el usuario: "cuando estás en el minador y entra la
primera estrategia, o estás mirando las que van saliendo en el databank, a
veces la aplicación te scrollea para arriba automáticamente".

Medido durante una corrida real, mirando la tabla desde 519px: un salto de
237px hacia arriba justo al entrar una estrategia nueva. Intermitente —una de
cada tres corridas al principio— que es lo que lo hacía difícil de agarrar.

LA CAUSA no es repintar de más: la pantalla ya compara el HTML y sólo reescribe
lo que cambió. Es el anclaje de scroll del navegador, que elige un nodo visible
como referencia para que la página no se corra cuando algo crece más arriba.
Cuando ese nodo es justo uno de los que se reescriben en cada vuelta, el ancla
se pierde y la vista cae donde puede.

POR QUÉ ESTA PRUEBA MIRA EL CSS Y NO EL JAVASCRIPT. Se probaron y descartaron
dos arreglos en JavaScript, los dos por medición: guardar y restituir
`scrollTop` alrededor del repintado no sirve, ni dentro de `renderMining` ni
envolviendo la vuelta entera del sondeo, porque el navegador aplica su ajuste
DESPUÉS, en el layout siguiente. La restitución llega temprano y el salto
ocurre igual. La única corrección que funcionó fue declarativa.

Medido con la regla puesta: cero saltos en cinco corridas seguidas.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CSS = (RAIZ / "ui" / "styles.css").read_text(encoding="utf-8")

#: Los que se reescriben en cada vuelta del sondeo. Salen de observar las
#: mutaciones del DOM en el instante del salto, no de leer el código.
VOLATILES = ("#m-goal", "#m-goal-lado", "#m-champ", "#m-histbox",
             "#m-hist", "#m-prog", "#m-runbar")


def _reglas_sin_ancla() -> str:
    """Todo el CSS que apaga el anclaje, junto."""
    return " ".join(m.group(0) for m in
                    re.finditer(r"[^{}]+\{[^}]*overflow-anchor:\s*none[^}]*\}", CSS))


def test_los_bloques_que_se_reescriben_no_pueden_ser_ancla():
    """Si el navegador ancla en uno de éstos, al reescribirlo pierde el ancla.

    Y perder el ancla es exactamente el salto que se reportó.
    """
    reglas = _reglas_sin_ancla()
    assert reglas, (
        "no quedó ninguna regla `overflow-anchor: none`. Sin eso el navegador "
        "vuelve a anclar el scroll en un bloque que se reescribe cada vuelta, "
        "y la vista salta para arriba mientras uno mira la tabla")
    faltan = [v for v in VOLATILES if v not in reglas]
    assert not faltan, (
        f"estos bloques se reescriben en cada vuelta del minado y volvieron a "
        f"poder ser elegidos como ancla: {faltan}")


def test_la_tabla_si_puede_ser_ancla():
    """Y esto es la otra mitad de la decisión.

    Apagar el anclaje en todo el contenedor también evitaba el salto, pero de
    paso perdía lo que el anclaje hace bien: sostener la vista cuando crece
    algo por encima. La tabla es justo donde está mirando la persona, así que
    tiene que seguir siendo elegible.
    """
    reglas = _reglas_sin_ancla()
    assert "#m-bank" not in reglas, (
        "se excluyó también la tabla de resultados. Es donde la persona está "
        "leyendo: si no puede ser ancla, no queda nada estable a lo que "
        "sostenerse cuando el contenido de arriba crece")
    assert not re.search(r"(^|[^-\w])main\s*\{[^}]*overflow-anchor:\s*none", CSS, re.M), (
        "se apagó el anclaje en todo el contenedor con scroll; eso evita el "
        "salto pero también desactiva la protección para el caso normal")
