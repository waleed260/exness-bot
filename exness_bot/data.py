"""Live data: pull MT5 rates, build the indicator frame the strategy needs."""

import pandas as pd

from exness_bot import config
from exness_bot import mt5_client
from exness_bot import indicators
from exness_bot import market_data

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
    market_data.validate_frame(df, require_fresh=True)
    return indicators.add_indicators(df)


def load_multi_frame():
    """Fetch M5, M15, H1 for the SMC strategy. Returns dict of DataFrames + VP snapshot."""
    from exness_bot.volume_profile import VolumeProfile
    from datetime import datetime, timezone

    symbol = mt5_client.resolved_symbol()
    result = {}

    timeframes = [
        ("m5", config.SMC_PRIMARY_TF, config.SMC_LOOKBACK_M5),
        ("m15", config.SMC_STRUCTURE_TF, config.SMC_LOOKBACK_M15),
        ("h1", config.SMC_TREND_TF, config.SMC_LOOKBACK_H1),
    ]

    for role, tf, count in timeframes:
        raw = mt5_client.rates(symbol, tf, count)
        if raw is None or len(raw) < 2:
            raise RuntimeError(f"Not enough {role.upper()} data from MT5")
        df = pd.DataFrame(raw)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.iloc[:-1].reset_index(drop=True)
        market_data.validate_frame(df, require_fresh=(role == "m5"))
        result[role] = df

    if config.SMC_USE_VP_CONFLUENCE:
        vp = VolumeProfile(bin_size=config.SMC_VP_BIN_SIZE)
        for _, row in result["m5"].iterrows():
            vp.add_closed_candle(row.to_dict())
        try:
            now = datetime.now(timezone.utc)
            result["vp_snapshot"] = vp.snapshot_before(now)
        except (ValueError, RuntimeError):
            result["vp_snapshot"] = None
    else:
        result["vp_snapshot"] = None

    tick = mt5_client.tick()
    result["spread_points"] = mt5_client.spread_points() if tick else None

    return result
