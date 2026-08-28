import numpy as np
import pandas as pd

def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    parts = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1)
    return parts.max(axis=1)

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).rolling(period).mean()

def realized_vol(close: pd.Series, period: int = 24) -> pd.Series:
    r = np.log(close / close.shift(1))
    return r.rolling(period).std() * np.sqrt(24 * 365)

def prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema20"] = ema(out["close"], 20)
    out["ema50"] = ema(out["close"], 50)
    out["atr14"] = atr(out, 14)
    out["vol24"] = realized_vol(out["close"], 24)
    out["high20_prev"] = out["high"].shift(1).rolling(20).max()
    out["ret6"] = out["close"].pct_change(6)
    out["ret24"] = out["close"].pct_change(24)
    return out
