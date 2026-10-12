"""Tests for the mock_uss injection payload."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from middleware.models import GeoPoint, TrackPoint
from middleware.publish.mock_uss import (
    build_injection_body,
    publish_tracks,
    shift_to_future,
)


def _point(track_id: str, minute: int, lat: float, lng: float) -> TrackPoint:
    return TrackPoint(
        track_id=track_id,
        time=datetime(2026, 9, 29, 18, minute, tzinfo=timezone.utc),
        position=GeoPoint(lat, lng, 120),
        speed_mps=8,
        heading_deg=0,
        vertical_speed_mps=0,
        uncertainty_m=1.6,
        source="test",
    )


class PublishPayloadTests(unittest.TestCase):
    def test_times_move_into_the_future_without_changing_spacing(self) -> None:
        points = [_point("t1", 0, 37.22, -80.42), _point("t1", 1, 37.23, -80.41)]
        now = datetime(2026, 10, 12, 19, 23, tzinfo=timezone.utc)
        shifted = shift_to_future(points, lead_s=120, now=now)
        self.assertEqual(shifted[0].time, now + timedelta(seconds=120))
        self.assertEqual(shifted[1].time - shifted[0].time, timedelta(minutes=1))

    def test_north_only_track_gets_a_longitude_span(self) -> None:
        body = build_injection_body(
            [_point("t1", 0, 37.2284, -80.4234), _point("t1", 1, 37.2291, -80.4234)]
        )
        longitudes = [
            sample["position"]["lng"]
            for sample in body["requested_flights"][0]["telemetry"]
        ]
        self.assertGreater(max(longitudes) - min(longitudes), 0)
        self.assertEqual(
            body["requested_flights"][0]["telemetry"][0]["position"]["accuracy_h"],
            "HA3m",
        )

    def test_publish_sends_the_injection_put(self) -> None:
        calls = []

        def fake_request(method, url, body=None, token=None):
            calls.append((method, url, body, token))
            if method == "GET":
                return {"access_token": "token-1"}
            return {"injected_flights": body["requested_flights"]}

        points = [_point("t1", 0, 37.2284, -80.4234), _point("t1", 1, 37.2291, -80.4228)]
        with patch("middleware.publish.mock_uss._request_json", fake_request):
            result = publish_tracks(points, test_id="demo-test", lead_s=120)

        self.assertEqual(len(result["injected_flights"]), 1)
        self.assertEqual(calls[0][0], "GET")
        self.assertIn("rid.inject_test_data", calls[0][1])
        self.assertEqual(calls[1][0], "PUT")
        self.assertTrue(calls[1][1].endswith("/ridsp/injection/tests/demo-test"))
        self.assertEqual(calls[1][3], "token-1")
        self.assertIn("requested_flights", calls[1][2])

    def test_http_error_includes_the_response_body(self) -> None:
        def fake_request(method, url, body=None, token=None):
            if method == "GET":
                return {"access_token": "token-1"}
            raise RuntimeError("PUT failed (400): time_start must not be in the past")

        points = [_point("t1", 0, 37.22, -80.42), _point("t1", 1, 37.23, -80.41)]
        with patch("middleware.publish.mock_uss._request_json", fake_request):
            with self.assertRaises(RuntimeError) as caught:
                publish_tracks(points, test_id="demo-test")
        self.assertIn("time_start", str(caught.exception))
