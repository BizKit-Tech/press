import unittest
from datetime import datetime, time
from unittest.mock import MagicMock, patch

import pytz


class TestShouldBeUp(unittest.TestCase):
    """Tests for _should_be_up — pure logic, no DB needed."""

    def _make_schedule(self, override="None", override_until=None):
        s = MagicMock()
        s.name = "SCHED-001"
        s.override = override
        s.override_until = override_until
        return s

    def _make_preset(self, all_day=False, start="08:00:00", stop="18:00:00",
                     weekdays_only=True):
        p = MagicMock()
        p.monday = p.tuesday = p.wednesday = p.thursday = p.friday = 1 if weekdays_only else 1
        p.saturday = p.sunday = 0 if weekdays_only else 1
        p.all_day = all_day
        p.start_time = start
        p.stop_time = stop
        return p

    def _local_dt(self, weekday_offset, hour, minute=0):
        """Return a Monday + weekday_offset datetime at the given hour."""
        # 2026-06-22 is a Monday
        base = datetime(2026, 6, 22 + weekday_offset, hour, minute)
        return pytz.utc.localize(base)

    def test_indefinite_override_always_up(self):
        from press.press.doctype.site.site_schedule import _should_be_up
        schedule = self._make_schedule(override="Indefinite")
        result = _should_be_up(schedule, self._local_dt(0, 2), lambda: None)
        self.assertTrue(result)

    def test_until_datetime_override_up_before_expiry(self):
        from press.press.doctype.site.site_schedule import _should_be_up
        schedule = self._make_schedule(
            override="Until Datetime",
            override_until="2099-12-31 23:59:59"
        )
        result = _should_be_up(schedule, self._local_dt(0, 2), lambda: None)
        self.assertTrue(result)

    def test_until_datetime_override_clears_when_expired(self):
        from press.press.doctype.site.site_schedule import _should_be_up
        cleared = []
        schedule = self._make_schedule(
            override="Until Datetime",
            override_until="2020-01-01 00:00:00"
        )

        def on_clear():
            cleared.append(True)

        with patch("press.press.doctype.site.site_schedule._get_preset") as mock_preset:
            mock_preset.return_value = self._make_preset(all_day=True)
            # Monday 10am — within Business Hours after override clears
            local_now = self._local_dt(0, 10)
            result = _should_be_up(schedule, local_now, on_clear)
        self.assertTrue(len(cleared) == 1, "Override clear callback was not called")

    def test_preset_weekday_within_hours_is_up(self):
        from press.press.doctype.site.site_schedule import _should_be_up
        schedule = self._make_schedule()
        with patch("press.press.doctype.site.site_schedule._get_preset") as mock_preset:
            mock_preset.return_value = self._make_preset()
            result = _should_be_up(schedule, self._local_dt(0, 10), lambda: None)
        self.assertTrue(result)

    def test_preset_weekday_outside_hours_is_down(self):
        from press.press.doctype.site.site_schedule import _should_be_up
        schedule = self._make_schedule()
        with patch("press.press.doctype.site.site_schedule._get_preset") as mock_preset:
            mock_preset.return_value = self._make_preset()
            result = _should_be_up(schedule, self._local_dt(0, 1), lambda: None)  # 1am
        self.assertFalse(result)

    def test_preset_weekend_is_down(self):
        from press.press.doctype.site.site_schedule import _should_be_up
        schedule = self._make_schedule()
        with patch("press.press.doctype.site.site_schedule._get_preset") as mock_preset:
            mock_preset.return_value = self._make_preset(weekdays_only=True)
            result = _should_be_up(schedule, self._local_dt(5, 10), lambda: None)  # Saturday
        self.assertFalse(result)

    def test_all_day_preset_active_day_is_up(self):
        from press.press.doctype.site.site_schedule import _should_be_up
        schedule = self._make_schedule()
        with patch("press.press.doctype.site.site_schedule._get_preset") as mock_preset:
            mock_preset.return_value = self._make_preset(all_day=True)
            result = _should_be_up(schedule, self._local_dt(0, 3), lambda: None)  # 3am Monday
        self.assertTrue(result)
