from datetime import datetime, timedelta, timezone
import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from trading_desk.config import Config

def fetch_hourly(
    symbol: str,
    days: int,
    cfg: Config,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Fetch completed hourly bars ending at a stable UTC hour boundary."""
    completed_through = end or datetime.now(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    if completed_through.tzinfo is None:
        completed_through = completed_through.replace(tzinfo=timezone.utc)
    else:
        completed_through = completed_through.astimezone(timezone.utc)

    client = CryptoHistoricalDataClient(cfg.alpaca_api_key or None, cfg.alpaca_secret_key or None)
    req = CryptoBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame(1, TimeFrameUnit.Hour),
        start=completed_through - timedelta(days=days),
        end=completed_through,
    )
    raw = client.get_crypto_bars(req).df
    if raw.empty:
        raise RuntimeError(f"No bars returned for {symbol}")
    if isinstance(raw.index, pd.MultiIndex):
        df = raw.xs(symbol, level=0).copy()
    else:
        df = raw.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    # Alpaca may return the bar timestamped exactly at `end`. That bar has only
    # just opened, so exclude it explicitly rather than relying on API boundary
    # semantics.
    df = df[df.index < completed_through]
    return df[["open", "high", "low", "close", "volume", "trade_count", "vwap"]]
