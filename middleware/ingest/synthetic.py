"""Load the two synthetic JSON shapes used during development."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from middleware.models import Detection, GeoPoint, TrackPoint, parse_utc


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


def load_detection_frames(path: str | Path) -> list[DetectionFrame]:
    """Load HermesPy-like local point-cloud frames."""
    document = _read_json(path)
    sensor_id = document.get("sensor", {}).get("id", "unknown")
    frames: list[DetectionFrame] = []
    for raw_frame in document.get("frames", []):
        time = parse_utc(raw_frame["time"])
        detections = [
            Detection(
                time=time,
                position_m=tuple(float(v) for v in item["position_m"]),
                velocity_mps=tuple(float(v) for v in item["velocity_mps"]),
                power=float(item["power"]),
                sensor_id=sensor_id,
            )
            for item in raw_frame.get("detections", [])
        ]
        frames.append(DetectionFrame(raw_frame["time"], detections))
    if not frames:
        raise ValueError(f"{path} contains no detection frames")
    return frames


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
