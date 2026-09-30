"""
Converts our middleware aircraft data into a JSON format
that can later be sent to a mock USS/InterUSS system.
"""

from middleware.models import TrackPoint, format_utc

def track_point_to_payload(point: TrackPoint):
    """Convert one aircraft tracking point into a USS-style format."""

    return {
        "track_id": point.track_id,

        "timestamp": format_utc(point.time),

        "position": {
            "lat": point.position.lat,
            "lng": point.position.lng,
            "alt_m": point.position.alt_m,
        },

        "velocity": {
            "speed_mps": point.speed_mps,
            "heading_deg": point.heading_deg,
            "vertical_speed_mps": point.vertical_speed_mps,
        },

        "position_uncertainty_m": point.uncertainty_m,

        "source": point.source,
    }

def build_injection_payload(points: list[TrackPoint]):
    """Put multiple aircraft tracking points into one payload."""

    return {
        "description": "Prototype USS injection payload",
        "aircraft": [
            track_point_to_payload(point)
            for point in points
        ],
    }