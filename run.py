"""QuantForge launcher: ``python run.py`` then open http://127.0.0.1:8765.

Set ``PORT`` to serve somewhere else (used when another instance already holds 8765).
"""

from __future__ import annotations

import os
import pathlib

import uvicorn
from dotenv import load_dotenv

# las credenciales viven en .env, fuera del repositorio
load_dotenv(pathlib.Path(__file__).with_name(".env"))

DEFAULT_PORT = 8765


def main() -> None:
    port = int(os.environ.get("PORT") or DEFAULT_PORT)
    uvicorn.run("quantforge.api.app:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
