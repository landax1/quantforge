"""La base cambió de nombre con el rename QuantForge → Botiquant.

Esto se prueba porque es lo único del rename que puede destruir datos del
usuario: si la migración falla en silencio, la app arranca con una base vacía
y el usuario cree que perdió sus instrumentos y sus estrategias.
"""

from __future__ import annotations

import sqlite3

from botiquant.api.app import _base_de_datos


def _base_con_algo(ruta):
    """Una base con una fila reconocible, para distinguirla de una recién
    creada."""
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE datasets (id TEXT)")
    con.execute("INSERT INTO datasets VALUES ('EURUSD')")
    con.commit()
    con.close()


def _filas(ruta) -> list[str]:
    con = sqlite3.connect(ruta)
    try:
        return [r[0] for r in con.execute("SELECT id FROM datasets")]
    finally:
        con.close()


def test_the_old_database_is_carried_over(tmp_path):
    """Lo que importa no es que exista el archivo nuevo, sino que adentro
    estén los datos viejos."""
    _base_con_algo(tmp_path / "quantforge.sqlite")

    elegida = _base_de_datos(tmp_path)

    assert elegida == tmp_path / "botiquant.sqlite"
    assert _filas(elegida) == ["EURUSD"]
    assert not (tmp_path / "quantforge.sqlite").exists()


def test_a_fresh_install_just_uses_the_new_name(tmp_path):
    elegida = _base_de_datos(tmp_path)
    assert elegida == tmp_path / "botiquant.sqlite"


def test_an_existing_new_database_is_never_overwritten(tmp_path):
    """Si ya se migró y quedó un archivo viejo dando vueltas, pisar el nuevo
    borraría todo lo hecho desde la migración."""
    _base_con_algo(tmp_path / "botiquant.sqlite")
    con = sqlite3.connect(tmp_path / "quantforge.sqlite")
    con.execute("CREATE TABLE datasets (id TEXT)")
    con.execute("INSERT INTO datasets VALUES ('VIEJO')")
    con.commit()
    con.close()

    elegida = _base_de_datos(tmp_path)

    assert _filas(elegida) == ["EURUSD"]
    assert (tmp_path / "quantforge.sqlite").exists()


def test_a_locked_file_does_not_stop_the_app(tmp_path, monkeypatch):
    """En Windows basta con que otra instancia tenga la base abierta para que
    el rename falle. Una migración de conveniencia no puede impedir arrancar:
    se sigue con el archivo viejo."""
    _base_con_algo(tmp_path / "quantforge.sqlite")

    import pathlib

    real = pathlib.Path.rename

    def rename_trabado(self, destino):
        if self.name == "quantforge.sqlite":
            raise PermissionError(32, "en uso por otro proceso")
        return real(self, destino)

    monkeypatch.setattr(pathlib.Path, "rename", rename_trabado)

    elegida = _base_de_datos(tmp_path)

    assert elegida == tmp_path / "quantforge.sqlite"
    assert _filas(elegida) == ["EURUSD"]
