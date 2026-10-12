"""Tests for the HermesPy radar input path."""

import unittest
from pathlib import Path

from middleware.ingest.sionna import load_radar_detection_frames
from middleware.pipeline import process_local_detections

ROOT = Path(__file__).parents[1]


class RadarPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.points = process_local_detections(
            ROOT / "data/hermespy/radar_fmcw_11s.json",
            ROOT / "scenarios/campus_origin.json",
            loader=load_radar_detection_frames,
        )

    def test_one_track_moving_north(self) -> None:
        self.assertEqual(len(self.points), 11)
        self.assertEqual({point.track_id for point in self.points}, {"t1"})
        latitudes = [point.position.lat for point in self.points]
        self.assertEqual(latitudes, sorted(latitudes))

    def test_uncertainty_is_range_resolution(self) -> None:
        self.assertEqual({point.uncertainty_m for point in self.points}, {1.61})

    def test_speed_is_estimated_from_motion(self) -> None:
        self.assertEqual(self.points[0].speed_mps, 0.0)
        for point in self.points[3:]:
            self.assertTrue(2.0 < point.speed_mps < 4.0)


if __name__ == "__main__":
    unittest.main()