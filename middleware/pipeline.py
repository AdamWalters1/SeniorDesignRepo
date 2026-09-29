"""Run ingest → geocode → associate → uncertainty → publisher boundary."""

from __future__ import annotations

import argparse
from math import atan2, degrees
from pathlib import Path

from middleware.associate.tracker import NearestNeighborTracker
from middleware.geocode.wgs84 import local_to_wgs84
from middleware.ingest.synthetic import (
    load_detection_frames,
    load_origin,
    load_track_points,
)
from middleware.models import TrackPoint, horizontal_speed
from middleware.publish.mock_uss import write_track_points
from middleware.uncertainty.estimate import estimate_uncertainty_m


def _heading_deg(east_mps: float, north_mps: float) -> float | None:
    if east_mps == 0 and north_mps == 0:
        return None
    return round(degrees(atan2(east_mps, north_mps)) % 360, 2)


def process_local_detections(
    input_path: str | Path,
    origin_path: str | Path,
    *,
    max_tracks: int = 3,
    gate_m: float = 25.0,
) -> list[TrackPoint]:
    """Convert local point-cloud frames into normalized geospatial tracks."""
    frames = load_detection_frames(input_path)
    origin = load_origin(origin_path)
    tracker = NearestNeighborTracker(max_tracks=max_tracks, gate_m=gate_m)
    output: list[TrackPoint] = []

    for frame in frames:
        for track_id, detection in tracker.update(frame.detections):
            east, north, up = detection.velocity_mps
            output.append(
                TrackPoint(
                    track_id=track_id,
                    time=detection.time,
                    position=local_to_wgs84(detection.position_m, origin),
                    speed_mps=round(horizontal_speed(detection.velocity_mps), 2),
                    heading_deg=_heading_deg(east, north),
                    vertical_speed_mps=round(up, 2),
                    uncertainty_m=estimate_uncertainty_m(detection.power),
                    source="hermespy-like",
                )
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Synthetic JSON input")
    parser.add_argument(
        "--format",
        choices=("local", "geocoded"),
        default="local",
        help="Input shape (default: local HermesPy-like frames)",
    )
    parser.add_argument("--origin", help="Scene-origin JSON; required for local input")
    parser.add_argument(
        "--output",
        default="build/normalized_tracks.json",
        help="Normalized output JSON path",
    )
    parser.add_argument("--max-tracks", type=int, default=3)
    parser.add_argument("--gate-m", type=float, default=25.0)
    args = parser.parse_args()

    if args.format == "local":
        if not args.origin:
            parser.error("--origin is required for local input")
        points = process_local_detections(
            args.input,
            args.origin,
            max_tracks=args.max_tracks,
            gate_m=args.gate_m,
        )
    else:
        points = load_track_points(args.input)

    write_track_points(points, args.output)
    print(f"Wrote {len(points)} points to {args.output}")


if __name__ == "__main__":
    main()
