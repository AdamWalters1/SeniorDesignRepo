"""REL-1: invalid readings are skipped and logged. They never crash the run and
never create a track."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from middleware.ingest.sionna import load_radar_detection_frames
from middleware.ingest.synthetic import load_detection_frames
from middleware.pipeline import process_local_detections

ROOT = Path(__file__).parents[1]
ORIGIN = ROOT / "scenarios/campus_origin.json"
RADAR_FILE = ROOT / "data/hermespy/radar_fmcw_11s.json"
CLOUD_FILE = ROOT / "data/synthetic/hermes_pointcloud_10s.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class _TempFileCase(unittest.TestCase):
    def write(self, document: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "input.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path


class RadarInvalidReadingTests(_TempFileCase):
    def run_radar(self, document: dict):
        path = self.write(document)
        issues: list[str] = []
        with self.assertLogs("middleware.ingest", level="WARNING") as logs:
            frames = load_radar_detection_frames(path, issues=issues)
        points = process_local_detections(
            path, ORIGIN, loader=load_radar_detection_frames
        )
        return frames, issues, logs.output, points

    def change_frame_5(self, **detection) -> dict:
        document = copy.deepcopy(_load(RADAR_FILE))
        document["frames"][5]["detections"][0].update(detection)
        return document

    def assert_skipped_one(self, document: dict) -> None:
        frames, issues, log_lines, points = self.run_radar(document)
        self.assertEqual(len(issues), 1)
        self.assertIn("frame 5 reading 0", issues[0])
        self.assertEqual(len(log_lines), 1)
        self.assertEqual(len(frames[5].detections), 0)
        self.assertEqual(len(points), 10)
        self.assertEqual({p.track_id for p in points}, {"t1"})

    def test_clean_file_has_no_issues(self) -> None:
        issues: list[str] = []
        load_radar_detection_frames(RADAR_FILE, issues=issues)
        self.assertEqual(issues, [])

    def test_missing_range_is_skipped(self) -> None:
        document = copy.deepcopy(_load(RADAR_FILE))
        del document["frames"][5]["detections"][0]["range_m"]
        self.assert_skipped_one(document)

    def test_null_range_is_skipped(self) -> None:
        self.assert_skipped_one(self.change_frame_5(range_m=None))

    def test_negative_range_is_skipped_and_no_second_track(self) -> None:
        self.assert_skipped_one(self.change_frame_5(range_m=-50.0))

    def test_negative_power_is_skipped(self) -> None:
        self.assert_skipped_one(self.change_frame_5(power=-1e-9))

    def test_zero_power_is_skipped(self) -> None:
        self.assert_skipped_one(self.change_frame_5(power=0))

    def test_missing_power_is_skipped(self) -> None:
        document = copy.deepcopy(_load(RADAR_FILE))
        del document["frames"][5]["detections"][0]["power"]
        self.assert_skipped_one(document)

    def test_text_range_and_nan_are_skipped(self) -> None:
        self.assert_skipped_one(self.change_frame_5(range_m="far"))
        self.assert_skipped_one(self.change_frame_5(range_m=float("nan")))

    def test_reading_that_is_not_an_object_is_skipped(self) -> None:
        document = copy.deepcopy(_load(RADAR_FILE))
        document["frames"][5]["detections"][0] = 42.0
        self.assert_skipped_one(document)

    def test_one_bad_reading_does_not_hide_a_good_one(self) -> None:
        document = copy.deepcopy(_load(RADAR_FILE))
        good = dict(document["frames"][5]["detections"][0])
        document["frames"][5]["detections"].insert(0, {"range_m": -1.0, "power": 1e-9})
        _, issues, _, points = self.run_radar(document)
        self.assertEqual(len(issues), 1)
        self.assertEqual(len(points), 11)
        self.assertEqual(good["range_m"] > 0, True)

    def test_frame_without_time_is_skipped(self) -> None:
        document = copy.deepcopy(_load(RADAR_FILE))
        del document["frames"][5]["time"]
        frames, issues, _, points = self.run_radar(document)
        self.assertEqual(len(frames), 10)
        self.assertIn("whole frame skipped", issues[0])
        self.assertEqual(len(points), 10)

    def test_all_readings_bad_gives_no_points_not_a_crash(self) -> None:
        document = copy.deepcopy(_load(RADAR_FILE))
        for frame in document["frames"]:
            frame["detections"] = [{"range_m": -3.0, "power": 1e-9}]
        path = self.write(document)
        with self.assertLogs("middleware.ingest", level="WARNING"):
            points = process_local_detections(
                path, ORIGIN, loader=load_radar_detection_frames
            )
        self.assertEqual(points, [])


class PointCloudInvalidReadingTests(_TempFileCase):
    def run_cloud(self, document: dict):
        path = self.write(document)
        issues: list[str] = []
        with self.assertLogs("middleware.ingest", level="WARNING"):
            load_detection_frames(path, issues=issues)
        points = process_local_detections(path, ORIGIN)
        return issues, points

    def test_clean_file_has_no_issues(self) -> None:
        issues: list[str] = []
        load_detection_frames(CLOUD_FILE, issues=issues)
        self.assertEqual(issues, [])

    def test_missing_position_is_skipped(self) -> None:
        document = copy.deepcopy(_load(CLOUD_FILE))
        del document["frames"][5]["detections"][0]["position_m"]
        issues, points = self.run_cloud(document)
        self.assertEqual(len(issues), 1)
        self.assertEqual(len(points), 32)

    def test_null_position_and_short_position_are_skipped(self) -> None:
        for bad in (None, [1.0, 2.0], ["a", 1, 2]):
            document = copy.deepcopy(_load(CLOUD_FILE))
            document["frames"][5]["detections"][0]["position_m"] = bad
            issues, points = self.run_cloud(document)
            self.assertEqual(len(issues), 1, bad)
            self.assertEqual(len(points), 32, bad)

    def test_missing_velocity_is_skipped(self) -> None:
        document = copy.deepcopy(_load(CLOUD_FILE))
        del document["frames"][5]["detections"][0]["velocity_mps"]
        issues, points = self.run_cloud(document)
        self.assertEqual(len(issues), 1)
        self.assertEqual(len(points), 32)

    def test_negative_and_null_power_are_skipped(self) -> None:
        for bad in (-0.5, None, 0):
            document = copy.deepcopy(_load(CLOUD_FILE))
            document["frames"][5]["detections"][0]["power"] = bad
            issues, points = self.run_cloud(document)
            self.assertEqual(len(issues), 1, bad)
            self.assertEqual(len(points), 32, bad)

    def test_dropped_aircraft_keeps_its_id_after_a_bad_reading(self) -> None:
        document = copy.deepcopy(_load(CLOUD_FILE))
        del document["frames"][5]["detections"][0]["position_m"]
        _, points = self.run_cloud(document)
        self.assertEqual({p.track_id for p in points}, {"t1", "t2", "t3"})


if __name__ == "__main__":
    unittest.main()
