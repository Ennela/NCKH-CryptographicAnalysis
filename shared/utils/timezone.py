from datetime import datetime, timezone
from typing import Union

def now_utc() -> datetime:
    """Returns current datetime object localized to UTC timezone."""
    return datetime.now(timezone.utc)

def to_utc(dt: datetime) -> datetime:
    """
    Enforces UTC on a datetime object.
    If naive, localizes to UTC. If aware, converts to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def format_iso(dt: datetime) -> str:
    """Formats datetime to standard ISO 8601 with Z indicator."""
    return to_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(iso_str: str) -> datetime:
    """Parses standard ISO 8601 string to a UTC datetime object."""
    # Handle 'Z' ending replace with +00:00
    cleaned = iso_str.replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)
