"""Read the middleware's normalized JSON and group it into tracks.

This only reads build/normalized_tracks.json. It never writes to it and
never changes middleware behaviour.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from middleware.ingest.synthetic import load_origin
from middleware.models import format_utc, parse_utc


def _optional_number(raw: dict[str, Any], name: str) -> float | None:
    """Return a finite number, or None if the field is missing or invalid."""
    try:
        value = float(raw[name])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _clean_point(raw: Any) -> dict[str, Any] | None:
    """Validate one point. Return None if it cannot be placed on the map."""
    if not isinstance(raw, dict):
        return None
    try:
        track_id = str(raw["track_id"])
        time = parse_utc(str(raw["time"]))
        lat = float(raw["lat"])
        lng = float(raw["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return {
        "track_id": track_id,
        "time": format_utc(time),
        "lat": lat,
        "lng": lng,
        "alt": _optional_number(raw, "alt"),
        "speed_mps": _optional_number(raw, "speed_mps"),
        "heading_deg": _optional_number(raw, "heading_deg"),
        "vertical_speed_mps": _optional_number(raw, "vertical_speed_mps"),
        "uncertainty_m": _optional_number(raw, "uncertainty_m"),
        "source": raw.get("source"),
    }


def load_tracks_file(tracks_path: Path, origin_path: Path) -> dict[str, Any]:
    """Return the dashboard's track document built from the JSON file."""
    with tracks_path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    raw_points = document.get("points")
    if not isinstance(raw_points, list):
        raise ValueError("File has no 'points' list")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped = 0
    for raw in raw_points:
        point = _clean_point(raw)
        if point is None:
            skipped += 1
        else:
            grouped[point["track_id"]].append(point)

    tracks = [
        {
            "track_id": track_id,
            "points": sorted(points, key=lambda p: parse_utc(p["time"])),
        }
        for track_id, points in sorted(grouped.items())
    ]
    origin = load_origin(origin_path)
    return {
        "source": "file",
        "file": tracks_path.name,
        "origin": {"lat": origin.lat, "lng": origin.lng, "alt_m": origin.alt_m},
        "tracks": tracks,
        "skipped_points": skipped,
    }