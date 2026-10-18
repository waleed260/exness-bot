"""Strategy router — selects the active strategy based on config."""

from exness_bot import config


def decide(data, position_side):
    """Route to the active strategy and return its decision dict.

    Every strategy returns at minimum {'action', 'confidence', 'reason'}.
    SMC additionally returns 'entry', 'sl', 'tp1', 'tp2', etc.
    """
    if config.ACTIVE_STRATEGY == "smc":
        from exness_bot.smc_strategy import make_strategy
        smc = make_strategy()
        return smc.decide(
            data["m5"],
            data["m15"],
            h1=data.get("h1"),
            vp_snapshot=data.get("vp_snapshot"),
            spread_points=data.get("spread_points"),
            news_events=data.get("news_events"),
        )

    from exness_bot import strategy
    return strategy.decide(data, position_side)
