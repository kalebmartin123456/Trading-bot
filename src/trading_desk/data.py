from datetime import datetime, timedelta, timezone
import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from trading_desk.config import Config

BAR_COLUMNS = ["open", "high", "low", "close", "volume", "trade_count", "vwap"]


def _completed_through(end: datetime | None) -> datetime:
    completed_through = end or datetime.now(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    if completed_through.tzinfo is None:
        return completed_through.replace(tzinfo=timezone.utc)
    return completed_through.astimezone(timezone.utc)


def fetch_hourly_many(
    symbols: list[str] | tuple[str, ...],
    days: int,
    cfg: Config,
    end: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch one synchronized completed-bar dataset for several symbols."""
    requested = list(dict.fromkeys(symbols))
    if not requested:
        raise ValueError("At least one symbol is required.")
    if days <= 0:
        raise ValueError("days must be positive.")
    completed_through = _completed_through(end)

    client = CryptoHistoricalDataClient(cfg.alpaca_api_key or None, cfg.alpaca_secret_key or None)
    req = CryptoBarsRequest(
        symbol_or_symbols=requested,
        timeframe=TimeFrame(1, TimeFrameUnit.Hour),
        start=completed_through - timedelta(days=days),
        end=completed_through,
    )
    raw = client.get_crypto_bars(req).df
    if raw.empty:
        raise RuntimeError(f"No bars returned for {requested}")

    frames: dict[str, pd.DataFrame] = {}
    for symbol in requested:
        if isinstance(raw.index, pd.MultiIndex):
            try:
                df = raw.xs(symbol, level=0).copy()
            except KeyError as exc:
                raise RuntimeError(f"No bars returned for {symbol}") from exc
        elif len(requested) == 1:
            df = raw.copy()
        else:
            raise RuntimeError("Expected a symbol-indexed response for a multi-symbol request.")
        df.index = pd.to_datetime(df.index, utc=True)
        # Alpaca may return the bar timestamped exactly at `end`. That bar has
        # only just opened, so exclude it regardless of endpoint boundary rules.
        df = df[df.index < completed_through].sort_index()
        df = df[~df.index.duplicated(keep="last")]
        if df.empty:
            raise RuntimeError(f"No completed bars returned for {symbol}")
        frames[symbol] = df[BAR_COLUMNS]
    return frames


def fetch_hourly(
    symbol: str,
    days: int,
    cfg: Config,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Fetch completed hourly bars ending at a stable UTC hour boundary."""
    return fetch_hourly_many([symbol], days, cfg, end=end)[symbol]
