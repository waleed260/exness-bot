"""Enhanced SMC (Smart Money Concepts) XAUUSD M5 strategy.

Multi-timeframe: M5 entries, M15 structure bias, optional H1 EMA trend.
Confluences: liquidity sweep + BOS + order block + FVG + displacement +
price action + premium/discount + VP levels + H1 trend + volume.
Filters: session, regime (ADX), volatility spike (news proxy).
"""

from datetime import time
import pandas as pd

from exness_bot import config
from exness_bot.indicators import h1_ema_trend

_MAX_SCORE = 15


class SMCStrategy:
    def __init__(self):
        self.last_trade = None

    def decide(self, m5, m15, h1=None, vp_snapshot=None, spread_points=None):
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

        atr_series = self._atr(m5)
        atr = atr_series.iloc[-1]

        if config.SMC_USE_REGIME_FILTER and self._is_ranging(m5):
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

        vol = self._volume_score(m5)

        bscore = (
            2 * (bias > 0) + 2 * bs + 2 * bb + 2 * (bo is not None)
            + bdisp + bf + disc + bpa
            + (h1_bias > 0) + vp_buy + vol
        )
        sscore = (
            2 * (bias < 0) + 2 * ss + 2 * sb + 2 * (so is not None)
            + sdisp + sf + prem + spa
            + (h1_bias < 0) + vp_sell + vol
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
                "volume confirmed" if vol else "",
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
                "volume confirmed" if vol else "",
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
        for i in range(len(d) - 2, start - 1, -1):
            c = d.iloc[i]
            if (c.close < c.open) if bull else (c.close > c.open):
                f = d.iloc[i + 1 : min(i + 4, len(d))]
                move = (f.high.max() - c.high) if bull else (c.low - f.low.min())
                if move >= atr * 0.8:
                    return {"high": float(c.high), "low": float(c.low)}
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

    def _in_session(self, ts):
        t = ts.timetz().replace(tzinfo=None) if hasattr(ts, "timetz") else ts
        h = t.hour + t.minute / 60.0
        sessions = [config.SMC_SESSION_LONDON, config.SMC_SESSION_NY]
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

    def _vp_confluence(self, price, vp_snapshot, atr, is_buy):
        if vp_snapshot is None or not config.SMC_USE_VP_CONFLUENCE:
            return False
        proximity = 0.5 * atr
        if is_buy:
            return abs(price - vp_snapshot.val) < proximity or abs(price - vp_snapshot.poc) < proximity
        return abs(price - vp_snapshot.vah) < proximity or abs(price - vp_snapshot.poc) < proximity

    def _adx(self, d, period=None):
        if period is None:
            period = config.SMC_ADX_PERIOD
        high, low, close = d.high, d.low, d.close
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
        tr = pd.concat([
            high - low, (high - close.shift()).abs(), (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr_r = tr.rolling(period).mean()
        safe = atr_r.replace(0, 1e-9)
        plus_di = 100 * plus_dm.rolling(period).mean() / safe
        minus_di = 100 * minus_dm.rolling(period).mean() / safe
        denom = (plus_di + minus_di).replace(0, 1e-9)
        dx = 100 * (plus_di - minus_di).abs() / denom
        return dx.rolling(period).mean()

    def _is_ranging(self, d):
        adx = self._adx(d)
        val = adx.iloc[-1]
        if pd.isna(val):
            return False
        return bool(val < config.SMC_ADX_RANGE_THRESHOLD)

    def _volatility_spike(self, atr_series, current_atr):
        if pd.isna(current_atr):
            return False
        recent = atr_series.iloc[-51:-1]
        avg = recent.mean()
        if avg <= 0 or pd.isna(avg):
            return False
        return current_atr / avg > config.SMC_NEWS_VOLATILITY_MULT

    def _volume_score(self, d):
        if not config.SMC_USE_VOLUME_CONFIRM:
            return 0
        vol_col = None
        if "tick_volume" in d.columns:
            vol_col = "tick_volume"
        elif "volume" in d.columns:
            vol_col = "volume"
        if vol_col is None:
            return 0
        recent = d[vol_col].iloc[-20:]
        avg = recent.mean()
        if avg <= 0:
            return 0
        return 1 if d[vol_col].iloc[-1] > avg * 1.2 else 0

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
