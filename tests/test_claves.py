"""Las claves del exchange: que se guarden cifradas y que no se filtren.

Dos preguntas distintas y las dos importan. Que el cifrado funcione es lo
obvio. Que el secreto no salga por ningún otro lado —una pantalla, un listado,
un mensaje de error— es lo que en la práctica falla, porque nadie lo mira.
"""

from __future__ import annotations

import json

import pytest

from botiquant.vivo import claves
from botiquant.vivo.claves import ClaveError, borrar, describir, guardar, leer, listar

CLAVE = "AbCdEf1234567890PUBLICA"
SECRETO = "SECRETO_QUE_NO_PUEDE_APARECER_EN_NINGUN_LADO"


@pytest.fixture
def carpeta(tmp_path):
    return tmp_path / "claves"


# ------------------------------------------------------------ ida y vuelta

def test_lo_que_se_guarda_se_puede_leer(carpeta):
    guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret=SECRETO)
    assert leer(carpeta, "bingx", "practica") == (CLAVE, SECRETO)


def test_practica_y_real_son_dos_claves_distintas(carpeta):
    """Es la separación que evita el peor accidente posible.

    Con una sola clave para los dos entornos, cambiar de práctica a real sería
    un interruptor en la pantalla — y un clic de más opera con plata de verdad.
    Así hay que cargar otra clave a propósito.
    """
    guardar(carpeta, "bingx", "practica", api_key="DEMO", secret="s1")
    guardar(carpeta, "bingx", "real", api_key="REAL", secret="s2")
    assert leer(carpeta, "bingx", "practica")[0] == "DEMO"
    assert leer(carpeta, "bingx", "real")[0] == "REAL"


def test_sin_clave_guardada_lo_dice_claro(carpeta):
    with pytest.raises(ClaveError, match="No hay claves"):
        leer(carpeta, "bingx", "practica")


# ------------------------------------------------- el archivo está cifrado

def test_el_secreto_no_esta_en_el_archivo(carpeta):
    """La prueba central del cifrado.

    Un archivo de configuración con un secreto adentro es exactamente lo que
    busca cualquier cosa que entre a la máquina.
    """
    guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret=SECRETO)
    crudo = (carpeta / "claves-bingx-practica.bin").read_bytes()
    assert SECRETO.encode() not in crudo
    assert CLAVE.encode() not in crudo


def test_tampoco_esta_en_ningun_archivo_de_la_carpeta(carpeta):
    """Más ancha que la anterior a propósito.

    La de arriba mira el archivo que esperamos. Ésta mira TODOS: si algún día
    alguien agrega un índice, un caché o un archivo de respaldo con el secreto
    adentro, lo agarra.
    """
    guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret=SECRETO)
    for f in carpeta.rglob("*"):
        if f.is_file():
            assert SECRETO.encode() not in f.read_bytes(), f"el secreto está en {f.name}"


# ------------------------------------------- lo que se puede mostrar y lo que no

def test_lo_que_se_muestra_nunca_trae_el_secreto(carpeta):
    """`describir` es lo único que va a la pantalla. Si filtra, filtra a la vista."""
    guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret=SECRETO)
    d = describir(carpeta, "bingx", "practica")
    texto = json.dumps(d)
    assert SECRETO not in texto
    assert CLAVE not in texto, "tampoco la clave pública entera"
    assert d["termina_en"] == CLAVE[-4:]


def test_el_listado_completo_tampoco(carpeta):
    guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret=SECRETO)
    guardar(carpeta, "bingx", "real", api_key=CLAVE, secret=SECRETO)
    texto = json.dumps(listar(carpeta))
    assert SECRETO not in texto and CLAVE not in texto


def test_los_ultimos_cuatro_alcanzan_para_reconocer_y_no_para_usar(carpeta):
    """Sirven para saber CUÁL clave está cargada cuando alguien tiene varias.

    El secreto no aparece ni siquiera enmascarado: un secreto enmascarado
    sigue siendo una pista sobre su longitud y su formato.
    """
    guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret=SECRETO)
    d = describir(carpeta, "bingx", "practica")
    assert len(d["termina_en"]) == 4
    assert "secret" not in json.dumps(d).lower()


def test_sin_configurar_lo_dice_sin_reventar(carpeta):
    d = describir(carpeta, "bingx", "real")
    assert d["configurada"] is False


# ------------------------------------------------------------------ borrar

def test_borrar_saca_la_clave_de_la_maquina(carpeta):
    guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret=SECRETO)
    assert borrar(carpeta, "bingx", "practica") is True
    assert not (carpeta / "claves-bingx-practica.bin").exists()
    with pytest.raises(ClaveError):
        leer(carpeta, "bingx", "practica")


def test_borrar_lo_que_no_esta_no_es_un_error(carpeta):
    assert borrar(carpeta, "bingx", "practica") is False


# ------------------------------------------------------------ las validaciones

def test_una_clave_vacia_no_se_guarda(carpeta):
    with pytest.raises(ClaveError, match="Faltan"):
        guardar(carpeta, "bingx", "practica", api_key="", secret=SECRETO)
    with pytest.raises(ClaveError, match="Faltan"):
        guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret="   ")


def test_se_le_sacan_los_espacios(carpeta):
    """Pegar desde el navegador arrastra espacios y saltos de línea.

    Una clave con un espacio al final falla la firma y el mensaje del exchange
    dice "clave incorrecta", que manda a buscar en el lugar equivocado.
    """
    guardar(carpeta, "bingx", "practica",
            api_key=f"  {CLAVE}\n", secret=f"\t{SECRETO}  ")
    assert leer(carpeta, "bingx", "practica") == (CLAVE, SECRETO)


@pytest.mark.parametrize("exchange,entorno", [
    ("bingx", "produccion"),          # el entorno se llama "real"
    ("../../etc", "practica"),        # el nombre va a una ruta
])
def test_un_nombre_desconocido_se_rechaza(carpeta, exchange, entorno):
    """El nombre se usa para construir una ruta, así que no puede ser libre."""
    with pytest.raises(ClaveError, match="desconocido"):
        guardar(carpeta, exchange, entorno, api_key=CLAVE, secret=SECRETO)


# ---------------------------------------------- el archivo de otra máquina

def test_un_archivo_ilegible_no_revienta_la_pantalla(carpeta, monkeypatch):
    """Pasa de verdad: alguien copia su carpeta a otra computadora.

    Con DPAPI la clave está atada a esa sesión de Windows, así que en la
    máquina nueva no se puede descifrar. Lo que NO puede pasar es que la
    pantalla de exchanges se caiga entera por eso.
    """
    guardar(carpeta, "bingx", "practica", api_key=CLAVE, secret=SECRETO)
    (carpeta / "claves-bingx-practica.bin").write_bytes(b"basura que no descifra")
    d = describir(carpeta, "bingx", "practica")
    assert d["configurada"] is True
    assert "ilegible" in d


def test_binance_en_REAL_no_se_puede_guardar(carpeta):
    """NO ES UNA PREFERENCIA: la aplicación no tiene forma de operar en real
    con Binance —el adaptador no acepta una base— así que una clave real sería
    una clave que no puede usar nadie.

    Guardarla igual dejaría en pantalla un "configurada" que promete algo que
    no existe, y ese es el tipo de mentira que después alguien toma por cierta.
    """
    with pytest.raises(ClaveError, match="solo en practica"):
        guardar(carpeta, "binance", "real", api_key="K" * 20, secret="S" * 20)


def test_binance_en_practica_si(carpeta):
    d = guardar(carpeta, "binance", "practica", api_key="K" * 20, secret="S" * 20)
    assert d["configurada"] is True
    assert leer(carpeta, "binance", "practica") == ("K" * 20, "S" * 20)


def test_el_listado_no_ofrece_binance_real(carpeta):
    """Si apareciera con "configurada: false" sonaría a que falta cargarla,
    cuando lo que pasa es que no existe."""
    filas = {(x["exchange"], x["entorno"]) for x in listar(carpeta)}
    assert ("binance", "practica") in filas
    assert ("binance", "real") not in filas
    assert ("bingx", "real") in filas
