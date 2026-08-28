"""Exportar un conjunto de EA que van a convivir en una cuenta.

La diferencia con exportar cinco veces de a uno no es comodidad: el reparto
del capital, la concentración y el riesgo combinado sólo existen mirando el
conjunto, y exportando de a uno nadie los mira nunca.
"""

from __future__ import annotations

import pytest

from botiquant.reports.portafolio import (CONCENTRADO_DESDE, repartir, resumen)


def _e(nombre: str, instrumento: str = "SP500 M1") -> dict:
    return {"id": nombre, "name": nombre, "meta": {"dataset_name": instrumento}}


# ------------------------------------------------------------- el reparto

def test_reparte_la_cuenta_entre_todas():
    r = repartir([_e("a"), _e("b"), _e("c"), _e("d")], usar_pct=100.0)
    assert set(r.porciones.values()) == {25.0}
    assert r.total == 100.0


def test_el_colchon_se_respeta():
    """El informe del que salió esto opera al 89% y guarda el resto: una
    cuenta al 100% no aguanta que dos posiciones se muevan en contra."""
    r = repartir([_e("a"), _e("b")], usar_pct=80.0)
    assert r.total == 80.0
    assert set(r.porciones.values()) == {40.0}


def test_una_sola_se_lleva_todo_lo_que_se_pidio_usar():
    assert repartir([_e("sola")], usar_pct=100.0).porciones["sola"] == 100.0
    assert repartir([_e("sola")], usar_pct=50.0).porciones["sola"] == 50.0


def test_sin_estrategias_no_reparte_nada():
    r = repartir([])
    assert r.porciones == {}
    assert r.total == 0.0


def test_el_reparto_es_igualitario_y_esta_documentado_por_que():
    """No es pereza: los métodos que reparten según el riesgo necesitan
    estimar correlaciones a futuro desde el pasado, y con muestras cortas esa
    estimación es tan ruidosa que reparten PEOR que partir por igual.

    Si algún día hay años de datos propios, se revisa — y ahí conviene mirar
    la literatura en vez de inventar la fórmula.
    """
    r = repartir([_e(x) for x in "abcde"])
    assert len(set(r.porciones.values())) == 1, "todas la misma porción"


# ---------------------------------------------------------- los avisos

def test_avisa_cuando_hay_demasiadas_del_mismo_instrumento():
    """Medido: dos estrategias del mismo instrumento correlacionan +0,64 a
    +0,71, y entre instrumentos distintos van de -0,18 a +0,11."""
    r = repartir([_e("a", "BTCUSDT"), _e("b", "BTCUSDT"), _e("c", "BTCUSDT"),
                  _e("d", "SP500")])
    claves = [a.clave for a in r.avisos]
    assert "concentracion" in claves
    assert any("BTCUSDT" in a.texto for a in r.avisos)


def test_dos_del_mismo_instrumento_todavia_no_alarman():
    """Con dos se puede argumentar que son distintas —una de tendencia y una
    de reversión—; con tres es concentración."""
    r = repartir([_e("a", "BTCUSDT"), _e("b", "BTCUSDT"), _e("c", "SP500")])
    assert "concentracion" not in [a.clave for a in r.avisos]
    assert CONCENTRADO_DESDE == 3


def test_avisa_cuando_todas_operan_el_mismo_mercado():
    """El caso más grave y el más fácil de no ver: si ese mercado se da
    vuelta, se dan vuelta todas a la vez."""
    r = repartir([_e("a", "SP500"), _e("b", "SP500")])
    assert "un_solo_mercado" in [a.clave for a in r.avisos]


def test_una_sola_estrategia_no_dispara_el_aviso_de_un_solo_mercado():
    """Obviamente opera un solo mercado: decirlo sería ruido."""
    r = repartir([_e("sola", "SP500")])
    assert "un_solo_mercado" not in [a.clave for a in r.avisos]


def test_avisa_si_la_cuenta_queda_sin_colchon():
    r = repartir([_e("a"), _e("b")], usar_pct=100.0)
    assert "sin_colchon" in [a.clave for a in r.avisos]
    r2 = repartir([_e("a"), _e("b")], usar_pct=85.0)
    assert "sin_colchon" not in [a.clave for a in r2.avisos]


def test_avisa_cuando_las_porciones_quedan_diminutas():
    """Con porciones muy chicas el lote mínimo del bróker puede quedar por
    encima de lo que la estrategia quiere arriesgar, y va a operar más grande
    de lo pedido o no operar — las dos cosas en silencio."""
    r = repartir([_e(str(i)) for i in range(80)], usar_pct=100.0)
    assert "porciones_chicas" in [a.clave for a in r.avisos]


def test_no_apaga_nada():
    """Si el conjunto está concentrado lo dice y exporta igual: el usuario es
    el que arma su cartera."""
    r = repartir([_e("a", "BTC"), _e("b", "BTC"), _e("c", "BTC")])
    assert r.avisos
    assert r.total > 0, "avisar no puede impedir el reparto"


# ---------------------------------------------------------- el resumen

def test_el_resumen_dice_cuanto_queda_libre():
    s = resumen([_e("a"), _e("b")], repartir([_e("a"), _e("b")], usar_pct=80.0))
    assert s["cuantas"] == 2
    assert s["usado_pct"] == 80.0
    assert s["libre_pct"] == 20.0


def test_el_resumen_sale_del_MISMO_calculo_que_va_en_los_EA():
    """Si la pantalla calculara su propio reparto, el número que se ve y el
    que va adentro de cada archivo podrían divergir sin que nadie lo note."""
    ests = [_e("a"), _e("b"), _e("c")]
    r = repartir(ests, usar_pct=90.0)
    s = resumen(ests, r)
    assert s["porciones"] is r.porciones


# ------------------------------------------- el conjunto llega al disco

def _cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from botiquant.api.app import create_app
    monkeypatch.setenv("BQ_EXPORTS", str(tmp_path / "salida"))
    return TestClient(create_app(workdir=tmp_path / "ws"))


def _guardar(c, nombre, instrumento="SP500 M1"):
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    c.post("/api/strategies", json={
        "name": nombre,
        "spec": {"name": nombre, "direction": "long",
                 "entry_long": [{"left": ema(5), "op": "cross_above",
                                 "right": ema(20)}],
                 "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                          "stop_type": "atr", "stop_value": 2.0,
                          "target_type": "atr", "target_value": 4.0}},
        "meta": {"dataset_name": instrumento, "timeframe": "1h"}})
    return [x for x in c.get("/api/strategies").json() if x["name"] == nombre][0]["id"]


def test_cada_archivo_sale_con_SU_porcion_adentro(tmp_path, monkeypatch):
    """Lo que hace que sea un portafolio y no cinco archivos sueltos.

    Con cinco exportados por separado, cada uno se cree dueño del 100% de la
    cuenta y entre todos arriesgan cinco veces lo pedido — y el aviso de
    riesgo de cada uno dice que está bien, porque contra su propio número lo
    está.
    """
    from pathlib import Path

    with _cliente(tmp_path, monkeypatch) as c:
        ids = [_guardar(c, f"S{i}") for i in range(4)]
        r = c.post("/api/export/portafolio", json={"ids": ids, "usar_pct": 80})
        assert r.status_code == 200, r.text
        d = r.json()

        assert len(d["archivos"]) == 4
        assert d["usado_pct"] == 80.0
        assert d["libre_pct"] == 20.0
        for a in d["archivos"]:
            assert a["porcion_pct"] == 20.0
            texto = (Path(d["carpeta"]) / a["archivo"]).read_text(encoding="utf-8")
            assert "InpPorcionPct  = 20;" in texto


def test_cada_uno_conserva_su_Magic_Number_propio(tmp_path, monkeypatch):
    """Sin eso, los cinco creen que las posiciones de los otros son suyas."""
    from pathlib import Path

    from botiquant.reports.mql5 import magic_de

    with _cliente(tmp_path, monkeypatch) as c:
        ids = [_guardar(c, f"S{i}") for i in range(3)]
        d = c.post("/api/export/portafolio", json={"ids": ids}).json()
        magicos = set()
        for a in d["archivos"]:
            texto = (Path(d["carpeta"]) / a["archivo"]).read_text(encoding="utf-8")
            linea = [l for l in texto.splitlines() if "InpMagic" in l][0]
            magicos.add(linea)
        assert len(magicos) == 3, "dos EA con el mismo Magic Number"


def test_los_avisos_viajan_con_el_conjunto(tmp_path, monkeypatch):
    with _cliente(tmp_path, monkeypatch) as c:
        ids = [_guardar(c, f"B{i}", "BTCUSDT M1") for i in range(3)]
        d = c.post("/api/export/portafolio", json={"ids": ids}).json()
        claves = [a["clave"] for a in d["avisos"]]
        assert "concentracion" in claves
        assert "un_solo_mercado" in claves


def test_sin_estrategias_no_exporta(tmp_path, monkeypatch):
    with _cliente(tmp_path, monkeypatch) as c:
        assert c.post("/api/export/portafolio", json={"ids": []}).status_code == 400


def test_hay_un_tope_de_cuantas_entran(tmp_path, monkeypatch):
    """Con más, las porciones quedan tan chicas que el lote mínimo del bróker
    manda sobre lo que la estrategia quiere arriesgar."""
    with _cliente(tmp_path, monkeypatch) as c:
        r = c.post("/api/export/portafolio", json={"ids": [str(i) for i in range(25)]})
        assert r.status_code == 400
        assert "Veinte" in r.json()["detail"]


def _guardar_nueva(c, nombre, instrumento="SP500 M1") -> str:
    """El id de la que se ACABA de guardar.

    `_guardar` devuelve la primera que coincide por nombre, y con dos que se
    llaman igual eso devuelve dos veces la misma: la prueba exportaba un solo
    id repetido y no dos estrategias. Se lo saca por diferencia.
    """
    antes = {x["id"] for x in c.get("/api/strategies").json()}
    _guardar(c, nombre, instrumento)
    despues = {x["id"] for x in c.get("/api/strategies").json()}
    nuevos = despues - antes
    assert len(nuevos) == 1, f"se esperaba una guardada nueva, hubo {len(nuevos)}"
    return nuevos.pop()

def test_dos_estrategias_con_el_MISMO_nombre_salen_como_dos(tmp_path, monkeypatch):
    """VISTO USANDO LA APLICACIÓN, no deducido.

    Guardar dos veces la misma estrategia desde el banco deja dos guardadas con
    el mismo nombre. Exportando el conjunto, el aviso decía «3 robots
    guardados» y en el disco había DOS: el segundo archivo pisó al primero.

    Y el reparto ya había calculado 30% para cada uno de tres, así que la
    cuenta quedaba operando al 60% en vez del 90%, con un robot que el usuario
    cree tener y no tiene.
    """
    from pathlib import Path

    with _cliente(tmp_path, monkeypatch) as c:
        ids = [_guardar_nueva(c, "S-005"), _guardar_nueva(c, "S-005"),
               _guardar_nueva(c, "S-007")]
        d = c.post("/api/export/portafolio",
                   json={"ids": ids, "usar_pct": 90}).json()

        archivos = [a["archivo"] for a in d["archivos"]]
        assert len(set(archivos)) == 3, f"se pisaron: {archivos}"
        for a in archivos:
            assert (Path(d["carpeta"]) / a).exists(), f"{a} no llegó al disco"


def test_dos_con_el_mismo_nombre_NO_comparten_Magic_Number(tmp_path, monkeypatch):
    """Lo que hace daño de verdad si los archivos no se pisan.

    El Magic sale del nombre. Dos EA con el mismo número creen cada uno que las
    posiciones del otro son suyas: uno cierra lo que el otro abrió, y ninguno
    de los dos da error.
    """
    from pathlib import Path

    with _cliente(tmp_path, monkeypatch) as c:
        ids = [_guardar_nueva(c, "S-005"), _guardar_nueva(c, "S-005")]
        d = c.post("/api/export/portafolio", json={"ids": ids}).json()
        magicos = set()
        for a in d["archivos"]:
            texto = (Path(d["carpeta"]) / a["archivo"]).read_text(encoding="utf-8")
            magicos.add([l for l in texto.splitlines() if "InpMagic" in l][0])
        assert len(magicos) == 2, "dos EA con el mismo Magic Number"


def test_el_nombre_propio_no_depende_del_ORDEN_en_que_se_tildan(tmp_path,
                                                                monkeypatch):
    """Si el sufijo fuera un contador, reexportar el mismo conjunto en otro
    orden daría otro Magic — y el EA nuevo no reconocería la posición que dejó
    abierta el anterior."""
    with _cliente(tmp_path, monkeypatch) as c:
        a, b = _guardar_nueva(c, "S-005"), _guardar_nueva(c, "S-005")
        uno = c.post("/api/export/portafolio", json={"ids": [a, b]}).json()
        dos = c.post("/api/export/portafolio", json={"ids": [b, a]}).json()
        por_nombre = lambda d: {x["nombre"] for x in d["archivos"]}
        assert por_nombre(uno) == por_nombre(dos)


def test_el_EA_dice_contra_QUE_mide_el_riesgo(tmp_path, monkeypatch):
    """VISTO EN EL PROBADOR DE METATRADER.

    Un EA con el 30% de la cuenta imprimió «pierde 30.64 = 0.98% del balance»
    sobre un balance de 10.410, donde 30,64 es el 0,3%. El cálculo estaba bien
    —se dimensiona contra SU PARTE, que es lo correcto— y la frase producía
    justo la duda que ese bloque venía a evitar.
    """
    from pathlib import Path

    with _cliente(tmp_path, monkeypatch) as c:
        ids = [_guardar_nueva(c, f"S{i}") for i in range(3)]
        d = c.post("/api/export/portafolio", json={"ids": ids}).json()
        texto = (Path(d["carpeta"]) / d["archivos"][0]["archivo"]).read_text(
            encoding="utf-8")
        # El literal va partido en dos líneas en el .mq5, así que se busca el
        # trozo que no se corta. Buscando "de su parte" entero, la prueba
        # fallaba con el arreglo YA puesto.
        assert "parte (%.0f%% de la cuenta" in texto, (
            "no dice contra qué mide el porcentaje ni cuánto es su parte")


def test_un_EA_solo_sigue_diciendo_del_balance(tmp_path, monkeypatch):
    """Con el 100% de la cuenta, «de su parte» sería una vuelta de más: su
    parte ES el balance."""
    from pathlib import Path

    with _cliente(tmp_path, monkeypatch) as c:
        sid = _guardar_nueva(c, "Sola")
        d = c.post("/api/export/portafolio",
                   json={"ids": [sid], "usar_pct": 100}).json()
        texto = (Path(d["carpeta"]) / d["archivos"][0]["archivo"]).read_text(
            encoding="utf-8")
        assert "InpPorcionPct  = 100;" in texto
        # Con el 100% su parte ES el balance, así que la rama que se usa es la
        # que dice "del balance" — y ahí la frase es cierta.
        assert "InpPorcionPct >= 100.0" in texto
