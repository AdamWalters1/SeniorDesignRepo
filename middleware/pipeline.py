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


def _say(enabled: bool, message: str) -> None:
    if enabled:
        print(message)


def process_local_detections(
    input_path: str | Path,
    origin_path: str | Path,
    *,
    max_tracks: int = 3,
    gate_m: float = 25.0,
    loader=load_detection_frames,
    announce: bool = False,
) -> list[TrackPoint]:
    """Convert local point-cloud frames into normalized geospatial tracks."""
    frames = loader(input_path)
    if loader is load_radar_detection_frames:
        _say(
            announce,
            f"Read radar range and power from {len(frames)} frames. "
            "Each range is placed straight north.",
        )
    else:
        _say(announce, f"Read {len(frames)} local detection frames.")
    origin = load_origin(origin_path)
    tracker = NearestNeighborTracker(max_tracks=max_tracks, gate_m=gate_m)
    output: list[TrackPoint] = []
    kept_radar_uncertainty = False
    estimated_from_power = False

    for frame in frames:
        for track_id, detection in tracker.update(frame.detections):
            east, north, up = detection.velocity_mps
            if detection.uncertainty_m is not None:
                uncertainty_m = detection.uncertainty_m
                kept_radar_uncertainty = True
            else:
                uncertainty_m = estimate_uncertainty_m(detection.power)
                estimated_from_power = True
            output.append(
                TrackPoint(
                    track_id=track_id,
                    time=detection.time,
                    position=local_to_wgs84(detection.position_m, origin),
                    speed_mps=round(horizontal_speed(detection.velocity_mps), 2),
                    heading_deg=_heading_deg(east, north),
                    vertical_speed_mps=round(up, 2),
                    uncertainty_m=uncertainty_m,
                    source="hermespy-like",
                )
            )
    track_ids = ", ".join(sorted({point.track_id for point in output})) or "none"
    _say(announce, f"Associated tracks: {track_ids}.")
    _say(
        announce,
        f"Converted {len(output)} points to WGS84 from origin "
        f"{origin.lat}, {origin.lng}.",
    )
    if kept_radar_uncertainty:
        _say(announce, "Kept the radar range uncertainty on each point.")
    if estimated_from_power:
        _say(announce, "Estimated position uncertainty from detection power.")
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
            announce=True,
        )
    else:
        points = load_track_points(args.input)
        print(f"Loaded {len(points)} points that are already WGS84.")

    print(f"Writing {len(points)} points to {args.output}.")
    write_track_points(points, args.output)
    if args.publish:
        print(
            f"Preparing to push to mock_uss. "
            f"The first sample will start {args.lead_seconds:g} s ahead."
        )
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
