from __future__ import annotations

import pytz
import frappe
from frappe.utils import get_datetime, now_datetime, get_system_timezone

from press.press.doctype.site_activity.site_activity import log_site_activity

_DAY_FIELDS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def run_site_schedules():
    schedules = frappe.get_all(
        "Site Schedule",
        filters={"enabled": 1},
        fields=["name", "site", "preset", "override", "override_until"],
    )
    for schedule in schedules:
        try:
            _process_schedule(schedule)
        except Exception:
            frappe.log_error(f"Site Schedule failed for {schedule.site}")


def _process_schedule(schedule):
    site = frappe.db.get_value(
        "Site", schedule.site, ["server", "status"], as_dict=True
    )
    if not site or site.status == "Archived":
        return

    server = frappe.db.get_value(
        "Server", site.server, ["environment", "status"], as_dict=True
    )
    if not server or server.environment not in ("Development", "Demo"):
        return

    tz = pytz.timezone(get_system_timezone())
    local_now = pytz.utc.localize(now_datetime()).astimezone(tz)

    def on_override_clear():
        frappe.db.set_value(
            "Site Schedule",
            schedule.name,
            {"override": "None", "override_until": None},
        )
        frappe.db.commit()

    desired_up = _should_be_up(schedule, local_now, on_override_clear)
    actual_up = server.status == "Active"

    if desired_up and not actual_up:
        frappe.get_doc("Server", site.server).start_instance()
        log_site_activity(schedule.site, "Schedule Start")
    elif not desired_up and actual_up:
        frappe.get_doc("Server", site.server).stop_instance()
        log_site_activity(schedule.site, "Schedule Stop")


def _should_be_up(schedule, local_now, on_override_clear):
    """
    Pure(-ish) function: given a schedule and the local current datetime,
    return True if the site instance should be running.

    on_override_clear is called (with no args) when an expired Until Datetime
    override is detected and should be cleared.
    """
    if schedule.override == "Indefinite":
        return True

    if schedule.override == "Until Datetime" and schedule.override_until:
        override_dt = pytz.utc.localize(get_datetime(schedule.override_until))
        if local_now < override_dt:
            return True
        on_override_clear()
        # Fall through to preset evaluation after clearing

    preset = _get_preset(schedule.preset)
    if not preset:
        return True  # No preset found; leave instance running

    day_index = local_now.weekday()  # 0=Monday, 6=Sunday
    if not getattr(preset, _DAY_FIELDS[day_index], False):
        return False

    if preset.all_day:
        return True

    if not preset.start_time or not preset.stop_time:
        return True

    current = local_now.time().replace(second=0, microsecond=0)
    start = _parse_time(preset.start_time)
    stop = _parse_time(preset.stop_time)
    return start <= current <= stop


def _get_preset(preset_name):
    return frappe.db.get_value(
        "Site Schedule Preset",
        preset_name,
        _DAY_FIELDS + ["all_day", "start_time", "stop_time"],
        as_dict=True,
    )


def _parse_time(t):
    """Convert a Frappe time value (string 'HH:MM:SS' or datetime.time) to datetime.time."""
    from datetime import time as dtime
    if isinstance(t, dtime):
        return t.replace(second=0, microsecond=0)
    h, m, *_ = str(t).split(":")
    return dtime(int(h), int(m))
