"""Run ingest → geocode → associate → uncertainty → publisher boundary."""

from __future__ import annotations

import argparse
from math import atan2, degrees
from pathlib import Path
from uuid import uuid4

from middleware.associate.tracker import NearestNeighborTracker
from middleware.geocode.wgs84 import local_to_wgs84
from middleware.ingest.sionna import load_radar_detection_frames
from middleware.ingest.synthetic import (
    load_detection_frames,
    load_origin,
    load_track_points,
)
from middleware.models import TrackPoint, horizontal_speed
from middleware.publish.mock_uss import publish_tracks, write_track_points
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
    loader=load_detection_frames,
) -> list[TrackPoint]:
    """Convert local point-cloud frames into normalized geospatial tracks."""
    frames = loader(input_path)
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
                    uncertainty_m=(
                        detection.uncertainty_m
                        if detection.uncertainty_m is not None
                        else estimate_uncertainty_m(detection.power)
                    ),
                    source="hermespy-like",
                )
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Synthetic JSON input")
    parser.add_argument(
        "--format",
        choices=("local", "geocoded", "radar"),
        default="local",
        help="Input shape: local frames, geocoded points, or raw radar range/power",
    )
    parser.add_argument("--origin", help="Scene-origin JSON; required for local input")
    parser.add_argument(
        "--output",
        default="build/normalized_tracks.json",
        help="Normalized output JSON path",
    )
    parser.add_argument("--max-tracks", type=int, default=3)
    parser.add_argument("--gate-m", type=float, default=25.0)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="PUT the tracks to the local mock_uss after writing JSON",
    )
    parser.add_argument("--mock-uss-url", default="http://localhost:8081")
    parser.add_argument("--oauth-url", default="http://localhost:8085")
    parser.add_argument(
        "--test-id",
        default="",
        help="Injection test id. A new id is used when this is omitted.",
    )
    parser.add_argument(
        "--lead-seconds",
        type=float,
        default=120,
        help="How far in the future the first published sample starts",
    )
    args = parser.parse_args()

    if args.format in ("local", "radar"):
        if not args.origin:
            parser.error("--origin is required for local and radar input")
        points = process_local_detections(
            args.input,
            args.origin,
            max_tracks=args.max_tracks,
            gate_m=args.gate_m,
            loader=(
                load_radar_detection_frames
                if args.format == "radar"
                else load_detection_frames
            ),
        )
    else:
        points = load_track_points(args.input)

    write_track_points(points, args.output)
    print(f"Wrote {len(points)} points to {args.output}")
    if args.publish:
        test_id = args.test_id or f"pipeline-{uuid4().hex[:8]}"
        result = publish_tracks(
            points,
            mock_uss_url=args.mock_uss_url,
            oauth_url=args.oauth_url,
            test_id=test_id,
            lead_s=args.lead_seconds,
        )
        print(f"Published test {test_id} ({len(result.get('injected_flights', []))} flights)")


if __name__ == "__main__":
    main()
