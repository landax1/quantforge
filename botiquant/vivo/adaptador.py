"""Hablar con un exchange, y poder no hablarle.

Es la única pieza que sabe que BingX existe. El núcleo decide, el runner
coordina, y acá abajo se traduce esa decisión a lo que el exchange entiende.
Cambiar de exchange es escribir otra clase con estos cinco métodos.

TRES ADAPTADORES Y NO UNO, porque son tres niveles de riesgo distintos:

  * `Papel`    lee datos de verdad y NO manda ninguna orden. Simula el
               resultado y lo anota. Es el modo con el que se compara contra
               el backtest antes de arriesgar nada.
  * `BingX`    contra el entorno de práctica (VST) o el real, según la URL.
               Es el mismo código: lo único que cambia es a dónde apunta.
  * cualquiera que escriba estos cinco métodos.

LO QUE ESTÁ VERIFICADO Y LO QUE NO.

  * Los datos de mercado, contra la API real: velas, contrato y funding
    responden y el formato es el que dice este archivo.
  * La forma del pedido de orden, contra la referencia oficial de BingX. De
    ese contraste salieron TRES errores que no avisaban —los parámetros se
    firman ordenados, un POST manda el cuerpo y no la query, y el
    `positionSide` depende del modo de la cuenta— y los tres devolvían "clave
    incorrecta", que manda a revisar la clave.
  * Lo que NO se probó todavía es una orden REAL contra una cuenta de
    práctica. BingX valida la clave antes que los parámetros —comprobado
    mandando pedidos con credenciales falsas: siempre 100413— así que el
    último tramo sólo se confirma con una clave demo.

El envío está aislado en dos métodos justamente para que, cuando se pruebe y
algo no cuadre, se corrija en un lugar y no en diez.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd

from botiquant.data import bingx, binance_trade

#: El entorno de práctica de BingX. Misma API, mismos endpoints, plata de
#: juguete: comprobado que sirve velas y contratos igual que el real.
BASE_PRACTICA = "https://open-api-vst.bingx.com"
BASE_REAL = "https://open-api.bingx.com"


def a_simbolo(simbolo: str, *, con_guion: bool) -> str:
    """El mismo par, escrito como lo escribe cada casa.

    ==================================================================
    BINGX PIDE BTC-USDT Y BINANCE PIDE BTCUSDT, Y EL EQUIVOCADO NO
    DEVUELVE "FORMATO INVALIDO": DEVUELVE "ESE SIMBOLO NO EXISTE".
    ==================================================================

    Que es el peor mensaje posible, porque manda a revisar el catálogo cuando
    el par existe perfectamente y lo único que está mal es el guion.

    SE TRADUCE ACA Y NO AL GUARDAR EL BOT. El archivo del bot se escribió
    cuando había un solo exchange, así que lleva el símbolo con guion adentro;
    traducir al guardar arreglaría los bots nuevos y dejaría rotos todos los
    que ya existen. Traducir acá los arregla a todos, incluidos los que alguien
    guardó hace meses.

    NO ADIVINA. La cuenta base/cotización no se puede partir por longitud fija
    —hay cotizaciones de tres letras y de cuatro, y BTCUSDC partido a lo bruto
    da "BTCU" + "SDC"— así que si no reconoce la cotización devuelve el símbolo
    tal cual y que falle del lado del exchange con su propio mensaje. Inventar
    un guion en el lugar equivocado daría un símbolo que existe y es otro.
    """
    s = str(simbolo or "").upper().replace("-", "")
    if not con_guion:
        return s
    for cot in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(cot) and len(s) > len(cot):
            return f"{s[:-len(cot)]}-{cot}"
    return simbolo


@dataclass
class Posicion:
    """Lo que el exchange dice que hay abierto. No lo que el bot recuerda."""

    lado: int = 0                 # +1 largo, -1 corto, 0 plano
    cantidad: float = 0.0
    precio_entrada: float = float("nan")

    @property
    def abierta(self) -> bool:
        return self.lado != 0 and abs(self.cantidad) > 1e-12


class Adaptador(Protocol):
    """Los cinco métodos que necesita el runner. Nada más."""

    def velas(self, simbolo: str, intervalo: str, limite: int) -> pd.DataFrame: ...
    def capital(self) -> float: ...
    def posicion(self, simbolo: str) -> Posicion: ...
    def abrir(self, simbolo: str, lado: int, cantidad: float,
              stop: float, objetivo: float) -> dict[str, Any]: ...
    def cerrar(self, simbolo: str, posicion: Posicion) -> dict[str, Any]: ...


# --------------------------------------------------------------------- BingX

class BingX:
    """El exchange de verdad, o su entorno de práctica según `base`.

    Por defecto apunta a PRÁCTICA. Es a propósito: el que quiera operar con
    plata real tiene que escribirlo, y ningún error de configuración puede
    terminar en una orden real por omisión.
    """

    def __init__(self, api_key: str, secret: str, *, base: str = BASE_PRACTICA):
        self.api_key = api_key
        self.secret = secret
        self.base = base
        self._contratos: dict[str, dict[str, Any]] = {}
        #: Se consulta una vez y se recuerda: es una preferencia de la cuenta
        #: que no cambia sola, y preguntarla en cada orden agrega una llamada
        #: a la red en el momento en que menos conviene demorarse.
        self._cobertura: bool | None = None

    @property
    def es_real(self) -> bool:
        return self.base == BASE_REAL

    def _con_base(self, fn, *a, **k):
        """Corre una llamada apuntando a la base de este adaptador.

        `bingx.BASE` es del módulo, y el runner puede tener a la vez uno de
        práctica y uno real. Se cambia y se repone alrededor de cada llamada.
        """
        anterior = bingx.BASE
        bingx.BASE = self.base
        try:
            return fn(*a, **k)
        finally:
            bingx.BASE = anterior

    # ------------------------------------------------------------- lectura
    def _simbolo(self, simbolo: str) -> str:
        """BingX escribe BTC-USDT. Ver `a_simbolo`."""
        return a_simbolo(simbolo, con_guion=True)

    def velas(self, simbolo: str, intervalo: str, limite: int = 500) -> pd.DataFrame:
        return self._con_base(bingx.velas, self._simbolo(simbolo), intervalo, limite)

    def capital(self) -> float:
        s = self._con_base(bingx.saldo, self.api_key, self.secret)
        return float(s.get("disponible") or s.get("saldo") or 0.0)

    def posicion(self, simbolo: str) -> Posicion:
        simbolo = self._simbolo(simbolo)
        for p in self._con_base(bingx.posiciones, self.api_key, self.secret, simbolo):
            cant = abs(float(p["cantidad"]))
            if cant <= 1e-12:
                continue
            lado = -1 if p["lado"].startswith("short") else 1
            return Posicion(lado, cant, float(p["precio_entrada"]))
        return Posicion()

    def cobertura(self) -> bool:
        """Si la cuenta opera en modo cobertura. Ver `bingx.modo_cobertura`."""
        if self._cobertura is None:
            self._cobertura = self._con_base(
                bingx.modo_cobertura, self.api_key, self.secret)
        return self._cobertura

    def _lado_posicion(self, lado: int) -> str:
        """LONG/SHORT en cobertura, BOTH en modo simple.

        Mandar el equivocado hace que el exchange rechace la orden con un
        mensaje que no menciona el modo de posición por ningún lado.
        """
        if not self.cobertura():
            return "BOTH"
        return "LONG" if lado > 0 else "SHORT"

    def contrato(self, simbolo: str) -> dict[str, Any]:
        """Los límites del símbolo, CON NOMBRES QUE NO SON DE NINGUN EXCHANGE.

        Acá se traduce, y es el lugar: este archivo es la única pieza que sabe
        que BingX existe. Mientras hubo un solo exchange daba igual usar sus
        nombres crudos —`tradeMinQuantity`, `quantityPrecision`— pero eso los
        filtró hasta las guardas, que no tienen por qué saber de dónde salen
        los datos. Con un segundo exchange, o el de más abajo finge los nombres
        del primero, o cada capa aprende los dos. Ninguna de las dos cosas.
        """
        simbolo = self._simbolo(simbolo)
        if simbolo not in self._contratos:
            c = self._con_base(bingx.contrato, simbolo)
            self._contratos[simbolo] = {
                "simbolo": simbolo,
                "decimales_cantidad": int(c.get("quantityPrecision", 4)),
                "minimo": float(c.get("tradeMinQuantity") or 0.0),
                "minimo_nocional": float(c.get("tradeMinUSDT") or 0.0),
                "crudo": c,
            }
        return self._contratos[simbolo]

    def redondear(self, simbolo: str, cantidad: float) -> float:
        """La cantidad como el exchange la acepta, o 0 si no llega al mínimo.

        Una orden con más decimales de los permitidos la rechaza, y una por
        debajo del mínimo también. Redondear HACIA ABAJO y no al más cercano:
        hacia arriba se opera más de lo que se dimensionó.
        """
        c = self.contrato(simbolo)
        dec = int(c.get("decimales_cantidad", 4))
        minimo = float(c.get("minimo") or 0.0)
        paso = 10.0 ** -dec
        cant = float(np.floor(abs(cantidad) / paso) * paso)
        cant = round(cant, dec)
        return cant if cant >= minimo and cant > 0 else 0.0

    # ------------------------------------------------------------- escritura
    def abrir(self, simbolo: str, lado: int, cantidad: float,
              stop: float, objetivo: float) -> dict[str, Any]:
        """Una orden a mercado con el stop y el objetivo PUESTOS EN EL EXCHANGE.

        Que el stop viva del lado del exchange y no del bot no es un detalle:
        si se apaga la computadora, se corta internet o el programa se cierra,
        la posición sigue protegida. Un bot que vigila su propio stop deja de
        proteger nada en el momento en que deja de correr, que es justo cuando
        más falta hace.
        """
        simbolo = self._simbolo(simbolo)
        cant = self.redondear(simbolo, cantidad)
        if cant <= 0:
            raise bingx.BingXError(
                f"La cantidad calculada ({cantidad:.8f}) no llega al mínimo de "
                f"{simbolo}. No se manda la orden.")

        params: dict[str, Any] = {
            "symbol": simbolo,
            "side": "BUY" if lado > 0 else "SELL",
            "positionSide": self._lado_posicion(lado),
            "type": "MARKET",
            "quantity": cant,
        }
        if not np.isnan(stop):
            params["stopLoss"] = json.dumps({
                "type": "STOP_MARKET", "stopPrice": round(float(stop), 8),
                "workingType": "MARK_PRICE"})
        if not np.isnan(objetivo):
            params["takeProfit"] = json.dumps({
                "type": "TAKE_PROFIT_MARKET", "stopPrice": round(float(objetivo), 8),
                "workingType": "MARK_PRICE"})

        return self._con_base(bingx._pedir, "/openApi/swap/v2/trade/order",
                              params, self.api_key, self.secret,
                              metodo="POST") or {}

    def cerrar(self, simbolo: str, posicion: Posicion) -> dict[str, Any]:
        """Cierra con una orden del lado contrario, por la cantidad que HAY.

        La cantidad sale de `posicion`, o sea de lo que dijo el exchange, y no
        de lo que el bot calculó al abrir: si el stop se ejecutó parcialmente,
        cerrar por la cantidad original abriría una posición al revés.
        """
        if not posicion.abierta:
            return {"sin_efecto": "no hay posición abierta"}
        simbolo = self._simbolo(simbolo)
        params = {
            "symbol": simbolo,
            "side": "SELL" if posicion.lado > 0 else "BUY",
            "positionSide": self._lado_posicion(posicion.lado),
            "type": "MARKET",
            "quantity": self.redondear(simbolo, posicion.cantidad),
        }
        # En modo simple hace falta `reduceOnly` para que la orden contraria
        # CIERRE en vez de abrir del otro lado. En cobertura no se manda: ahí
        # el `positionSide` ya dice cuál posición se está tocando, y BingX
        # rechaza el parámetro.
        if not self.cobertura():
            params["reduceOnly"] = True
        return self._con_base(bingx._pedir, "/openApi/swap/v2/trade/order",
                              params, self.api_key, self.secret,
                              metodo="POST") or {}


# ------------------------------------------------------------------- Binance

class Binance:
    """Los perpetuos USDT de Binance, SIEMPRE contra el entorno de prueba.

    ==================================================================
    NO SE PUEDE APUNTAR A LA CUENTA REAL, Y ESO NO ES UNA OPCION.
    ==================================================================

    No hay parámetro `base`. No hay un `real=False` que alguien pueda pasar en
    `True`, ni un valor que leer de la configuración, ni un campo que pueda
    llegar vacío. La única URL que este archivo conoce para Binance es la de
    prueba, y para operar con plata de verdad hay que venir a editar esto a
    propósito.

    Es más fuerte que "el valor por omisión es seguro": un valor por omisión lo
    da vuelta un bug, un JSON mal leído o un campo que llegó en None. Esto no
    tiene qué dar vuelta.

    LOS DATOS DE MERCADO SI SALEN DE PRODUCCION, y es a propósito: el volumen
    del entorno de prueba viene de operaciones falsas, y la biblioteca tiene
    dos indicadores que lo usan. Que el bot DECIDA lo mismo en los dos lados
    importa más que la coherencia de mirar y operar contra el mismo sitio. Lo
    que cambia entre entornos es dónde se ejecuta la orden, no qué se ve.
    """

    #: Apalancamiento que se fija en cada símbolo antes de abrir. Bajo a
    #: propósito: el tamaño lo decide el riesgo por operación, esto sólo
    #: dice cuánto margen se aparta.
    APALANCAMIENTO = 5

    #: Siempre falso, y no es un cálculo. Ver el encabezado de la clase.
    es_real = False

    def __init__(self, api_key: str, secret: str):
        self.api_key = api_key
        self.secret = secret
        self.base = binance_trade.BASE_PRUEBA
        self._contratos: dict[str, dict[str, Any]] = {}
        #: Se consulta una vez: es una preferencia de la cuenta que no cambia
        #: sola, y preguntarla en cada orden agrega una llamada a la red justo
        #: en el momento en que menos conviene demorarse.
        self._modo: str | None = None

    # ------------------------------------------------------------- lectura
    def _simbolo(self, simbolo: str) -> str:
        """Binance escribe BTCUSDT, sin guion. Ver `a_simbolo`."""
        return a_simbolo(simbolo, con_guion=False)

    def velas(self, simbolo: str, intervalo: str, limite: int = 500) -> pd.DataFrame:
        # A PRODUCCION, a propósito. Ver el encabezado de la clase.
        return binance_trade.velas(self._simbolo(simbolo), intervalo, limite,
                                   base=binance_trade.BASE_REAL)

    def capital(self) -> float:
        return binance_trade.saldo(self.api_key, self.secret, base=self.base)

    def posicion(self, simbolo: str) -> Posicion:
        p = binance_trade.posicion(self._simbolo(simbolo), self.api_key,
                                   self.secret, base=self.base)
        if not p["lado"]:
            return Posicion()
        return Posicion(p["lado"], p["cantidad"], p["precio_entrada"])

    def modo(self) -> str:
        """"una_via" o "cobertura". Decide con qué se cierra una posición."""
        if self._modo is None:
            self._modo = binance_trade.modo_posicion(
                self.api_key, self.secret, base=self.base)
        return self._modo

    def contrato(self, simbolo: str) -> dict[str, Any]:
        """Los límites del símbolo, con los nombres neutros de siempre.

        `binance_trade.contrato` ya los devuelve así, con lo cual acá no hay
        traducción que hacer — que es justamente la señal de que los nombres
        neutros eran los correctos y no un capricho.
        """
        simbolo = self._simbolo(simbolo)
        if simbolo not in self._contratos:
            self._contratos[simbolo] = binance_trade.contrato(simbolo, self.base)
        return self._contratos[simbolo]

    # ------------------------------------------------------------- escritura
    def abrir(self, simbolo: str, lado: int, cantidad: float,
              stop: float, objetivo: float) -> dict[str, Any]:
        """Abre a mercado y deja el stop puesto EN EL EXCHANGE.

        ==================================================================
        SI LA PROTECCION FALLA, SE CIERRA LA POSICION EN EL ACTO.
        ==================================================================

        En Binance el stop es una SEGUNDA llamada —el Algo Service es otro
        servicio— así que entre que la entrada se llena y el stop queda puesto
        hay una ventana. Si el segundo pedido falla, lo que queda es una
        posición abierta sin protección, y este bot está pensado para correr
        sin que nadie mire: nadie se va a enterar hasta que el precio vaya en
        contra.

        Entre quedarse con una posición desprotegida y cerrar una operación que
        quizás era buena, se cierra. Perder una entrada cuesta una comisión;
        quedarse sin stop cuesta lo que el mercado quiera.

        NO ALCANZA CON QUE EL PEDIDO NO FALLE: se pregunta después si el stop
        está REGISTRADO. Medido el 31/8/2026, un pedido aceptado y un stop
        anotado son dos cosas distintas, y las condicionales ni siquiera
        aparecen donde aparecen las demás órdenes.
        """
        c = self.contrato(simbolo)
        precio = float(self.velas(simbolo, "1m", 1)["close"].iloc[-1])
        simbolo = self._simbolo(simbolo)
        # MARGEN AISLADO Y APALANCAMIENTO BAJO, ANTES DE ABRIR. El primer
        # trade salió en cruzado a 20× porque nadie lo fijaba. Si Binance no
        # deja cambiarlo (ya hay posición u orden en el símbolo), no se abre:
        # abrir en cruzado sería exactamente lo que se quiso evitar.
        binance_trade.preparar_margen(
            simbolo, self.api_key, self.secret,
            apalancamiento=self.APALANCAMIENTO, base=self.base)
        orden = binance_trade.abrir(
            simbolo, lado, cantidad, precio=precio, api_key=self.api_key,
            secret=self.secret, modo=self.modo(), contrato_=c, base=self.base)

        # La respuesta NO trae el precio de ejecución ni con RESULT: se
        # pregunta aparte. Sin esto el registro dice que operó y no a cuánto.
        try:
            d = binance_trade.detalle_orden(
                simbolo, orden.get("orderId"), api_key=self.api_key,
                secret=self.secret, base=self.base)
            orden["precio_ejecutado"] = d["precio"]
        except binance_trade.BinanceError:
            orden["precio_ejecutado"] = 0.0

        if np.isnan(stop) and np.isnan(objetivo):
            return orden

        motivo = ""
        try:
            binance_trade.proteger(
                simbolo, lado, stop=None if np.isnan(stop) else float(stop),
                objetivo=None if np.isnan(objetivo) else float(objetivo),
                api_key=self.api_key, secret=self.secret, modo=self.modo(),
                contrato_=c, base=self.base)
            puestas = {o["tipo"] for o in binance_trade.condicionales_abiertas(
                simbolo, self.api_key, self.secret, base=self.base)}
            if not np.isnan(stop) and "STOP_MARKET" not in puestas:
                motivo = "el pedido se aceptó pero el stop no quedó registrado"
        except binance_trade.BinanceError as exc:
            motivo = str(exc)

        if motivo:
            orden["desprotegida"] = motivo
            orden["cerrada_por_seguridad"] = True
            pos = self.posicion(simbolo)
            if pos.abierta:
                self.cerrar(simbolo, pos)
        return orden

    def cerrar(self, simbolo: str, posicion: Posicion) -> dict[str, Any]:
        """Cierra por la cantidad que HAY, y limpia lo que quedó colgado.

        La cantidad sale de `posicion`, o sea de lo que dijo el exchange, y no
        de lo que el bot calculó al abrir: si el stop se ejecutó parcialmente,
        cerrar por la cantidad original abriría una posición al revés.

        LA LIMPIEZA VA DESPUES Y NUNCA ANTES: cancelar las órdenes con la
        posición abierta la deja desprotegida. Y hace falta porque, medido, el
        stop y el objetivo SOBREVIVEN al cierre de la posición.
        """
        if not posicion.abierta:
            return {"sin_efecto": "no hay posición abierta"}
        contrato_ = self.contrato(simbolo)
        simbolo = self._simbolo(simbolo)
        r = binance_trade.cerrar(
            simbolo, posicion.lado, posicion.cantidad, api_key=self.api_key,
            secret=self.secret, modo=self.modo(),
            contrato_=contrato_, base=self.base)
        try:
            binance_trade.cancelar_todo(simbolo, self.api_key, self.secret,
                                        base=self.base)
        except binance_trade.BinanceError as exc:      # noqa: BLE001
            r["limpieza"] = f"no se pudieron cancelar las pendientes: {exc}"
        return r


# --------------------------------------------------------------------- papel

@dataclass
class Papel:
    """Datos de verdad, órdenes de mentira.

    Envuelve a otro adaptador para leer el mercado —las velas son reales, los
    precios son reales— y simula las órdenes en memoria. Es el modo con el que
    se compara contra el backtest antes de poner un peso.

    NO simula el deslizamiento ni la comisión al llenar: anota el precio de
    referencia y listo. El punto de este modo no es predecir la ganancia sino
    comprobar que el bot DECIDE lo mismo que el backtest, y meterle costos
    simulados encima confundiría las dos cosas.
    """

    datos: Any                             # otro adaptador, sólo para leer
    capital_inicial: float = 1000.0
    _posicion: Posicion = field(default_factory=Posicion)
    ordenes: list[dict[str, Any]] = field(default_factory=list)

    es_real = False

    def velas(self, simbolo: str, intervalo: str, limite: int = 500) -> pd.DataFrame:
        return self.datos.velas(simbolo, intervalo, limite)

    def capital(self) -> float:
        return self.capital_inicial

    def posicion(self, simbolo: str) -> Posicion:
        return self._posicion

    def abrir(self, simbolo: str, lado: int, cantidad: float,
              stop: float, objetivo: float) -> dict[str, Any]:
        precio = float(self.velas(simbolo, "1m", 1)["close"].iloc[-1])
        self._posicion = Posicion(lado, abs(cantidad), precio)
        orden = {"simulada": True, "accion": "abrir",
                 "lado": "largo" if lado > 0 else "corto",
                 "cantidad": abs(cantidad), "precio": precio,
                 "stop": stop, "objetivo": objetivo,
                 "cuando": pd.Timestamp.now(tz="UTC").isoformat()}
        self.ordenes.append(orden)
        return orden

    def cerrar(self, simbolo: str, posicion: Posicion) -> dict[str, Any]:
        if not posicion.abierta:
            return {"sin_efecto": "no hay posición abierta"}
        precio = float(self.velas(simbolo, "1m", 1)["close"].iloc[-1])
        orden = {"simulada": True, "accion": "cerrar",
                 "cantidad": posicion.cantidad, "precio": precio,
                 "precio_entrada": posicion.precio_entrada,
                 "cuando": pd.Timestamp.now(tz="UTC").isoformat()}
        self._posicion = Posicion()
        self.ordenes.append(orden)
        return orden


class SoloDatos:
    """Un adaptador de lectura sin credenciales, para el modo simulacro.

    Los datos de mercado de BingX son públicos: para mirar velas no hace falta
    ninguna clave. Así el simulacro se puede correr sin que el usuario haya
    creado todavía su clave de práctica.
    """

    es_real = False

    def __init__(self, base: str = BASE_PRACTICA):
        self.base = base
        self._bx = BingX("", "", base=base)

    def velas(self, simbolo: str, intervalo: str, limite: int = 500) -> pd.DataFrame:
        return self._bx.velas(simbolo, intervalo, limite)

    def contrato(self, simbolo: str) -> dict[str, Any]:
        return self._bx.contrato(simbolo)

    def capital(self) -> float:
        raise NotImplementedError("SoloDatos no tiene cuenta: usá Papel encima.")

    def posicion(self, simbolo: str) -> Posicion:
        return Posicion()

    def abrir(self, *a, **k):
        raise NotImplementedError("SoloDatos no manda órdenes, y es a propósito.")

    def cerrar(self, *a, **k):
        raise NotImplementedError("SoloDatos no manda órdenes, y es a propósito.")
