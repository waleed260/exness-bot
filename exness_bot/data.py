"""Live data: pull MT5 rates, build the indicator frame the strategy needs."""

import pandas as pd

from exness_bot import config
from exness_bot import mt5_client
from exness_bot import indicators

# re-exported so existing imports keep working
snapshot = indicators.snapshot


def load_frame():
    """DataFrame of CLOSED candles with indicator columns (forming bar dropped)."""
    raw = mt5_client.rates(mt5_client.resolved_symbol(), config.TIMEFRAME, config.LOOKBACK_BARS)
    need = max(config.SMA_SLOW, config.TREND_SMA) + config.TREND_SLOPE_LOOKBACK + 5
    if raw is None or len(raw) < need:
        raise RuntimeError("Not enough price history returned from MT5")

    df = pd.DataFrame(raw)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.iloc[:-1].reset_index(drop=True)  # drop the forming candle
    return indicators.add_indicators(df)
