from datetime import datetime, timedelta, timezone
import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from trading_desk.config import Config

def fetch_hourly(symbol: str, days: int, cfg: Config) -> pd.DataFrame:
    client = CryptoHistoricalDataClient(cfg.alpaca_api_key or None, cfg.alpaca_secret_key or None)
    req = CryptoBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame(1, TimeFrameUnit.Hour), start=datetime.now(timezone.utc) - timedelta(days=days), end=datetime.now(timezone.utc))
    raw = client.get_crypto_bars(req).df
    if raw.empty:
        raise RuntimeError(f"No bars returned for {symbol}")
    if isinstance(raw.index, pd.MultiIndex):
        df = raw.xs(symbol, level=0).copy()
    else:
        df = raw.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    return df[["open", "high", "low", "close", "volume", "trade_count", "vwap"]]
