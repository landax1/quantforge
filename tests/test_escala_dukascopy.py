"""La escala de precios de cada instrumento, que es lo que traba agregar más.

Los precios de Dukascopy son enteros escalados: 107896 es 1,07896 en EURUSD y
107.896 en un índice. No se puede adivinar del dato.

Con cuatro instrumentos alcanzaba una tabla a mano. Para agregar más —que es
lo único que hace que un portafolio diversifique de verdad— no: el catálogo de
Dukascopy tiene 1.499 instrumentos y una tabla propia se desactualiza sola.

MEDIDO, y es el motivo de que este archivo exista: de siete instrumentos
probados fuera de la tabla, SEIS necesitaban 1e3 y sólo GBPUSD 1e5. Adivinar
acierta una de cada siete veces, y las seis restantes bajan con los precios
divididos por cien sin que nada falle.
"""

from __future__ import annotations

import pytest

from botiquant.data import dukascopy as dk


@pytest.fixture(autouse=True)
def _sin_cache():
    """Cada prueba arranca sin nada consultado."""
    dk._ESCALAS_VISTAS.clear()
    yield
    dk._ESCALAS_VISTAS.clear()


class _Resp:
    def __init__(self, code, cuerpo=None):
        self.status_code = code
        self._c = cuerpo or {}

    def json(self):
        return self._c


def _cliente_falso(monkeypatch, respuestas):
    """Reemplaza la red. `respuestas` es una lista que se va consumiendo."""
    pedidos = []

    class _C:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, url):
            pedidos.append(url)
            return respuestas[min(len(pedidos) - 1, len(respuestas) - 1)]

    monkeypatch.setattr(dk.httpx, "Client", _C)
    monkeypatch.setattr(dk.time, "sleep", lambda *_: None)
    return pedidos


# --------------------------------------------- los cuatro verificados a mano

@pytest.mark.parametrize("simbolo,escala", [
    ("eurusd", 1e5),
    ("usa500idxusd", 1e3),
    ("xauusd", 1e3),
    ("btcusd", 1e1),
])
def test_los_de_la_tabla_no_consultan_nada(monkeypatch, simbolo, escala):
    """Están verificados contra precios reales y la aplicación los viene
    bajando desde siempre. Una consulta que falla no puede cambiarlos.
    """
    pedidos = _cliente_falso(monkeypatch, [_Resp(500)])
    assert dk.escala_de(simbolo) == escala
    assert pedidos == [], "no tendría que haber salido a la red"


# ------------------------------------------------------- lo que se consulta

def test_un_instrumento_nuevo_se_consulta(monkeypatch):
    """`espidxeur` no esta en la tabla A PROPOSITO: si se usara uno que si
    esta, la prueba pasaria por la tabla y no por la consulta, y seguiria
    verde con la consulta rota."""
    assert "espidxeur" not in dk.ESCALA
    _cliente_falso(monkeypatch, [_Resp(200, {"multiplier": 0.001})])
    assert dk.escala_de("espidxeur", "ESP.IDX-EUR") == 1000.0


def test_se_consulta_UNA_vez_por_instrumento(monkeypatch):
    """Bajar quince años son miles de días. Preguntar la escala en cada uno
    multiplicaría por mil los pedidos a una API que ya limita por IP."""
    assert "espidxeur" not in dk.ESCALA
    pedidos = _cliente_falso(monkeypatch, [_Resp(200, {"multiplier": 0.001})])
    for _ in range(5):
        dk.escala_de("espidxeur", "ESP.IDX-EUR")
    assert len(pedidos) == 1


def test_reintenta_UNA_vez_cuando_lo_limitan(monkeypatch):
    """Una y no cinco. Ver el bloque de REINTENTOS_ESCALA: insistir no
    atraviesa el limite de Dukascopy, lo causa."""
    _cliente_falso(monkeypatch, [_Resp(429),
                                 _Resp(200, {"multiplier": 0.001})])
    assert dk.escala_de("usa30idxusd", "USA30.IDX-USD") == 1000.0


# ------------------------------------------- lo que NO hace: adivinar

def test_si_no_puede_saberla_se_NIEGA_a_bajar(monkeypatch):
    """La decisión importante de todo el módulo.

    Un default es cómodo y silencioso: el Dow a 387 en vez de 38.700, el
    backtest corre igual, las métricas salen, y todo lo que se decida encima
    está mal. Sin datos se puede vivir; con datos equivocados que parecen
    buenos, no.
    """
    _cliente_falso(monkeypatch, [_Resp(429)])
    with pytest.raises(dk.DukascopyError, match="escala"):
        dk.escala_de("usa30idxusd", "USA30.IDX-USD")


def test_no_queda_ningun_valor_por_defecto_en_el_modulo():
    """Si alguien lo vuelve a agregar «para que no falle», esto se pone rojo.

    Es exactamente el cambio que se hace con buena intención y produce
    históricos equivocados que nadie detecta.
    """
    assert not hasattr(dk, "ESCALA_POR_DEFECTO")


def test_un_multiplicador_absurdo_no_se_acepta(monkeypatch):
    """Cero o negativo daría una división por cero o precios invertidos."""
    _cliente_falso(monkeypatch, [_Resp(200, {"multiplier": 0})])
    with pytest.raises(dk.DukascopyError):
        dk.escala_de("raro", "RARO-USD")


def test_sin_codigo_de_api_tampoco_adivina(monkeypatch):
    """Las guardadas viejas y los importados a mano no tienen código."""
    _cliente_falso(monkeypatch, [_Resp(200, {"multiplier": 0.001})])
    with pytest.raises(dk.DukascopyError):
        dk.escala_de("desconocido")


# ------------------------------------------------ la API dice la verdad

@pytest.mark.parametrize("simbolo,codigo", [
    ("eurusd", "EUR-USD"),
    ("usa500idxusd", "USA500.IDX-USD"),
    ("xauusd", "XAU-USD"),
    ("btcusd", "BTC-USD"),
])
def test_la_API_coincide_con_lo_verificado_a_mano(monkeypatch, simbolo, codigo):
    """Es como se comprobó que se puede confiar en ella.

    Los cuatro de la tabla se midieron contra precios reales hace meses. Si la
    API dijera otra cosa para alguno, no habría motivo para creerle en los
    otros 1.495 — y esta prueba fija esa correspondencia con los valores que
    devolvió el 27 de agosto de 2026.
    """
    de_la_api = {"EUR-USD": 1e-5, "USA500.IDX-USD": 0.001,
                 "XAU-USD": 0.001, "BTC-USD": 0.1}[codigo]
    _cliente_falso(monkeypatch, [_Resp(200, {"multiplier": de_la_api})])
    dk._ESCALAS_VISTAS.clear()
    # se pregunta con otro nombre para saltear la tabla y forzar la consulta
    consultada = dk.escala_de(f"{simbolo}_prueba", codigo)
    assert consultada == pytest.approx(dk.ESCALA[simbolo])


# --------------------------------------- cuanto insiste, y por que asi

def test_insiste_POCO_con_la_escala_y_espera_mucho(monkeypatch):
    """Esta prueba existe porque la primera version hacia lo contrario.

    Se habia puesto cinco reintentos con espera corta, para "atravesar" el
    limite de Dukascopy. MEDIDO despues:

      * diez codigos nunca pedidos, un pedido cada uno: OCHO dieron 200 a la
        primera.
      * un codigo al que se le habian hecho unos quince pedidos: TRECE
        rechazos seguidos con un pedido cada veinte segundos, mientras los
        frescos seguian contestando en el mismo minuto.

    Insistir no atraviesa el limite: lo causa. Si esto vuelve a subir, sube
    tambien la probabilidad de dejar un instrumento bloqueado.
    """
    assert dk.REINTENTOS_ESCALA <= 2
    assert dk.ESPERA_ESCALA >= 30.0


def test_no_machaca_a_dukascopy_cuando_no_hay_caso(monkeypatch):
    """Con 429 en las dos, para. Cada pedido de mas empeora el bloqueo."""
    pedidos = _cliente_falso(monkeypatch, [_Resp(429)])
    with pytest.raises(dk.DukascopyError):
        dk.escala_de("lightcmdusd", "LIGHT.CMD-USD")
    assert len(pedidos) == 2


def test_el_mensaje_no_invita_a_insistir(monkeypatch):
    """Decia «probá de nuevo en un minuto», que es exactamente lo que deja el
    instrumento peor. El texto que ve el usuario tambien es parte del arreglo.
    """
    _cliente_falso(monkeypatch, [_Resp(429)])
    with pytest.raises(dk.DukascopyError) as e:
        dk.escala_de("lightcmdusd", "LIGHT.CMD-USD")
    assert "UNA vez" in str(e.value)


# ------------------------- lo que verificamos no se consulta en el usuario

@pytest.mark.parametrize("simbolo,escala,cierre_real", [
    ("usdjpy", 1e3, 155.116),
    ("deuidxeur", 1e3, 18_482.477),
    ("jpnidxjpy", 1e3, 38_551.417),
    ("usatechidxusd", 1e3, 18_689.398),
    ("gbridxgbp", 1e3, 8_258.592),
    ("xagusd", 1e3, 29.562),
    ("gascmdusd", 1e4, 2.6242),
    ("audusd", 1e5, 0.6645),
])
def test_los_verificados_no_dependen_de_la_red(monkeypatch, simbolo, escala,
                                               cierre_real):
    """Cada uno se bajo el 3 de junio de 2024 y se comparo con el precio real.

    Consultar es lo correcto para un instrumento que nadie verifico: es eso o
    adivinar. Para uno que SI verificamos, dejar que dependa de la API en la
    maquina del usuario cambia una certeza por un pedido de red que falla.

    MEDIDO: probando doce instrumentos seguidos, Dukascopy contesto 429 a la
    mitad, y cuatro siguieron en 429 con un pedido cada veinte segundos
    mientras otros contestaban 200 en el mismo minuto. La causa no la se; el
    usuario se topa con el 429 igual.

    `cierre_real` no se usa en la assertion a proposito: esta para que el
    numero contra el que se verifico quede en el archivo y se pueda repetir la
    comprobacion sin buscarla en ningun lado.
    """
    pedidos = _cliente_falso(monkeypatch, [_Resp(429)])
    assert dk.escala_de(simbolo) == escala
    assert pedidos == [], f"{simbolo} salio a la red teniendolo verificado"
    assert cierre_real > 0


def test_las_dos_escalas_raras_siguen_siendo_raras():
    """Son las que prueban que la tabla hace falta.

    Seis de los ocho nuevos usan 1e3. Si alguien mira eso y concluye "los
    indices y las materias primas son 1e3", el gas natural baja diez veces mas
    caro y el AUDUSD mil veces. Ninguno de los dos falla.
    """
    assert dk.ESCALA["gascmdusd"] == 1e4
    assert dk.ESCALA["audusd"] == 1e5
    assert dk.ESCALA["btcusd"] == 1e1
