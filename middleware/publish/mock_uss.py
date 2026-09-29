"""Prepare output for InterUSS mock_uss.

Network transport is intentionally deferred until the team selects and starts
the exact mock_uss profile. The functions here create inspectable JSON at the
publisher boundary so that adding HTTP does not change the pipeline.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from middleware.models import TrackPoint


def write_track_points(points: list[TrackPoint], path: str | Path) -> None:
    """Write the normalized middleware output as JSON."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "description": "Normalized middleware output; not UAV-provided identity.",
        "points": [point.to_dict() for point in points],
    }
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


def group_by_track(points: list[TrackPoint]) -> dict[str, list[TrackPoint]]:
    """Group chronologically for a later mock_uss injection payload."""
    grouped: dict[str, list[TrackPoint]] = defaultdict(list)
    for point in points:
        grouped[point.track_id].append(point)
    return {
        track_id: sorted(track_points, key=lambda point: point.time)
        for track_id, track_points in grouped.items()
    }
