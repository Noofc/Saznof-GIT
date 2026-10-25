import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore
    ZoneInfoNotFoundError = Exception  # type: ignore

try:
    import pytz
except ImportError:  # pragma: no cover
    pytz = None  # type: ignore

DEFAULT_RECEIPT_TIMEZONE = "America/Sao_Paulo"
FIXED_BRASILIA_TZ = timezone(timedelta(hours=-3), DEFAULT_RECEIPT_TIMEZONE)


def _load_zoneinfo(timezone_name: str):
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return None


def _load_pytz_timezone(timezone_name: str):
    if pytz is None:
        return None
    try:
        return pytz.timezone(timezone_name)
    except Exception:
        return None


def _get_timezone(timezone_name: str):
    tz = _load_zoneinfo(timezone_name)
    if tz is not None:
        return tz
    tz = _load_pytz_timezone(timezone_name)
    if tz is not None:
        return tz
    if ZoneInfo is not None:
        try:
            return ZoneInfo(DEFAULT_RECEIPT_TIMEZONE)
        except Exception:
            pass
    if pytz is not None:
        return pytz.timezone(DEFAULT_RECEIPT_TIMEZONE)
    return FIXED_BRASILIA_TZ


BRASILIA_TZ = _get_timezone(DEFAULT_RECEIPT_TIMEZONE)


def brasilia_now() -> datetime:
    return datetime.now(BRASILIA_TZ)


def brasilia_timestamp() -> int:
    return int(brasilia_now().timestamp())


def _extract_timezone_from_config(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None

    timezone_keys = ["timezone", "time_zone", "timeZone"]
    for key in timezone_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    bot_section = data.get("bot") if isinstance(data.get("bot"), dict) else None
    if bot_section:
        for key in timezone_keys:
            value = bot_section.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def load_config_timezone(base_dir: Optional[str] = None) -> str:
    candidates = []
    if base_dir:
        candidates.append(os.path.join(base_dir, "config.json"))
    candidates.append(os.path.join(os.getcwd(), "config.json"))

    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8-sig") as f:
                config_data = json.load(f)
            timezone_value = _extract_timezone_from_config(config_data)
            if timezone_value:
                return timezone_value
        except Exception:
            continue

    return DEFAULT_RECEIPT_TIMEZONE


def load_receipt_time_offset_minutes(base_dir: Optional[str] = None) -> int:
    candidates = []
    if base_dir:
        candidates.append(os.path.join(base_dir, "config.json"))
    candidates.append(os.path.join(os.getcwd(), "config.json"))

    offset_keys = ("receiptTimeOffsetMinutes", "receipt_time_offset_minutes", "receipt_time_offset")

    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8-sig") as f:
                config_data = json.load(f)

            values = []
            if isinstance(config_data, dict):
                values.extend(config_data.get(key) for key in offset_keys)
                bot_section = config_data.get("bot")
                if isinstance(bot_section, dict):
                    values.extend(bot_section.get(key) for key in offset_keys)

            for value in values:
                if value in (None, ""):
                    continue
                return int(float(value))
        except Exception:
            continue

    return 0


def normalize_timezone(timezone_name: Optional[str] = None, base_dir: Optional[str] = None):
    candidate = timezone_name or load_config_timezone(base_dir)
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = DEFAULT_RECEIPT_TIMEZONE

    tz = _get_timezone(candidate.strip())
    if tz is None:
        return BRASILIA_TZ
    return tz


def receipt_now(timezone_name: Optional[str] = None, base_dir: Optional[str] = None) -> datetime:
    tz = normalize_timezone(timezone_name, base_dir)
    return datetime.now(tz)


def format_receipt_timestamp(timestamp: datetime, timezone_name: Optional[str] = None, base_dir: Optional[str] = None) -> Dict[str, str]:
    tz = normalize_timezone(timezone_name, base_dir)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(tz)

    offset = timestamp.utcoffset() or timedelta(0)
    offset_hours = int(offset.total_seconds() // 3600)
    offset_minutes = int((abs(offset.total_seconds()) % 3600) // 60)
    offset_sign = "+" if offset_hours >= 0 else "-"
    gmt_label = f"GMT{offset_sign}{abs(offset_hours)}"
    if offset_minutes:
        gmt_label += f":{offset_minutes:02d}"

    zone_name = getattr(tz, "key", None) or str(tz) or DEFAULT_RECEIPT_TIMEZONE

    return {
        "date": timestamp.strftime("%d/%m/%Y"),
        "time": timestamp.strftime("%H:%M:%S"),
        "datetime": timestamp.strftime("%d/%m/%Y %H:%M:%S"),
        "timezone_label": f"{gmt_label} ({zone_name})",
        "timezone_name": zone_name,
    }
