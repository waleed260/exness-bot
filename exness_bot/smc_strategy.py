"""Enhanced SMC (Smart Money Concepts) XAUUSD M5 strategy.

Multi-timeframe: M5 entries, M15 structure bias, optional H1 EMA trend.
Confluences: liquidity sweep + BOS + order block + FVG + displacement +
price action + premium/discount + VP levels + H1 trend + volume (graduated).
Filters: session killzones + DST, regime (ADX+BB+ATR multi-indicator),
volatility spike, economic calendar news blackout.
"""

from datetime import datetime, date, timedelta, timezone
import pandas as pd

from exness_bot import config
from exness_bot.indicators import h1_ema_trend
from exness_bot import regime as regime_mod
from exness_bot import news_calendar

_MAX_SCORE = 17


class SMCStrategy:
    def __init__(self):
        self.last_trade = None

    def decide(self, m5, m15, h1=None, vp_snapshot=None, spread_points=None, news_events=None):
        m5 = self._clean(m5)
        m15 = self._clean(m15)
        if len(m5) < 80 or len(m15) < 40:
            return self._hold("not enough candles")

        i = len(m5) - 1
        if self.last_trade is not None and i - self.last_trade < config.SMC_COOLDOWN_BARS:
            return self._hold("cooldown active")

        last_time = m5["time"].iloc[-1] if "time" in m5.columns else m5.index[-1]
        if not self._in_session(last_time):
            return self._hold("outside London/New York session")

        if spread_points is not None and spread_points > config.SMC_SPREAD_FILTER_POINTS:
            return self._hold("spread too wide")

        if news_events:
            nearest = min(news_events, key=lambda e: abs(e.get("minutes_until", 999)))
            mins = nearest.get("minutes_until", 999)
            name = nearest.get("name", "event")
            if mins >= 0:
                return self._hold(f"news blackout: {name} in {mins:.0f}min")
            else:
                return self._hold(f"post-news cooldown: {name} ended {abs(mins):.0f}min ago")

        atr_series = self._atr(m5)
        atr = atr_series.iloc[-1]

        reg = regime_mod.detect_regime(m5)
        if config.SMC_USE_REGIME_FILTER and reg == regime_mod.RANGING:
            return self._hold("ranging market — SMC signals unreliable")

        if config.SMC_USE_NEWS_FILTER and self._volatility_spike(atr_series, atr):
            return self._hold("abnormal volatility — possible news event")

        bias = self._m15_bias(m15)
        if bias == 0:
            return self._hold("M15 structure unclear")

        sw = self._swings(m5)
        hi = [x[1] for x in sw["h"][-8:]]
        lo = [x[1] for x in sw["l"][-8:]]
        buy_liq = min(lo) if lo else None
        sell_liq = max(hi) if hi else None

        bs = self._bull_sweep(m5, buy_liq)
        ss = self._bear_sweep(m5, sell_liq)
        bb = self._bull_bos(m5, sw)
        sb = self._bear_bos(m5, sw)
        bo = self._order_block(m5, atr, bull=True)
        so = self._order_block(m5, atr, bull=False)
        bf = self._fvg(m5, bull=True)
        sf = self._fvg(m5, bull=False)
        bdisp = self._displacement(m5, atr, bull=True)
        sdisp = self._displacement(m5, atr, bull=False)
        bpa = self._price_action(m5, bull=True)
        spa = self._price_action(m5, bull=False)

        mid = self._equilibrium(sw)
        price = float(m5.close.iloc[-1])
        disc = mid is not None and price <= mid
        prem = mid is not None and price >= mid

        h1_bias = h1_ema_trend(h1) if h1 is not None and config.SMC_USE_H1_TREND else 0
        vp_buy = self._vp_confluence(price, vp_snapshot, atr, is_buy=True)
        vp_sell = self._vp_confluence(price, vp_snapshot, atr, is_buy=False)

        vol_buy = self._volume_score(m5, bo, bs, is_buy=True)
        vol_sell = self._volume_score(m5, so, ss, is_buy=False)

        sq = self._session_quality(last_time)

        bscore = (
            2 * (bias > 0) + 2 * bs + 2 * bb + 2 * (bo is not None)
            + bdisp + bf + disc + bpa
            + (h1_bias > 0) + vp_buy + vol_buy + sq
        )
        sscore = (
            2 * (bias < 0) + 2 * ss + 2 * sb + 2 * (so is not None)
            + sdisp + sf + prem + spa
            + (h1_bias < 0) + vp_sell + vol_sell + sq
        )

        bc = bias > 0 and bs and bb and bo is not None and bscore >= config.SMC_MIN_SCORE
        sc = bias < 0 and ss and sb and so is not None and sscore >= config.SMC_MIN_SCORE

        if not bc and not sc:
            return self._hold(
                self._reason(bias, bs, ss, bb, sb, bo, so, bscore, sscore),
                max(bscore, sscore),
            )

        action = "buy" if bc and (not sc or bscore >= sscore) else "sell"
        ob = bo if action == "buy" else so
        liq = buy_liq if action == "buy" else sell_liq
        entry = price

        if action == "buy":
            sl = min(float(ob["low"]), float(liq)) - atr * config.SMC_SL_ATR_BUFFER
        else:
            sl = max(float(ob["high"]), float(liq)) + atr * config.SMC_SL_ATR_BUFFER

        risk = abs(entry - sl)
        if risk <= 0:
            return self._hold("invalid stop distance")

        tp1 = entry + (risk * config.SMC_TP1_R if action == "buy" else -risk * config.SMC_TP1_R)
        tp2 = entry + (risk * config.SMC_TP2_R if action == "buy" else -risk * config.SMC_TP2_R)

        self.last_trade = i
        score = max(bscore, sscore)
        vol = vol_buy if action == "buy" else vol_sell

        parts = []
        if action == "buy":
            parts = [
                "M15 bullish structure",
                "sell-side sweep" if bs else "",
                "bullish BOS" if bb else "",
                "bullish OB",
                "displacement" if bdisp else "",
                "FVG" if bf else "",
                "discount" if disc else "",
                "price action" if bpa else "",
                "H1 bullish" if h1_bias > 0 else "",
                "VP confluence" if vp_buy else "",
                f"volume {vol}/2" if vol else "",
                "killzone" if sq else "",
            ]
        else:
            parts = [
                "M15 bearish structure",
                "buy-side sweep" if ss else "",
                "bearish BOS" if sb else "",
                "bearish OB",
                "displacement" if sdisp else "",
                "FVG" if sf else "",
                "premium" if prem else "",
                "price action" if spa else "",
                "H1 bearish" if h1_bias < 0 else "",
                "VP confluence" if vp_sell else "",
                f"volume {vol}/2" if vol else "",
                "killzone" if sq else "",
            ]

        reason = " | ".join(p for p in parts if p)

        return {
            "action": action,
            "confidence": round(min(1.0, score / _MAX_SCORE), 2),
            "score": score,
            "reason": reason,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "risk_distance": risk,
            "partial_close_at_tp1": config.SMC_PARTIAL_CLOSE_PCT,
            "move_sl_to_breakeven_at_tp1": True,
        }

    # ---- helpers ----

    def _hold(self, reason, score=0):
        return {
            "action": "hold",
            "confidence": round(min(1.0, score / _MAX_SCORE), 2),
            "score": score,
            "reason": reason,
        }

    def _clean(self, d):
        d = d.copy()
        d.columns = [str(x).lower() for x in d.columns]
        return d.dropna(subset=["open", "high", "low", "close"])

    def _atr(self, d):
        pc = d.close.shift()
        tr = pd.concat(
            [d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1
        ).max(axis=1)
        return tr.rolling(config.SMC_ATR_PERIOD).mean()

    def _swings(self, d):
        n = config.SMC_SWING_LOOKBACK
        h, l = [], []
        for i in range(n, len(d) - n):
            if d.high.iloc[i] >= d.high.iloc[i - n : i + n + 1].max():
                h.append((i, float(d.high.iloc[i])))
            if d.low.iloc[i] <= d.low.iloc[i - n : i + n + 1].min():
                l.append((i, float(d.low.iloc[i])))
        return {"h": h, "l": l}

    def _m15_bias(self, d):
        s = self._swings(d)
        h, l = s["h"], s["l"]
        if len(h) < 2 or len(l) < 2:
            return 0
        if h[-1][1] > h[-2][1] and l[-1][1] > l[-2][1]:
            return 1
        if h[-1][1] < h[-2][1] and l[-1][1] < l[-2][1]:
            return -1
        return 0

    def _bull_sweep(self, d, lvl):
        return lvl is not None and d.low.iloc[-1] < lvl and d.close.iloc[-1] > lvl

    def _bear_sweep(self, d, lvl):
        return lvl is not None and d.high.iloc[-1] > lvl and d.close.iloc[-1] < lvl

    def _bull_bos(self, d, s):
        return (
            len(s["h"]) >= 2
            and d.close.iloc[-1] > s["h"][-2][1]
            and d.close.iloc[-2] <= s["h"][-2][1]
        )

    def _bear_bos(self, d, s):
        return (
            len(s["l"]) >= 2
            and d.close.iloc[-1] < s["l"][-2][1]
            and d.close.iloc[-2] >= s["l"][-2][1]
        )

    def _order_block(self, d, atr, bull):
        start = max(0, len(d) - 12)
        vol_col = self._vol_col(d)
        vol_avg = d[vol_col].iloc[-20:].mean() if vol_col else 0

        for i in range(len(d) - 2, start - 1, -1):
            c = d.iloc[i]
            if (c.close < c.open) if bull else (c.close > c.open):
                f = d.iloc[i + 1 : min(i + 4, len(d))]
                move = (f.high.max() - c.high) if bull else (c.low - f.low.min())
                if move >= atr * 0.8:
                    vol_ok = True
                    if vol_col and vol_avg > 0:
                        vol_ok = c[vol_col] > vol_avg * config.SMC_VOLUME_OB_MULTIPLIER
                    return {"high": float(c.high), "low": float(c.low), "vol_confirmed": vol_ok}
        return None

    def _fvg(self, d, bull):
        if len(d) < 3:
            return False
        if bull:
            return d.low.iloc[-1] > d.high.iloc[-3]
        return d.high.iloc[-1] < d.low.iloc[-3]

    def _displacement(self, d, atr, bull):
        move = d.close.iloc[-1] - d.open.iloc[-1] if bull else d.open.iloc[-1] - d.close.iloc[-1]
        return move >= atr * config.SMC_DISPLACEMENT_ATR

    def _price_action(self, d, bull):
        c = d.iloc[-1]
        r = max(float(c.high - c.low), 1e-9)
        body = abs(float(c.close - c.open))
        if bull:
            return c.close > c.open and body / r >= config.SMC_BODY_FRAC and c.close >= c.low + r * 0.65
        return c.close < c.open and body / r >= config.SMC_BODY_FRAC and c.close <= c.low + r * 0.35

    def _equilibrium(self, s):
        if not s["h"] or not s["l"]:
            return None
        hi = s["h"][-1][1]
        lo = s["l"][-1][1]
        return (hi + lo) / 2 if hi > lo else None

    # ---- DST helpers ----

    def _last_sunday(self, year, month):
        """Return the last Sunday of the given month."""
        last_day = 31
        while last_day > 0:
            try:
                d = date(year, month, last_day)
                if d.weekday() == 6:
                    return d
            except ValueError:
                pass
            last_day -= 1
        return date(year, month, 1)

    def _nth_sunday(self, year, month, n):
        """Return the nth Sunday of the given month."""
        import calendar as cal_mod
        weeks = cal_mod.monthcalendar(year, month)
        count = 0
        for week in weeks:
            if week[cal_mod.SUNDAY] != 0:
                count += 1
                if count == n:
                    return date(year, month, week[cal_mod.SUNDAY])
        return date(year, month, 1)

    def _dst_offsets(self, ts):
        """Return (london_offset, ny_offset) in hours for DST adjustment."""
        if not config.SMC_USE_DST_ADJUST:
            return 0, 0
        if not hasattr(ts, "year"):
            return 0, 0
        d = ts.date() if hasattr(ts, "date") else ts
        y = d.year

        uk_start = self._last_sunday(y, 3)
        uk_end = self._last_sunday(y, 10)
        london_dst = 1 if uk_start <= d < uk_end else 0

        us_start = self._nth_sunday(y, 3, 2)
        us_end = self._nth_sunday(y, 11, 1)
        ny_dst = 1 if us_start <= d < us_end else 0

        return london_dst, ny_dst

    def _in_session(self, ts):
        t = ts.timetz().replace(tzinfo=None) if hasattr(ts, "timetz") else ts
        h = t.hour + t.minute / 60.0
        lon_off, ny_off = self._dst_offsets(ts)

        lon_s, lon_e = config.SMC_SESSION_LONDON
        lon_s -= lon_off
        lon_e -= lon_off
        ny_s, ny_e = config.SMC_SESSION_NY
        ny_s -= ny_off
        ny_e -= ny_off

        sessions = [(lon_s, lon_e), (ny_s, ny_e)]
        if config.SMC_USE_ASIAN_SESSION:
            sessions.append(config.SMC_SESSION_ASIAN)

        for s, e in sessions:
            if s <= e:
                if s <= h <= e:
                    return True
            else:
                if h >= s or h <= e:
                    return True
        return False

    def _session_quality(self, ts):
        """Return 1 if in killzone or session overlap, 0 otherwise."""
        if not config.SMC_USE_SESSION_QUALITY:
            return 0
        t = ts.timetz().replace(tzinfo=None) if hasattr(ts, "timetz") else ts
        h = t.hour + t.minute / 60.0
        lon_off, ny_off = self._dst_offsets(ts)

        killzones = [
            (config.SMC_KILLZONE_LONDON[0] - lon_off, config.SMC_KILLZONE_LONDON[1] - lon_off),
            (config.SMC_KILLZONE_NY[0] - ny_off, config.SMC_KILLZONE_NY[1] - ny_off),
            (config.SMC_KILLZONE_OVERLAP[0] - ny_off, config.SMC_KILLZONE_OVERLAP[1] - lon_off),
        ]
        if config.SMC_USE_ASIAN_SESSION:
            killzones.append(config.SMC_KILLZONE_ASIAN)

        for s, e in killzones:
            if s <= e:
                if s <= h <= e:
                    return 1
            else:
                if h >= s or h <= e:
                    return 1
        return 0

    def _vp_confluence(self, price, vp_snapshot, atr, is_buy):
        if vp_snapshot is None or not config.SMC_USE_VP_CONFLUENCE:
            return False
        proximity = 0.5 * atr
        if is_buy:
            return abs(price - vp_snapshot.val) < proximity or abs(price - vp_snapshot.poc) < proximity
        return abs(price - vp_snapshot.vah) < proximity or abs(price - vp_snapshot.poc) < proximity

    # ---- volume helpers ----

    def _vol_col(self, d):
        if "tick_volume" in d.columns:
            return "tick_volume"
        if "volume" in d.columns:
            return "volume"
        return None

    def _volume_delta(self, d, is_buy):
        """Volume delta: sum of volume on up-candles minus down-candles. Aligned = positive signal."""
        vol_col = self._vol_col(d)
        if vol_col is None:
            return False
        lookback = config.SMC_VOLUME_DELTA_LOOKBACK
        recent = d.iloc[-lookback:]
        up_vol = recent.loc[recent.close > recent.open, vol_col].sum()
        down_vol = recent.loc[recent.close < recent.open, vol_col].sum()
        delta = up_vol - down_vol
        if is_buy:
            return bool(delta > 0)
        return bool(delta < 0)

    def _volume_score(self, d, ob, sweep_hit, is_buy):
        """Graduated volume score: 0/1/2."""
        if not config.SMC_USE_VOLUME_CONFIRM:
            return 0
        vol_col = self._vol_col(d)
        if vol_col is None:
            return 0

        score = 0
        avg = d[vol_col].iloc[-20:].mean()
        if avg <= 0:
            return 0

        entry_vol_ok = d[vol_col].iloc[-1] > avg * 1.2
        ob_vol_ok = ob is not None and ob.get("vol_confirmed", False)
        delta_ok = self._volume_delta(d, is_buy)

        if entry_vol_ok or ob_vol_ok:
            score = 1
        if (entry_vol_ok or ob_vol_ok) and delta_ok:
            score = 2

        return score

    def _volatility_spike(self, atr_series, current_atr):
        if pd.isna(current_atr):
            return False
        recent = atr_series.iloc[-51:-1]
        avg = recent.mean()
        if avg <= 0 or pd.isna(avg):
            return False
        return current_atr / avg > config.SMC_NEWS_VOLATILITY_MULT

    def _reason(self, bias, bs, ss, bb, sb, bo, so, bsco, ssco):
        if bias > 0:
            if not bs:
                return "BUY watch: waiting for sell-side liquidity sweep"
            if not bb:
                return "BUY watch: waiting for bullish BOS/CHOCH"
            if bo is None:
                return "BUY watch: waiting for bullish order block"
            return f"BUY setup incomplete: score {bsco}/{config.SMC_MIN_SCORE}"
        if bias < 0:
            if not ss:
                return "SELL watch: waiting for buy-side liquidity sweep"
            if not sb:
                return "SELL watch: waiting for bearish BOS/CHOCH"
            if so is None:
                return "SELL watch: waiting for bearish order block"
            return f"SELL setup incomplete: score {ssco}/{config.SMC_MIN_SCORE}"
        return "HOLD: M15 structure unclear"


_instance = None


def make_strategy():
    global _instance
    if _instance is None:
        _instance = SMCStrategy()
    return _instance
