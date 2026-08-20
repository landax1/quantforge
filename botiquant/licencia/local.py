"""La licencia del lado del escritorio: leerla, comprobarla y guardarla.

Todo pasa en la máquina del usuario. La aplicación lleva la clave pública
adentro, así que puede comprobar que una licencia es auténtica sin preguntarle
a ningún servidor — que es lo que la portada promete y lo que hace que la
herramienta siga funcionando con el wifi cortado, en un avión o el día que el
VPS se caiga.

**Hoy no habilita ni bloquea nada.** La aplicación funciona igual con licencia
y sin ella. Esto existe puesto desde el principio por una razón concreta: una
versión publicada que no mira la licencia la va a ignorar para siempre, y no
hay forma de agregarle el control después a las copias que ya están instaladas.
Cablearlo ahora no le cuesta nada a nadie y deja la decisión abierta.

Lo que sí hace desde el día uno es decir quién sos y desde cuándo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from botiquant.licencia.clave import CLAVE_PUBLICA
from botiquant.licencia.firma import Licencia, LicenciaError, verificar
from botiquant.rutas import carpeta_de_trabajo

#: El archivo que se baja de la página de cuenta, con ese nombre.
NOMBRE = "botiquant.licencia"

#: Cuánto puede pesar una licencia. Son unos cientos de bytes de texto; un
#: archivo más grande que esto no es una licencia y no hay por qué leerlo
#: entero para descubrirlo.
TOPE_BYTES = 8 * 1024


@dataclass(frozen=True)
class Estado:
    """Qué sabe la aplicación de quién la está usando.

    Se responde siempre, incluso sin licencia: ``plan`` dice "free" y la
    aplicación anda igual. La diferencia entre no tener licencia y tener una
    que no sirve importa para el mensaje, no para lo que se puede hacer.
    """

    #: "sin_licencia" | "valida" | "vencida" | "invalida"
    situacion: str
    plan: str
    email: str = ""
    alta: int = 0
    fundador: bool = False
    expira: int = 0
    #: por qué no sirve, en las palabras del usuario
    detalle: str = ""

    @property
    def dias_restantes(self) -> int | None:
        if self.expira == 0:
            return None
        return max(0, int((self.expira - time.time()) // 86400))

    def to_dict(self) -> dict[str, Any]:
        return {
            "situacion": self.situacion, "plan": self.plan, "email": self.email,
            "alta": self.alta, "fundador": self.fundador, "expira": self.expira,
            "dias_restantes": self.dias_restantes, "detalle": self.detalle,
            # Que la aplicación funcione completa es una decisión de producto y
            # puede cambiar. Va explícito para que la interfaz no la deduzca:
            # el día que algo se limite, la pantalla se entera por acá.
            "limita": False,
        }


def ruta() -> Path:
    """Dónde vive la licencia: junto a los datos del usuario."""
    return carpeta_de_trabajo() / NOMBRE


def leer(texto: str | None = None) -> Estado:
    """El estado de la licencia. Nunca levanta excepción.

    Con ``texto`` comprueba ese contenido sin guardarlo, que es lo que hace
    falta para poder decir "esta licencia no sirve" ANTES de pisar la que el
    usuario ya tenía puesta.
    """
    if texto is None:
        archivo = ruta()
        try:
            if not archivo.is_file():
                return Estado(situacion="sin_licencia", plan="free")
            if archivo.stat().st_size > TOPE_BYTES:
                return Estado(situacion="invalida", plan="free",
                              detalle="El archivo no parece una licencia.")
            texto = archivo.read_text(encoding="utf-8")
        except OSError as exc:
            return Estado(situacion="invalida", plan="free",
                          detalle=f"No se pudo leer el archivo: {exc}")

    texto = (texto or "").strip()
    if not texto:
        return Estado(situacion="sin_licencia", plan="free")

    try:
        lic: Licencia = verificar(texto, CLAVE_PUBLICA)
    except LicenciaError as exc:
        # `verificar` rechaza las vencidas igual que las falsas, pero para el
        # usuario no son lo mismo: una se arregla entrando a la cuenta y la
        # otra quiere decir que el archivo está mal. El mensaje lo distingue.
        detalle = str(exc)
        vencida = "vencid" in detalle.lower()
        return Estado(situacion="vencida" if vencida else "invalida",
                      plan="free", detalle=detalle)

    return Estado(situacion="valida", plan=lic.plan, email=lic.email,
                  alta=lic.alta, fundador=lic.fundador, expira=lic.expira)


def guardar(texto: str) -> Estado:
    """Comprueba primero y escribe después.

    En ese orden a propósito: pegar una licencia equivocada no puede dejarte
    sin la que tenías. Si no verifica, el archivo anterior queda intacto.
    """
    estado = leer(texto)
    if estado.situacion != "valida":
        return estado
    archivo = ruta()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(texto.strip(), encoding="utf-8")
    return estado


def borrar() -> Estado:
    """Sacar la licencia de la máquina. Es de quien la usa."""
    try:
        ruta().unlink(missing_ok=True)
    except OSError:
        pass
    return Estado(situacion="sin_licencia", plan="free")
