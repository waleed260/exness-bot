"""Economic calendar: MT5 integration + static recurring schedule + blackout logic."""

from datetime import datetime, timedelta, timezone, date
import calendar

from exness_bot import config


def _first_friday(year, month):
    """Return the date of the first Friday of the given month."""
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        if week[calendar.FRIDAY] != 0:
            return date(year, month, week[calendar.FRIDAY])
    return None


def _nth_weekday(year, month, weekday, n):
    """Return the date of the nth occurrence of weekday in month (1-indexed)."""
    cal = calendar.monthcalendar(year, month)
    count = 0
    for week in cal:
        if week[weekday] != 0:
            count += 1
            if count == n:
                return date(year, month, week[weekday])
    return None


_STATIC_EVENTS = []


def _build_static_events(year):
    """Build the static high-impact USD event schedule for the given year."""
    events = []

    for month in range(1, 13):
        nfp_date = _first_friday(year, month)
        if nfp_date:
            events.append({
                "name": "NFP",
                "time": datetime(nfp_date.year, nfp_date.month, nfp_date.day, 13, 30, tzinfo=timezone.utc),
                "impact": "HIGH",
            })

        cpi_date = _nth_weekday(year, month, calendar.TUESDAY, 2)
        if cpi_date:
            events.append({
                "name": "CPI",
                "time": datetime(cpi_date.year, cpi_date.month, cpi_date.day, 13, 30, tzinfo=timezone.utc),
                "impact": "HIGH",
            })

        ppi_date = _nth_weekday(year, month, calendar.WEDNESDAY, 2)
        if ppi_date:
            events.append({
                "name": "PPI",
                "time": datetime(ppi_date.year, ppi_date.month, ppi_date.day, 13, 30, tzinfo=timezone.utc),
                "impact": "MEDIUM",
            })

    for fomc_str in config.SMC_FOMC_DATES_2026:
        try:
            d = datetime.strptime(fomc_str, "%Y-%m-%d")
            events.append({
                "name": "FOMC",
                "time": datetime(d.year, d.month, d.day, 19, 0, tzinfo=timezone.utc),
                "impact": "HIGH",
            })
        except ValueError:
            pass

    return sorted(events, key=lambda e: e["time"])


def _get_static_events(year):
    """Cached static events for the given year."""
    global _STATIC_EVENTS
    if not _STATIC_EVENTS or _STATIC_EVENTS[0]["time"].year != year:
        _STATIC_EVENTS = _build_static_events(year)
    return _STATIC_EVENTS


def get_mt5_events(dt):
    """Try to fetch events from MT5 calendar. Returns list of event dicts or empty list."""
    if not config.SMC_NEWS_USE_MT5_CALENDAR:
        return []
    try:
        from exness_bot import mt5_client
        events = mt5_client.calendar_get(dt, dt + timedelta(days=1))
        if not events:
            return []
        result = []
        for ev in events:
            importance = getattr(ev, "importance", 0)
            if config.SMC_NEWS_HIGH_IMPACT_ONLY and importance < 3:
                continue
            country = getattr(ev, "country_id", 0)
            if country not in (0, 840):
                continue
            result.append({
                "name": getattr(ev, "name", "Unknown"),
                "time": datetime.fromtimestamp(getattr(ev, "time", 0), tz=timezone.utc),
                "impact": "HIGH" if importance >= 3 else "MEDIUM",
            })
        return result
    except Exception:
        return []


def get_upcoming_events(dt, window_minutes=None):
    """Return events within the blackout window around dt.

    Returns list of dicts with keys: name, time, impact, minutes_until.
    """
    if window_minutes is None:
        window_minutes = config.SMC_NEWS_BLACKOUT_BEFORE_MIN

    if not isinstance(dt, datetime):
        return []
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    events = get_mt5_events(dt)
    if not events and config.SMC_NEWS_USE_STATIC_SCHEDULE:
        events = _get_static_events(dt.year)

    before = timedelta(minutes=config.SMC_NEWS_BLACKOUT_BEFORE_MIN)
    after = timedelta(minutes=config.SMC_NEWS_BLACKOUT_AFTER_MIN)

    result = []
    for ev in events:
        ev_time = ev["time"]
        diff = (ev_time - dt).total_seconds() / 60.0
        if -config.SMC_NEWS_BLACKOUT_AFTER_MIN <= diff <= config.SMC_NEWS_BLACKOUT_BEFORE_MIN:
            if config.SMC_NEWS_HIGH_IMPACT_ONLY and ev["impact"] != "HIGH":
                continue
            result.append({
                "name": ev["name"],
                "time": ev_time,
                "impact": ev["impact"],
                "minutes_until": round(diff, 1),
            })

    return result


def in_news_blackout(dt):
    """Check if dt falls within any news blackout window. Returns (bool, event_name or None)."""
    events = get_upcoming_events(dt)
    if events:
        nearest = min(events, key=lambda e: abs(e["minutes_until"]))
        return True, nearest["name"]
    return False, None
