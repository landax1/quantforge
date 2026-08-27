"""Cuánto del resultado puede ser haber buscado mucho.

Los números de referencia salen del paper de Bailey y López de Prado y de la
corrida real de BTCUSDT. Están fijados como expectativas porque son la razón de
que el módulo exista: si la fórmula se rompe, tienen que fallar acá y no en una
pantalla mostrando un umbral inventado.
"""

from __future__ import annotations

import pytest

from botiquant.azar import contexto, frase, max_esperado


# --------------------------------------------------- los números del paper

@pytest.mark.parametrize("intentos,esperado", [
    (100, 2.53),
    (1_000, 3.26),
    (1_500, 3.37),
    (10_000, 3.86),
])
def test_reproduce_los_numeros_publicados(intentos, esperado):
    """Con Sharpe verdadero cero y desvío uno, que es el caso del paper.

    Probando mil quinientas estrategias SIN NINGUNA VENTAJA, se espera que la
    mejor muestre 3,37 sólo por suerte.
    """
    assert max_esperado(0.0, 1.0, intentos) == pytest.approx(esperado, abs=0.01)


def test_crece_con_los_intentos():
    """Es lo que hace que un ciclo automático sea peligroso: cada vuelta suma
    intentos y el umbral del azar sube con ellos."""
    anterior = 0.0
    for n in (10, 100, 1_000, 10_000, 100_000):
        actual = max_esperado(0.0, 1.0, n)
        assert actual > anterior
        anterior = actual


# ------------------------------------------------ cuando no se puede calcular

def test_con_un_solo_intento_no_hay_maximo_del_que_hablar():
    assert max_esperado(0.0, 1.0, 1) is None
    assert max_esperado(0.0, 1.0, 0) is None


def test_sin_dispersion_la_formula_no_aplica():
    """Todas las candidatas dieron lo mismo: no hay un "máximo por azar" que
    calcular, y devolver un número sería inventarlo."""
    assert max_esperado(1.0, 0.0, 1_000) is None


def test_sin_sharpe_no_opina():
    c = contexto(None, media_sr=0.7, desvio_sr=0.25, intentos=1_500)
    assert c["medible"] is False
    assert c["motivo"]


# --------------------------------------------- el caso real que lo motivó

def test_el_caso_de_BTCUSDT_queda_pegado():
    """Medido: el mejor Sharpe fue 1,606 y el azar con 1.500 intentos daba
    1,564. Casi pegados.

    No dice que la estrategia no sirva —aguantó 223 operaciones fuera de
    muestra— pero sí que su Sharpe, solo, casi no distingue habilidad de
    suerte. Es exactamente lo que hay que poder mostrar.
    """
    c = contexto(1.606, media_sr=0.700, desvio_sr=0.256, intentos=1_500,
                 muestra=100)
    assert c["esperado_por_azar"] == pytest.approx(1.564, abs=0.01)
    assert c["supera_al_azar"] is True
    assert c["ventaja"] < 0.1, "le saca muy poco"


def test_avisa_cuando_la_dispersion_esta_subestimada():
    """La dispersión se mide sobre las que SOBREVIVIERON el filtro, que son
    parecidas entre sí. Eso subestima el umbral: el número verdadero es PEOR
    que el que mostramos, y conviene que se sepa.
    """
    c = contexto(1.6, media_sr=0.7, desvio_sr=0.256, intentos=1_500, muestra=100)
    assert c["dispersion_subestimada"] is True
    assert "más alto" in frase(c)


def test_sin_ese_hueco_no_avisa_de_mas():
    c = contexto(1.6, media_sr=0.7, desvio_sr=0.256, intentos=1_500, muestra=1_500)
    assert c["dispersion_subestimada"] is False


# ----------------------------------------------------- lo que se muestra

def test_la_frase_pone_los_dos_numeros_juntos():
    """"Sharpe 1,61" no dice nada solo. Al lado del umbral, dice todo."""
    f = frase(contexto(1.606, media_sr=0.7, desvio_sr=0.256, intentos=1_500))
    assert "1.606" in f
    assert "1,500" in f or "1500" in f
    assert "azar" in f


def test_dice_cuando_NO_le_saca_ventaja_al_azar():
    """Es el caso que hay que poder ver de un vistazo: el Sharpe de esta
    estrategia es MENOR que el que salía por probar mucho."""
    c = contexto(1.0, media_sr=0.7, desvio_sr=0.256, intentos=1_500)
    assert c["supera_al_azar"] is False
    assert "no le saca ventaja" in frase(c)


def test_no_bloquea_nada():
    """Es contexto al lado de un número, no una puerta más.

    Convertirlo en umbral sería inventar una vara sobre una estimación que ya
    sabemos incompleta. Si algún día se hace, hay que cambiar esta prueba a
    propósito.
    """
    c = contexto(0.1, media_sr=0.7, desvio_sr=0.256, intentos=100_000)
    assert c["supera_al_azar"] is False
    assert "pasa" not in c and "permitido" not in c and "bloquea" not in c


# ------------------------------------ el umbral no puede depender de la pagina

def test_el_umbral_es_el_mismo_pidiendo_pocas_filas_o_muchas(tmp_path):
    """Un bug real que casi reporto como hallazgo.

    La dispersion se calculaba sobre las filas de LA PAGINA en vez de la
    corrida entera. Medido: cuatro filas de la corrida de BTCUSDT daban un
    umbral de 2,00 y las cien daban 1,56 — o sea que "esta estrategia le gana
    al azar" cambiaba segun cuantas filas hubieras pedido.

    Lo agarre porque el numero no coincidia con uno que habia calculado a mano
    media hora antes.
    """
    from fastapi.testclient import TestClient

    from botiquant.api.app import create_app

    with TestClient(create_app(workdir=tmp_path / "ws")) as c:
        pocas = c.get("/api/banco?limit=3").json()
        muchas = c.get("/api/banco?limit=200").json()
        # el banco arranca vacio; lo que se fija es que cuando haya filas, el
        # umbral de una misma corrida sea identico en las dos respuestas
        umbrales = {}
        for lote in (pocas, muchas):
            for f in lote:
                a = f.get("azar") or {}
                if a.get("medible"):
                    cid = f.get("corrida_id")
                    anterior = umbrales.get(cid)
                    if anterior is not None:
                        assert anterior == a["esperado_por_azar"], (
                            f"el umbral de {cid} cambio con la paginacion")
                    umbrales[cid] = a["esperado_por_azar"]
