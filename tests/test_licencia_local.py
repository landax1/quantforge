"""La licencia del lado del escritorio.

Dos cosas se prueban acá, y la segunda es la que más importa a largo plazo.

La primera es el comportamiento: qué pasa sin licencia, con una buena, con una
vencida y con un archivo que alguien editó a mano. Y sobre todo que importar
una licencia rota **no borra la que estaba puesta** — que es el error que deja
a un usuario sin nada por haber pegado mal.

La segunda es que ``CLAVE_PUBLICA`` corresponde de verdad a la privada del
servidor. El día que se rote el par y alguien se olvide de actualizar la
constante, las licencias emitidas dejan de verificar en todas las máquinas del
mundo y no hay ninguna señal: el servidor firma feliz y la aplicación rechaza.
Esa prueba convierte un incidente en un test rojo.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from botiquant.licencia.clave import CLAVE_PUBLICA
from botiquant.licencia.firma import LicenciaError, firmar, verificar

RAIZ = Path(__file__).resolve().parent.parent

#: Un par cualquiera para las pruebas de comportamiento. No se usa el de
#: producción: los tests no pueden depender de que exista un ``.env``.
PRIV = "1eSuTVOm5FdJU7YkxV0lPl3ndAVeYWfe1jUwQmVYaXM"


@pytest.fixture
def local(tmp_path, monkeypatch):
    """El módulo apuntando a una carpeta de trabajo desechable."""
    monkeypatch.setenv("BQ_WORKSPACE", str(tmp_path))
    from botiquant.licencia import local as modulo

    # la clave pública tiene que ser la del par de prueba, no la de producción
    from botiquant.licencia.firma import crear_par_de_claves

    priv, pub = crear_par_de_claves()
    monkeypatch.setattr(modulo, "CLAVE_PUBLICA", pub)
    modulo._PRIV_DE_PRUEBA = priv          # para que los tests puedan firmar
    return modulo


def _token(local, **campos):
    datos = {"user_id": "7", "email": "jm@botiquant.com", "plan": "free",
             "expira": 0, "alta": 1_750_000_000, "fundador": False}
    datos.update(campos)
    return firmar(datos, local._PRIV_DE_PRUEBA)


# ───────────────────────────────────────────────────────── comportamiento

def test_sin_licencia_la_app_no_se_limita(local):
    """Lo más importante de todo: sin licencia se puede hacer todo."""
    e = local.leer()
    assert e.situacion == "sin_licencia"
    assert e.plan == "free"
    assert e.to_dict()["limita"] is False


def test_una_licencia_buena_dice_quien_sos(local):
    e = local.guardar(_token(local, fundador=True))
    assert e.situacion == "valida"
    assert e.email == "jm@botiquant.com"
    assert e.alta == 1_750_000_000
    assert e.fundador is True
    # y sobrevive a cerrar el programa
    assert local.leer().email == "jm@botiquant.com"


def test_la_gratis_no_vence(local):
    e = local.guardar(_token(local, plan="free", expira=0))
    assert e.expira == 0
    assert e.dias_restantes is None, "sin fecha no hay días restantes que mostrar"


def test_una_vencida_se_distingue_de_una_falsa(local):
    """Para el usuario no son lo mismo: una se arregla entrando a la cuenta."""
    e = local.leer(_token(local, plan="pro", expira=1_000_000_000))
    assert e.situacion == "vencida"
    assert e.situacion != "invalida"


def test_texto_cualquiera_no_pasa(local):
    assert local.leer("esto no es una licencia").situacion == "invalida"
    assert local.leer("a.b").situacion == "invalida"
    assert local.leer("").situacion == "sin_licencia"


def test_una_firmada_con_otra_clave_no_pasa(local):
    """Es el punto entero del asunto: sin la privada no se fabrican licencias."""
    ajena = firmar({"user_id": "1", "email": "x@y.z", "plan": "pro",
                    "expira": 0}, PRIV)
    assert local.leer(ajena).situacion == "invalida"


def test_importar_una_rota_no_borra_la_que_estaba(local):
    """El error que deja al usuario sin nada por haber pegado mal."""
    local.guardar(_token(local))
    assert local.leer().situacion == "valida"

    e = local.guardar("basura pegada de cualquier lado")
    assert e.situacion == "invalida", "devuelve el problema"
    assert local.leer().email == "jm@botiquant.com", "y la buena sigue puesta"


def test_un_archivo_enorme_no_se_lee_entero(local):
    local.ruta().parent.mkdir(parents=True, exist_ok=True)
    local.ruta().write_text("x" * (local.TOPE_BYTES + 1), encoding="utf-8")
    assert local.leer().situacion == "invalida"


def test_sacarla_deja_la_maquina_como_estaba(local):
    local.guardar(_token(local))
    assert local.borrar().situacion == "sin_licencia"
    assert not local.ruta().exists()
    # y se puede sacar dos veces sin romper nada
    assert local.borrar().situacion == "sin_licencia"


def test_una_licencia_vieja_sin_los_campos_nuevos_sigue_sirviendo(local):
    """Compatibilidad: `alta` y `fundador` se agregaron después."""
    vieja = firmar({"user_id": "7", "email": "jm@botiquant.com",
                    "plan": "free", "expira": 0}, local._PRIV_DE_PRUEBA)
    e = local.leer(vieja)
    assert e.situacion == "valida"
    assert e.alta == 0 and e.fundador is False


# ─────────────────────────────── la constante contra la clave de verdad

@pytest.mark.skipif(not (RAIZ / ".env").is_file(),
                    reason="sin .env no hay clave privada contra la cual comparar")
def test_la_clave_publica_del_codigo_es_la_del_servidor():
    """Si esto falla, NO se publica.

    Quiere decir que el par se rotó y `botiquant/licencia/clave.py` quedó con
    la clave vieja. Las licencias que emita el servidor no van a verificar en
    ninguna máquina, y nada más lo avisa: el servidor firma sin problema y la
    aplicación rechaza sin poder explicar por qué.
    """
    env = (RAIZ / ".env").read_text(encoding="utf-8")
    m = re.search(r"^BQ_LICENCIA_PRIVADA=(.*)$", env, re.M)
    if not m or not m.group(1).strip():
        pytest.skip("el .env no tiene clave privada configurada")

    token = firmar({"user_id": "0", "email": "prueba@local", "plan": "free",
                    "expira": 0}, m.group(1).strip())
    try:
        lic = verificar(token, CLAVE_PUBLICA)
    except LicenciaError as exc:
        pytest.fail(
            "CLAVE_PUBLICA no corresponde a BQ_LICENCIA_PRIVADA. Se rotó el par "
            "y quedó sin actualizar botiquant/licencia/clave.py: las licencias "
            f"emitidas no van a verificar en ninguna máquina. ({exc})")
    assert lic.email == "prueba@local"
