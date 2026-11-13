"""Load the two synthetic JSON shapes used during development."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from middleware.models import Detection, GeoPoint, SourceMeta, TrackPoint, parse_utc
from middleware.uncertainty.estimate import range_resolution_m

logger = logging.getLogger("middleware.ingest")


@dataclass(frozen=True)
class DetectionFrame:
    time: str
    detections: list[Detection]


def _read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return document


def skip_reading(issues: list[str] | None, message: str) -> None:
    """Log one skipped reading and remember it for the caller."""
    logger.warning("Skipped reading: %s", message)
    if issues is not None:
        issues.append(message)


def read_number(item: dict[str, Any], name: str) -> float:
    """Return a finite number from ``item[name]`` or raise ValueError."""
    if name not in item:
        raise ValueError(f"missing field {name!r}")
    value = item[name]
    if value is None:
        raise ValueError(f"field {name!r} is null")
    if isinstance(value, bool):
        raise ValueError(f"field {name!r} is not a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"field {name!r} is not a number: {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"field {name!r} is not finite: {value!r}")
    return number


def read_vector(item: dict[str, Any], name: str) -> tuple[float, float, float]:
    """Return an x, y, z tuple from ``item[name]`` or raise ValueError."""
    if name not in item:
        raise ValueError(f"missing field {name!r}")
    value = item[name]
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"field {name!r} must be a list of three numbers")
    return tuple(read_number({name: v}, name) for v in value)


def read_power(item: dict[str, Any]) -> float:
    """Return a positive power or raise ValueError."""
    power = read_number(item, "power")
    if power <= 0:
        raise ValueError(f"power must be positive, got {power!r}")
    return power


def read_frame_time(raw_frame: Any, index: int, issues: list[str] | None):
    """Return the frame's UTC time, or None after logging why it was skipped."""
    try:
        if not isinstance(raw_frame, dict):
            raise ValueError("frame is not an object")
        if not isinstance(raw_frame.get("time"), str):
            raise ValueError("missing or non-text field 'time'")
        if not isinstance(raw_frame.get("detections", []), list):
            raise ValueError("field 'detections' is not a list")
        return parse_utc(raw_frame["time"])
    except ValueError as error:
        skip_reading(issues, f"frame {index}: whole frame skipped, {error}")
        return None


def _optional_positive(sensor: dict[str, Any], name: str, issues: list[str] | None):
    """Return a positive number from the sensor block, or None (logged if bad)."""
    if sensor.get(name) is None:
        return None
    try:
        value = read_number(sensor, name)
        if value <= 0:
            raise ValueError(f"field {name!r} must be positive, got {value!r}")
        return value
    except ValueError as error:
        skip_reading(issues, f"sensor metadata ignored, {error}")
        return None


def _optional_text(sensor: dict[str, Any], name: str) -> str | None:
    value = sensor.get(name)
    return value if isinstance(value, str) and value else None


def read_source_meta(
    sensor: Any,
    issues: list[str] | None = None,
    *,
    default_position_m: tuple[float, float, float] | None = None,
) -> SourceMeta:
    """Build SourceMeta from a file's ``sensor`` block.

    Missing or invalid optional fields become None and are logged. The sensor
    position comes from ``sensor["position_m"]`` when valid. Otherwise
    ``default_position_m`` is used and ``sensor_position_assumed`` is True.
    """
    if not isinstance(sensor, dict):
        sensor = {}
    bandwidth_hz = _optional_positive(sensor, "bandwidth_hz", issues)
    resolution = (
        range_resolution_m(bandwidth_hz)
        if bandwidth_hz is not None
        else _optional_positive(sensor, "range_resolution_m", issues)
    )
    position = None
    assumed = False
    if sensor.get("position_m") is not None:
        try:
            position = read_vector(sensor, "position_m")
        except ValueError as error:
            skip_reading(issues, f"sensor metadata ignored, {error}")
    if position is None and default_position_m is not None:
        position = tuple(default_position_m)
        assumed = True
    sensor_id = sensor.get("id")
    return SourceMeta(
        sensor_id=sensor_id if isinstance(sensor_id, str) and sensor_id else "unknown",
        sensor_type=_optional_text(sensor, "type"),
        signal_type=_optional_text(sensor, "signal_type"),
        carrier_frequency_hz=_optional_positive(sensor, "carrier_frequency_hz", issues),
        bandwidth_hz=bandwidth_hz,
        range_resolution_m=resolution,
        sensor_position_m=position,
        sensor_position_assumed=assumed,
    )


def load_detection_frames(
    path: str | Path, *, issues: list[str] | None = None
) -> list[DetectionFrame]:
    """Load HermesPy-like local point-cloud frames.

    A reading with a missing, null, wrongly shaped or non-positive field is
    skipped and logged. Pass a list as ``issues`` to collect the messages.
    """
    document = _read_json(path)
    source_meta = read_source_meta(document.get("sensor"), issues)
    sensor_id = source_meta.sensor_id
    frames: list[DetectionFrame] = []
    for frame_index, raw_frame in enumerate(document.get("frames", [])):
        time = read_frame_time(raw_frame, frame_index, issues)
        if time is None:
            continue
        detections = []
        for item_index, item in enumerate(raw_frame.get("detections", [])):
            try:
                if not isinstance(item, dict):
                    raise ValueError("reading is not an object")
                detections.append(
                    Detection(
                        time=time,
                        position_m=read_vector(item, "position_m"),
                        velocity_mps=read_vector(item, "velocity_mps"),
                        power=read_power(item),
                        sensor_id=sensor_id,
                        source_meta=source_meta,
                    )
                )
            except ValueError as error:
                skip_reading(issues, f"frame {frame_index} reading {item_index}: {error}")
        frames.append(DetectionFrame(raw_frame["time"], detections))
    if not frames:
        raise ValueError(f"{path} contains no detection frames")
    return frames


def _geocoded_meta(raw: Any) -> SourceMeta | None:
    """Rebuild SourceMeta from a normalized output point, or None if absent."""
    if not isinstance(raw, dict):
        return None

    def number(name):
        value = raw.get(name)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def text(name):
        value = raw.get(name)
        return value if isinstance(value, str) and value else None

    position = raw.get("sensor_position_m")
    try:
        position = tuple(float(v) for v in position) if position is not None else None
        if position is not None and len(position) != 3:
            position = None
    except (TypeError, ValueError):
        position = None
    geo = None
    wgs = raw.get("sensor_position_wgs84")
    if isinstance(wgs, dict):
        try:
            geo = GeoPoint(float(wgs["lat"]), float(wgs["lng"]), float(wgs["alt_m"]))
        except (KeyError, TypeError, ValueError):
            geo = None
    return SourceMeta(
        sensor_id=text("sensor_id") or "unknown",
        sensor_type=text("sensor_type"),
        signal_type=text("signal_type"),
        carrier_frequency_hz=number("carrier_frequency_hz"),
        bandwidth_hz=number("bandwidth_hz"),
        range_resolution_m=number("range_resolution_m"),
        sensor_position_m=position,
        sensor_position_assumed=raw.get("sensor_position_assumed") is True,
        sensor_position_wgs84=geo,
    )


def load_track_points(path: str | Path) -> list[TrackPoint]:
    """Load already-geocoded points, bypassing geocode and association."""
    document = _read_json(path)
    points = []
    for item in document.get("points", []):
        points.append(
            TrackPoint(
                track_id=str(item["track_id"]),
                time=parse_utc(item["time"]),
                position=GeoPoint(
                    float(item["lat"]), float(item["lng"]), float(item["alt"])
                ),
                speed_mps=float(item.get("speed_mps", 0)),
                heading_deg=(
                    float(item["heading_deg"])
                    if item.get("heading_deg") is not None
                    else None
                ),
                vertical_speed_mps=float(item.get("vertical_speed_mps", 0)),
                uncertainty_m=float(item.get("uncertainty_m", 100)),
                source=str(item.get("source", "synthetic")),
                source_meta=_geocoded_meta(item.get("source_meta")),
            )
        )
    if not points:
        raise ValueError(f"{path} contains no geocoded track points")
    return points


def load_origin(path: str | Path) -> GeoPoint:
    """Load the WGS84 scene origin used for local coordinates."""
    origin = _read_json(path)["origin"]
    return GeoPoint(
        lat=float(origin["lat"]),
        lng=float(origin["lng"]),
        alt_m=float(origin["alt_m"]),
    )
