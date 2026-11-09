"""Pure safety decisions shared by the API and actuator process."""

import math
from datetime import datetime
from zoneinfo import ZoneInfo


class Refused(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def moisture(raw, profile):
    dry, wet = profile.get("dry_raw"), profile.get("wet_raw")
    if dry is None or wet is None or dry == wet:
        return None
    return round(max(0, min(100, (raw - dry) / (wet - dry) * 100)), 1)


def day_start(now, timezone):
    return (
        datetime.fromtimestamp(now, ZoneInfo(timezone))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )


def validate_profile(p, settings):
    numeric = ["flow_ml_min", "dry_threshold", "wet_cutoff", "dose_ml", "daily_limit_ml"]
    if any(not math.isfinite(float(p[k])) for k in numeric):
        raise Refused("invalid_profile")
    if not 0 <= p["dry_threshold"] < p["wet_cutoff"] <= 100:
        raise Refused("invalid_thresholds")
    if not 0 < p["flow_ml_min"] <= 1000:
        raise Refused("invalid_flow")
    if not 0 < p["dose_ml"] <= settings.max_event_ml:
        raise Refused("volume_limit")
    if not p["dose_ml"] <= p["daily_limit_ml"] <= settings.max_daily_ml:
        raise Refused("daily_limit")
    if not 60 <= p["minimum_interval_seconds"] <= 86400:
        raise Refused("invalid_interval")
    if not 0 <= p["start_hour"] < p["end_hour"] <= 24:
        raise Refused("invalid_schedule")
    dry, wet = p.get("dry_raw"), p.get("wet_raw")
    if p["calibration_confirmed"] and (dry is None or wet is None or abs(dry - wet) < 50):
        raise Refused("invalid_calibration")
    if any(v is not None and (not math.isfinite(v) or not 0 <= v <= 3300) for v in (dry, wet)):
        raise Refused("invalid_calibration")
    if p["automatic"] and not (p["calibration_confirmed"] and p["flow_confirmed"]):
        raise Refused("calibration_required")


def check_safety(
    state, profile, reading, volume, settings, now, used_ml, last_at=None, source="manual"
):
    if state["estop"]:
        raise Refused("emergency_stop")
    if state["fault"]:
        raise Refused(state["fault"])
    if not state["armed"]:
        raise Refused("disarmed")
    if now - state["heartbeat"] > settings.stale_seconds:
        raise Refused("controller_offline")
    if not profile["calibration_confirmed"] or not profile["flow_confirmed"]:
        raise Refused("calibration_required")
    if not math.isfinite(volume) or not 0 < volume <= min(
        profile["dose_ml"], settings.max_event_ml
    ):
        raise Refused("volume_limit")
    if volume / profile["flow_ml_min"] * 60 > settings.max_runtime_seconds:
        raise Refused("runtime_limit")
    if not reading or now - reading["recorded_at"] > settings.stale_seconds:
        raise Refused("sensor_stale")
    if not reading["tank_ok"]:
        raise Refused("tank_empty")
    if reading["leak"]:
        raise Refused("leak_detected")
    if moisture(reading["raw"], profile) >= profile["wet_cutoff"]:
        raise Refused("soil_too_wet")
    if used_ml + volume > min(profile["daily_limit_ml"], settings.max_daily_ml):
        raise Refused("daily_limit")
    if last_at is not None and now - last_at < profile["minimum_interval_seconds"]:
        raise Refused("minimum_interval")
    if source == "automatic":
        hour = datetime.fromtimestamp(now, ZoneInfo(settings.timezone)).hour
        if not profile["automatic"] or not profile["start_hour"] <= hour < profile["end_hour"]:
            raise Refused("outside_schedule")
