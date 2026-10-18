"""Tests for exness_bot.news_calendar — economic calendar and blackout logic."""

import unittest
from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch, MagicMock

from exness_bot import news_calendar, config


class TestFirstFriday(unittest.TestCase):

    def test_jan_2026(self):
        result = news_calendar._first_friday(2026, 1)
        self.assertEqual(result, date(2026, 1, 2))

    def test_march_2026(self):
        result = news_calendar._first_friday(2026, 3)
        self.assertEqual(result, date(2026, 3, 6))

    def test_returns_date(self):
        result = news_calendar._first_friday(2026, 6)
        self.assertIsInstance(result, date)
        self.assertEqual(result.weekday(), 4)


class TestNthWeekday(unittest.TestCase):

    def test_second_tuesday_jan_2026(self):
        result = news_calendar._nth_weekday(2026, 1, 1, 2)  # Tuesday=1
        self.assertEqual(result, date(2026, 1, 13))

    def test_first_sunday_nov_2026(self):
        result = news_calendar._nth_weekday(2026, 11, 6, 1)  # Sunday=6
        self.assertEqual(result, date(2026, 11, 1))

    def test_returns_none_if_not_enough(self):
        result = news_calendar._nth_weekday(2026, 2, 0, 5)  # 5th Monday
        self.assertIsNone(result)


class TestBuildStaticEvents(unittest.TestCase):

    def test_has_nfp_every_month(self):
        events = news_calendar._build_static_events(2026)
        nfps = [e for e in events if e["name"] == "NFP"]
        self.assertEqual(len(nfps), 12)

    def test_nfp_is_high_impact(self):
        events = news_calendar._build_static_events(2026)
        nfps = [e for e in events if e["name"] == "NFP"]
        for e in nfps:
            self.assertEqual(e["impact"], "HIGH")

    def test_has_cpi_every_month(self):
        events = news_calendar._build_static_events(2026)
        cpis = [e for e in events if e["name"] == "CPI"]
        self.assertEqual(len(cpis), 12)

    def test_has_fomc_dates(self):
        events = news_calendar._build_static_events(2026)
        fomcs = [e for e in events if e["name"] == "FOMC"]
        self.assertEqual(len(fomcs), len(config.SMC_FOMC_DATES_2026))

    def test_events_sorted_by_time(self):
        events = news_calendar._build_static_events(2026)
        times = [e["time"] for e in events]
        self.assertEqual(times, sorted(times))

    def test_fomc_at_1900_utc(self):
        events = news_calendar._build_static_events(2026)
        fomcs = [e for e in events if e["name"] == "FOMC"]
        for f in fomcs:
            self.assertEqual(f["time"].hour, 19)
            self.assertEqual(f["time"].minute, 0)


class TestGetMT5Events(unittest.TestCase):

    @patch.object(config, "SMC_NEWS_USE_MT5_CALENDAR", False)
    def test_disabled_returns_empty(self):
        dt = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
        result = news_calendar.get_mt5_events(dt)
        self.assertEqual(result, [])

    @patch.object(config, "SMC_NEWS_USE_MT5_CALENDAR", True)
    @patch("exness_bot.mt5_client.calendar_get")
    def test_mt5_returns_events(self, mock_cal):
        mock_event = MagicMock()
        mock_event.importance = 3
        mock_event.country_id = 840
        mock_event.name = "NFP"
        mock_event.time = 1735992600
        mock_cal.return_value = [mock_event]

        dt = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
        result = news_calendar.get_mt5_events(dt)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "NFP")
        self.assertEqual(result[0]["impact"], "HIGH")

    @patch.object(config, "SMC_NEWS_USE_MT5_CALENDAR", True)
    @patch("exness_bot.mt5_client.calendar_get")
    def test_filters_non_usd(self, mock_cal):
        mock_event = MagicMock()
        mock_event.importance = 3
        mock_event.country_id = 999
        mock_event.name = "ECB Rate"
        mock_event.time = 1735992600
        mock_cal.return_value = [mock_event]

        dt = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
        result = news_calendar.get_mt5_events(dt)
        self.assertEqual(len(result), 0)


class TestGetUpcomingEvents(unittest.TestCase):

    def test_returns_list(self):
        dt = datetime(2026, 6, 5, 13, 10, tzinfo=timezone.utc)
        result = news_calendar.get_upcoming_events(dt)
        self.assertIsInstance(result, list)

    def test_nfp_friday_blackout(self):
        nfp_date = news_calendar._first_friday(2026, 3)
        dt = datetime(nfp_date.year, nfp_date.month, nfp_date.day, 13, 10, tzinfo=timezone.utc)
        result = news_calendar.get_upcoming_events(dt)
        nfp_events = [e for e in result if e["name"] == "NFP"]
        self.assertTrue(len(nfp_events) > 0)
        self.assertTrue(nfp_events[0]["minutes_until"] > 0)

    def test_no_events_on_random_day(self):
        dt = datetime(2026, 3, 4, 3, 0, tzinfo=timezone.utc)
        result = news_calendar.get_upcoming_events(dt)
        self.assertEqual(len(result), 0)

    def test_post_event_cooldown(self):
        nfp_date = news_calendar._first_friday(2026, 4)
        dt = datetime(nfp_date.year, nfp_date.month, nfp_date.day, 13, 35, tzinfo=timezone.utc)
        result = news_calendar.get_upcoming_events(dt)
        nfp_events = [e for e in result if e["name"] == "NFP"]
        if nfp_events:
            self.assertTrue(nfp_events[0]["minutes_until"] < 0)

    def test_naive_datetime_handled(self):
        dt = datetime(2026, 1, 5, 12, 0)
        result = news_calendar.get_upcoming_events(dt)
        self.assertIsInstance(result, list)

    def test_non_datetime_returns_empty(self):
        result = news_calendar.get_upcoming_events("not a datetime")
        self.assertEqual(result, [])


class TestInNewsBlackout(unittest.TestCase):

    def test_returns_tuple(self):
        dt = datetime(2026, 3, 4, 3, 0, tzinfo=timezone.utc)
        result = news_calendar.in_news_blackout(dt)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_no_blackout_off_schedule(self):
        dt = datetime(2026, 3, 4, 3, 0, tzinfo=timezone.utc)
        in_blackout, name = news_calendar.in_news_blackout(dt)
        self.assertFalse(in_blackout)
        self.assertIsNone(name)

    def test_blackout_near_nfp(self):
        nfp_date = news_calendar._first_friday(2026, 5)
        dt = datetime(nfp_date.year, nfp_date.month, nfp_date.day, 13, 15, tzinfo=timezone.utc)
        in_blackout, name = news_calendar.in_news_blackout(dt)
        self.assertTrue(in_blackout)
        self.assertEqual(name, "NFP")


if __name__ == "__main__":
    unittest.main()
