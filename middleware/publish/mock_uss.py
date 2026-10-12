"""Publish normalized tracks to the local InterUSS mock Service Provider.

The DSS rejects an airspace area that starts in the past, and it also rejects
an area with no width or height. Sample files use old timestamps and a
single-radar track may only move north, so this module shifts time forward
and, when needed, adds one extra point so the advertised area is a real box.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from middleware.models import GeoPoint, TrackPoint, format_utc

MIN_SPAN_DEG = 0.0001


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
    """Group chronologically for one injection flight per track."""
    grouped: dict[str, list[TrackPoint]] = defaultdict(list)
    for point in points:
        grouped[point.track_id].append(point)
    return {
        track_id: sorted(track_points, key=lambda point: point.time)
        for track_id, track_points in grouped.items()
    }


def shift_to_future(
    points: list[TrackPoint],
    *,
    lead_s: float = 120,
    now: datetime | None = None,
) -> list[TrackPoint]:
    """Keep the spacing between samples, but start the set in the future."""
    if not points:
        return []
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    delta = (current + timedelta(seconds=lead_s)) - min(point.time for point in points)
    return [
        TrackPoint(
            track_id=point.track_id,
            time=point.time + delta,
            position=point.position,
            speed_mps=point.speed_mps,
            heading_deg=point.heading_deg,
            vertical_speed_mps=point.vertical_speed_mps,
            uncertainty_m=point.uncertainty_m,
            source=point.source,
        )
        for point in points
    ]


def _with_area(points: list[TrackPoint]) -> list[TrackPoint]:
    """Ensure a flight spans both latitude and longitude.

    mock_uss turns the positions into a polygon. A single point, or a track
    that only changes latitude, produces a polygon the DSS rejects.
    """
    latitudes = [point.position.lat for point in points]
    longitudes = [point.position.lng for point in points]
    last = points[-1]
    lat = last.position.lat
    lng = last.position.lng
    if max(latitudes) - min(latitudes) < MIN_SPAN_DEG:
        lat += MIN_SPAN_DEG
    if max(longitudes) - min(longitudes) < MIN_SPAN_DEG:
        lng += MIN_SPAN_DEG
    if lat == last.position.lat and lng == last.position.lng:
        return points
    return [
        *points,
        TrackPoint(
            track_id=last.track_id,
            time=last.time + timedelta(seconds=1),
            position=GeoPoint(lat, lng, last.position.alt_m),
            speed_mps=last.speed_mps,
            heading_deg=last.heading_deg,
            vertical_speed_mps=last.vertical_speed_mps,
            uncertainty_m=last.uncertainty_m,
            source=last.source,
        ),
    ]


def horizontal_accuracy(uncertainty_m: float) -> str:
    """Map a metre uncertainty to the nearest honest horizontal class."""
    if uncertainty_m <= 1:
        return "HA1m"
    if uncertainty_m <= 3:
        return "HA3m"
    if uncertainty_m <= 10:
        return "HA10m"
    if uncertainty_m <= 30:
        return "HA30m"
    return "HAUnknown"


def _telemetry(point: TrackPoint) -> dict:
    return {
        "timestamp": format_utc(point.time),
        "timestamp_accuracy": 0.1,
        "operational_status": "Airborne" if point.position.alt_m > 0 else "Ground",
        "position": {
            "lat": point.position.lat,
            "lng": point.position.lng,
            "alt": point.position.alt_m,
            "accuracy_h": horizontal_accuracy(point.uncertainty_m),
            "accuracy_v": "VAUnknown",
        },
        "track": 0 if point.heading_deg is None else point.heading_deg,
        "speed": point.speed_mps,
        "speed_accuracy": "SAUnknown",
        "vertical_speed": point.vertical_speed_mps,
    }


def build_injection_body(points: list[TrackPoint]) -> dict:
    """Build the mock_uss test-injection body used by the working sandbox call."""
    flights = []
    for track_id, track_points in group_by_track(points).items():
        reported = _with_area(track_points)
        flights.append(
            {
                "injection_id": track_id,
                "telemetry": [_telemetry(point) for point in reported],
                "details_responses": [
                    {
                        "effective_after": format_utc(reported[0].time),
                        "details": {
                            "id": track_id,
                            "uas_id": {"utm_id": track_id},
                        },
                    }
                ],
            }
        )
    return {"requested_flights": flights}


def _request_json(method: str, url: str, body: dict | None = None, token: str | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed ({error.code}): {detail}") from error


def fetch_token(oauth_url: str, audience: str = "localhost") -> str:
    """Get a sandbox token for the injection scope."""
    url = (
        f"{oauth_url.rstrip('/')}/token?grant_type=client_credentials"
        f"&intended_audience={audience}&scope=rid.inject_test_data"
    )
    return _request_json("GET", url)["access_token"]


def publish_tracks(
    points: list[TrackPoint],
    *,
    mock_uss_url: str = "http://localhost:8081",
    oauth_url: str = "http://localhost:8085",
    test_id: str,
    lead_s: float = 120,
) -> dict:
    """Shift times forward and PUT one injection covering every track."""
    body = build_injection_body(shift_to_future(points, lead_s=lead_s))
    token = fetch_token(oauth_url)
    url = f"{mock_uss_url.rstrip('/')}/ridsp/injection/tests/{test_id}"
    return _request_json("PUT", url, body, token)
