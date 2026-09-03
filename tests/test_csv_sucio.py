"""Un CSV de la vida real: lo que se lee mal y lo que se tira sin decirlo.

Un usuario de prueba subió sus propios archivos el 3 de septiembre de 2026 y
encontró las dos formas en que la aplicación aceptaba datos rotos con el tilde
verde puesto:

* velas horarias del 2 al 26 de enero fechadas ``02/01/2023`` quedaron
  guardadas como once meses de historia desordenada, etiquetada "1h";
* un archivo con un ``low`` negativo, una marca de tiempo repetida y filas
  cortadas entró sin una palabra: ``dropna`` y deduplicado en silencio.

Las dos son peores que un error. Un archivo rechazado se arregla; un archivo
aceptado y roto se mina, se prueba, se aprueba y se pone a operar.
"""

from __future__ import annotations

import datetime as dt

import pytest

from botiquant.data.loader import parse_ohlcv_csv


def _velas(n: int, inicio: dt.datetime, formato: str, paso_h: int = 1) -> list[str]:
    filas = ["date,time,open,high,low,close,volume"]
    t = inicio
    for i in range(n):
        px = 1800 + i * 0.1
        filas.append(f"{t.strftime(formato)},{t.strftime('%H:%M')},"
                     f"{px:.2f},{px + 1:.2f},{px - 1:.2f},{px + .5:.2f},100")
        t += dt.timedelta(hours=paso_h)
    return filas


def test_las_fechas_dia_mes_no_se_leen_como_mes_dia():
    """25 días de velas horarias tienen que seguir siendo 25 días."""
    csv = "\n".join(_velas(600, dt.datetime(2023, 1, 2), "%d/%m/%Y"))
    df = parse_ohlcv_csv(csv)
    abarca = (df.index[-1] - df.index[0]).days
    assert abarca <= 26, (
        f"la serie abarca {abarca} días: se leyó el mes como día y la búsqueda "
        "mina sobre una historia que no existió nunca")
    assert df.index.is_monotonic_increasing, "las velas quedaron desordenadas"


def test_un_archivo_iso_sigue_leyendose_igual():
    """El arreglo de arriba no puede romper el formato de siempre."""
    csv = "\n".join(_velas(600, dt.datetime(2023, 3, 1), "%Y-%m-%d"))
    df = parse_ohlcv_csv(csv)
    assert str(df.index[0].date()) == "2023-03-01"
    assert df.index.is_monotonic_increasing


def _roto(n: int = 900) -> str:
    filas = ["timestamp,open,high,low,close,volume"]
    t = dt.datetime(2023, 1, 1)
    for i in range(n):
        px = 1800 + i * 0.1
        low = -1799.6 if i == 100 else px - 1        # un precio negativo
        high = px - 5 if i == 200 else px + 1        # una vela que cierra afuera
        filas.append(f"{t:%Y-%m-%d %H:%M:%S},{px:.2f},{high:.2f},{low:.2f},"
                     f"{px + .5:.2f},100")
        if i != 300:                                  # una marca repetida
            t += dt.timedelta(hours=1)
    return "\n".join(filas)


def test_lo_que_se_tira_se_cuenta_y_se_dice():
    df = parse_ohlcv_csv(_roto())
    d = df.attrs["descartadas"]
    assert d.get("precio_invalido") == 1, d
    assert d.get("vela_incoherente") == 1, d
    assert d.get("repetida") == 1, d
    assert df.attrs["filas_leidas"] == 900


def test_ninguna_vela_rota_sobrevive_al_alta():
    df = parse_ohlcv_csv(_roto())
    assert (df[["open", "high", "low", "close"]] > 0).all().all(), \
        "quedó un precio cero o negativo: le mueve el ATR a toda la serie"
    assert (df["high"] >= df["low"]).all()
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    assert not df.index.duplicated().any()


def test_un_archivo_sano_no_reporta_nada():
    """El aviso tiene que significar algo: si aparece siempre, no se lee."""
    csv = "\n".join(_velas(500, dt.datetime(2023, 1, 1), "%Y-%m-%d"))
    df = parse_ohlcv_csv(csv)
    assert not df.attrs.get("descartadas"), df.attrs


def test_el_alta_devuelve_lo_que_se_dejo_afuera(client_with_sample):
    """Y llega hasta la pantalla, que es donde hace falta."""
    r = client_with_sample.post(
        "/api/datasets/upload",
        files={"file": ("roto.csv", _roto().encode(), "text/csv")})
    assert r.status_code == 200, r.text[:300]
    meta = r.json()
    assert meta.get("descartadas"), "el alta no dijo nada de las filas que tiró"
    assert meta["filas_leidas"] == 900


def test_un_archivo_sano_no_ensucia_la_respuesta(client_with_sample):
    csv = "\n".join(_velas(500, dt.datetime(2023, 1, 1), "%Y-%m-%d"))
    r = client_with_sample.post(
        "/api/datasets/upload",
        files={"file": ("sano.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text[:300]
    assert "descartadas" not in r.json()


def test_un_archivo_sin_velas_utiles_se_rechaza():
    with pytest.raises(ValueError):
        parse_ohlcv_csv("timestamp,open,high,low,close\n2023-01-01,1,1,1,1\n")


def test_un_archivo_con_la_fila_mas_nueva_primero_no_se_da_vuelta():
    """Yahoo, Investing y varios brókers exportan al revés.

    El primer arreglo exigía que las velas quedaran en orden CRECIENTE para
    aceptar la lectura día/mes. Un archivo descendente no cumple eso de
    ninguna de las dos maneras, así que la elección volvía a caer en el
    criterio de siempre y las fechas se daban vuelta igual: 400 velas de
    diecisiete días entraban como doce meses, con HTTP 200 y el tilde verde.

    Lo que distingue un día de un mes no es hacia dónde va la serie, es que
    vaya en UNA dirección.
    """
    filas = _velas(400, dt.datetime(2023, 1, 2), "%d/%m/%Y")
    cabecera, cuerpo = filas[0], filas[1:]
    cuerpo.reverse()
    df = parse_ohlcv_csv("\n".join([cabecera, *cuerpo]))
    abarca = (df.index[-1] - df.index[0]).days
    assert abarca <= 20, (
        f"la serie abarca {abarca} días: un archivo ordenado de nuevo a viejo "
        "sigue dándose vuelta las fechas")


def test_un_archivo_iso_al_reves_tampoco_se_rompe():
    filas = _velas(400, dt.datetime(2023, 3, 1), "%Y-%m-%d")
    cabecera, cuerpo = filas[0], filas[1:]
    cuerpo.reverse()
    df = parse_ohlcv_csv("\n".join([cabecera, *cuerpo]))
    assert str(df.index[0].date()) == "2023-03-01"


def test_una_planilla_en_castellano_entra():
    """Punto y coma, coma decimal y cabeceras en castellano: lo que exporta
    Excel configurado en es-AR, que antes rebotaba entero."""
    filas = ["fecha;hora;apertura;maximo;minimo;cierre;volumen"]
    t = dt.datetime(2023, 1, 2)
    for _ in range(400):
        px = 1800.0
        coma = lambda x: f"{x:.2f}".replace(".", ",")  # noqa: E731
        filas.append(f"{t:%d/%m/%Y};{t:%H:%M};{coma(px)};{coma(px + 1)};"
                     f"{coma(px - 1)};{coma(px + .5)};100")
        t += dt.timedelta(hours=1)
    df = parse_ohlcv_csv("\n".join(filas))
    assert len(df) == 400
    assert float(df["open"].iloc[0]) == 1800.0, "la coma decimal quedó sin leer"
