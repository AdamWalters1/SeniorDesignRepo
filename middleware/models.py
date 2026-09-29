"""Shared, dependency-free data models for the middleware."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import hypot
from typing import Any


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and require timezone information."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    """Format a timestamp as ISO-8601 UTC."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Detection:
    """One unassociated sensing sample in a local Cartesian frame."""

    time: datetime
    position_m: tuple[float, float, float]
    velocity_mps: tuple[float, float, float]
    power: float
    sensor_id: str = "unknown"

    def __post_init__(self) -> None:
        if len(self.position_m) != 3 or len(self.velocity_mps) != 3:
            raise ValueError("Position and velocity must each contain x, y, and z")
        if self.power <= 0:
            raise ValueError("Detection power must be positive")


@dataclass(frozen=True)
class GeoPoint:
    """A WGS84 position."""

    lat: float
    lng: float
    alt_m: float

    def __post_init__(self) -> None:
        if not -90 <= self.lat <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if not -180 <= self.lng <= 180:
            raise ValueError("Longitude must be between -180 and 180")


@dataclass(frozen=True)
class TrackPoint:
    """One timestamped point in a middleware-owned track."""

    track_id: str
    time: datetime
    position: GeoPoint
    speed_mps: float
    heading_deg: float | None
    vertical_speed_mps: float
    uncertainty_m: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["time"] = format_utc(self.time)
        result["lat"] = result.pop("position")["lat"]
        result["lng"] = self.position.lng
        result["alt"] = self.position.alt_m
        return result


def horizontal_speed(velocity_mps: tuple[float, float, float]) -> float:
    """Return horizontal speed for axes x=east and y=north."""
    return hypot(velocity_mps[0], velocity_mps[1])
