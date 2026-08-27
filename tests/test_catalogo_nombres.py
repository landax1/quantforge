"""Que los dos bitcoins se puedan distinguir.

Desde que existe el perpetuo hay DOS instrumentos de bitcoin en el catálogo, y
son cosas distintas: uno es un CFD que se opera por MetaTrader y paga spread,
el otro es un perpetuo que se opera en un exchange y paga comisión y funding.

`BTCUSD` y `BTCUSDT` a un carácter de distancia no le dicen eso a nadie, y en
el código `crypto` y `cripto` a una letra de distancia era peor: un typo que
compila y que manda el instrumento a la familia equivocada.
"""

from __future__ import annotations

from pathlib import Path

from botiquant.data.catalog import CATALOG

UI = Path(__file__).resolve().parents[1] / "ui"


def _por_label(label: str) -> dict:
    return [e for e in CATALOG if e["label"] == label][0]


def test_las_dos_categorias_de_cripto_no_se_parecen_a_una_letra():
    """`crypto` y `cripto` era un typo que compila.

    Escribir uno por el otro manda el instrumento a la familia equivocada sin
    ningún error: aparece en la lista, con otro ícono y otro rótulo.
    """
    cats = {e["category"] for e in CATALOG}
    assert "cripto" not in cats, "volvió el nombre que se confunde con `crypto`"
    assert {"crypto", "perpetuos"} <= cats


def test_el_cfd_de_bitcoin_no_reclama_el_nombre_del_perpetuo():
    """Estaba de cuando el perpetuo no existía: buscar BTCUSDT devolvía el CFD."""
    assert "BTCUSDT" not in _por_label("BTCUSD").get("aliases", [])


def test_cada_bitcoin_dice_para_donde_es():
    """El nombre corto no alcanza; el largo tiene que resolver la duda."""
    assert "MetaTrader" in _por_label("BTCUSD")["full_name"]
    assert "exchange" in _por_label("BTCUSDT")["full_name"]


def test_toda_categoria_tiene_su_rotulo_y_su_icono():
    """Una categoría sin rótulo se dibuja en crudo; sin ícono cae en `_otro`."""
    i18n = (UI / "i18n.js").read_text(encoding="utf-8")
    app = (UI / "app.js").read_text(encoding="utf-8")
    for cat in sorted({e["category"] for e in CATALOG}):
        assert f'"cat.{cat}"' in i18n, f"falta el rótulo de {cat}"
        assert f"\n  {cat}: {{ icono:" in app, f"falta el ícono de {cat}"
