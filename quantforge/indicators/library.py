"""Built-in indicator library.

All computations are pure pandas/numpy, deterministic, and free of lookahead:
an output at bar *i* only uses data up to and including bar *i*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantforge.indicators.base import Indicator, ParamDef, register

__all__ = ["REGISTRY"]

from quantforge.indicators.base import REGISTRY  # re-export for convenience


def _wilder(s: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (RMA)."""
    return s.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - prev_close).abs(),
         (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def _arr(s: pd.Series) -> np.ndarray:
    return s.to_numpy(dtype=np.float64)


@register
class SMA(Indicator):
    name = "SMA"
    label = "Simple Moving Average"
    category = "trend"
    params = (ParamDef("period", 50, 2, 500, 1),)

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        return {"value": _arr(df["close"].rolling(n).mean())}


@register
class EMA(Indicator):
    name = "EMA"
    label = "Exponential Moving Average"
    category = "trend"
    params = (ParamDef("period", 50, 2, 500, 1),)

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        return {"value": _arr(df["close"].ewm(span=n, adjust=False, min_periods=n).mean())}


@register
class RSI(Indicator):
    name = "RSI"
    label = "Relative Strength Index"
    category = "momentum"
    params = (ParamDef("period", 14, 2, 100, 1),)

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        delta = df["close"].diff()
        gain = _wilder(delta.clip(lower=0.0), n)
        loss = _wilder((-delta).clip(lower=0.0), n)
        rs = gain / loss.replace(0.0, np.nan)
        rsi = 100.0 - 100.0 / (1.0 + rs)
        rsi = rsi.where(loss != 0.0, 100.0)
        return {"value": _arr(rsi)}


@register
class MACD(Indicator):
    name = "MACD"
    label = "MACD"
    category = "momentum"
    params = (
        ParamDef("fast", 12, 2, 100, 1),
        ParamDef("slow", 26, 3, 200, 1),
        ParamDef("signal", 9, 2, 50, 1),
    )
    outputs = ("macd", "signal", "hist")

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        fast, slow, sig = int(p["fast"]), int(p["slow"]), int(p["signal"])
        ema_f = df["close"].ewm(span=fast, adjust=False).mean()
        ema_s = df["close"].ewm(span=slow, adjust=False).mean()
        macd = ema_f - ema_s
        signal = macd.ewm(span=sig, adjust=False).mean()
        return {"macd": _arr(macd), "signal": _arr(signal), "hist": _arr(macd - signal)}


@register
class ATR(Indicator):
    name = "ATR"
    label = "Average True Range"
    category = "volatility"
    params = (ParamDef("period", 14, 2, 100, 1),)

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        return {"value": _arr(_wilder(_true_range(df), n))}


@register
class ADX(Indicator):
    name = "ADX"
    label = "Average Directional Index"
    category = "trend"
    params = (ParamDef("period", 14, 2, 100, 1),)
    outputs = ("adx", "plus_di", "minus_di")

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        up = df["high"].diff()
        down = -df["low"].diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        atr = _wilder(_true_range(df), n)
        plus_di = 100.0 * _wilder(plus_dm, n) / atr
        minus_di = 100.0 * _wilder(minus_dm, n) / atr
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
        adx = _wilder(dx.fillna(0.0), n)
        return {"adx": _arr(adx), "plus_di": _arr(plus_di), "minus_di": _arr(minus_di)}


@register
class VWAP(Indicator):
    name = "VWAP"
    label = "VWAP (session)"
    category = "volume"
    params = ()

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["volume"].astype("float64")
        day = df.index.normalize()
        pv = (tp * vol).groupby(day).cumsum()
        vv = vol.groupby(day).cumsum().replace(0.0, np.nan)
        return {"value": _arr(pv / vv)}


@register
class Donchian(Indicator):
    name = "Donchian"
    label = "Donchian Channel"
    category = "channel"
    params = (ParamDef("period", 20, 2, 300, 1),)
    outputs = ("upper", "lower", "middle")

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        # shift(1): the channel a breakout is measured against excludes the current bar
        upper = df["high"].rolling(n).max().shift(1)
        lower = df["low"].rolling(n).min().shift(1)
        return {"upper": _arr(upper), "lower": _arr(lower), "middle": _arr((upper + lower) / 2.0)}


@register
class Bollinger(Indicator):
    name = "Bollinger"
    label = "Bollinger Bands"
    category = "volatility"
    params = (ParamDef("period", 20, 2, 300, 1), ParamDef("mult", 2.0, 0.5, 5.0, 0.1))
    outputs = ("upper", "middle", "lower", "width")

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n, k = int(p["period"]), float(p["mult"])
        mid = df["close"].rolling(n).mean()
        sd = df["close"].rolling(n).std(ddof=0)
        upper, lower = mid + k * sd, mid - k * sd
        width = (upper - lower) / mid.replace(0.0, np.nan)
        return {"upper": _arr(upper), "middle": _arr(mid),
                "lower": _arr(lower), "width": _arr(width)}


@register
class CCI(Indicator):
    name = "CCI"
    label = "Commodity Channel Index"
    category = "momentum"
    params = (ParamDef("period", 20, 2, 200, 1),)

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        sma = tp.rolling(n).mean()
        mad = (tp - sma).abs().rolling(n).mean()
        cci = (tp - sma) / (0.015 * mad.replace(0.0, np.nan))
        return {"value": _arr(cci)}


@register
class Stochastic(Indicator):
    name = "Stochastic"
    label = "Stochastic Oscillator"
    category = "momentum"
    params = (ParamDef("k_period", 14, 2, 100, 1), ParamDef("d_period", 3, 1, 50, 1))
    outputs = ("k", "d")

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        kn, dn = int(p["k_period"]), int(p["d_period"])
        lo = df["low"].rolling(kn).min()
        hi = df["high"].rolling(kn).max()
        k = 100.0 * (df["close"] - lo) / (hi - lo).replace(0.0, np.nan)
        d = k.rolling(dn).mean()
        return {"k": _arr(k), "d": _arr(d)}


@register
class Supertrend(Indicator):
    name = "Supertrend"
    label = "Supertrend"
    category = "trend"
    params = (ParamDef("period", 10, 2, 100, 1), ParamDef("mult", 3.0, 0.5, 10.0, 0.1))
    outputs = ("line", "direction")   # direction: +1 bullish, -1 bearish

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n, k = int(p["period"]), float(p["mult"])
        atr = _wilder(_true_range(df), n).to_numpy(dtype=np.float64)
        hl2 = ((df["high"] + df["low"]) / 2.0).to_numpy(dtype=np.float64)
        close = df["close"].to_numpy(dtype=np.float64)
        upper = hl2 + k * atr
        lower = hl2 - k * atr
        m = len(close)
        line = np.full(m, np.nan)
        direction = np.full(m, np.nan)
        f_upper, f_lower = np.nan, np.nan
        trend = 1.0
        for i in range(m):
            if np.isnan(atr[i]):
                continue
            u, l = upper[i], lower[i]
            if not np.isnan(f_upper):
                u = u if (u < f_upper or close[i - 1] > f_upper) else f_upper
                l = l if (l > f_lower or close[i - 1] < f_lower) else f_lower
            if np.isnan(f_upper):
                trend = 1.0
            elif close[i] > f_upper:
                trend = 1.0
            elif close[i] < f_lower:
                trend = -1.0
            f_upper, f_lower = u, l
            line[i] = l if trend > 0 else u
            direction[i] = trend
        return {"line": line, "direction": direction}


@register
class Ichimoku(Indicator):
    name = "Ichimoku"
    label = "Ichimoku Cloud"
    category = "trend"
    params = (
        ParamDef("tenkan", 9, 2, 100, 1),
        ParamDef("kijun", 26, 2, 200, 1),
        ParamDef("senkou", 52, 2, 300, 1),
    )
    outputs = ("tenkan", "kijun", "senkou_a", "senkou_b")

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        def midline(n: int) -> pd.Series:
            return (df["high"].rolling(n).max() + df["low"].rolling(n).min()) / 2.0

        tn, kn, sn = int(p["tenkan"]), int(p["kijun"]), int(p["senkou"])
        tenkan, kijun = midline(tn), midline(kn)
        # senkou lines are shifted forward so the value visible at bar i was
        # computed kijun bars earlier — no lookahead
        senkou_a = ((tenkan + kijun) / 2.0).shift(kn)
        senkou_b = midline(sn).shift(kn)
        return {"tenkan": _arr(tenkan), "kijun": _arr(kijun),
                "senkou_a": _arr(senkou_a), "senkou_b": _arr(senkou_b)}


@register
class VolumeSMA(Indicator):
    name = "VolumeSMA"
    label = "Volume Average"
    category = "volume"
    params = (ParamDef("period", 20, 2, 300, 1),)

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        return {"value": _arr(df["volume"].astype("float64").rolling(n).mean())}


@register
class Momentum(Indicator):
    name = "Momentum"
    label = "Momentum (ROC %)"
    category = "momentum"
    params = (ParamDef("period", 10, 1, 200, 1),)

    @classmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        n = int(p["period"])
        roc = 100.0 * (df["close"] / df["close"].shift(n) - 1.0)
        return {"value": _arr(roc)}
