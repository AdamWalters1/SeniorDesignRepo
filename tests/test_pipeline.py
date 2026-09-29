"""Tests for the first end-to-end middleware path."""

from __future__ import annotations

import unittest
from pathlib import Path

from middleware.geocode.wgs84 import local_to_wgs84
from middleware.models import GeoPoint
from middleware.pipeline import process_local_detections

ROOT = Path(__file__).parents[1]


class GeocodeTests(unittest.TestCase):
    def test_origin_maps_to_itself(self) -> None:
        origin = GeoPoint(37.2284, -80.4234, 630.0)
        self.assertEqual(local_to_wgs84((0, 0, 0), origin), origin)

    def test_east_north_up_increase_expected_coordinates(self) -> None:
        origin = GeoPoint(37.2284, -80.4234, 630.0)
        point = local_to_wgs84((10, 10, 10), origin)
        self.assertGreater(point.lat, origin.lat)
        self.assertGreater(point.lng, origin.lng)
        self.assertEqual(point.alt_m, 640.0)


class PipelineTests(unittest.TestCase):
    def test_three_tracks_are_stable_and_clutter_is_ignored(self) -> None:
        points = process_local_detections(
            ROOT / "data/synthetic/hermes_pointcloud_10s.json",
            ROOT / "scenarios/campus_origin.json",
        )
        self.assertEqual(len(points), 33)
        self.assertEqual({point.track_id for point in points}, {"t1", "t2", "t3"})
        self.assertEqual(
            {sum(point.track_id == track_id for point in points) for track_id in {"t1", "t2", "t3"}},
            {11},
        )

    def test_motion_fields_are_derived(self) -> None:
        points = process_local_detections(
            ROOT / "data/synthetic/hermes_pointcloud_10s.json",
            ROOT / "scenarios/campus_origin.json",
        )
        first = points[0]
        self.assertEqual(first.speed_mps, 8.0)
        self.assertEqual(first.heading_deg, 0.0)
        self.assertGreater(first.uncertainty_m, 0)


if __name__ == "__main__":
    unittest.main()
