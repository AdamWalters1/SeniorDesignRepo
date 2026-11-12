"""Source metadata (sensor ID, type, signal, carrier, bandwidth, resolution,
position) travels from the input file to the outputs."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from middleware.ingest.sionna import load_radar_detection_frames
from middleware.ingest.synthetic import load_detection_frames, load_track_points
from middleware.pipeline import process_local_detections
from middleware.publish.interuss_adapter import build_injection_payload
from middleware.publish.mock_uss import build_injection_body, write_track_points

ROOT = Path(__file__).parents[1]
ORIGIN = ROOT / "scenarios/campus_origin.json"
RADAR_FILE = ROOT / "data/hermespy/radar_fmcw_11s.json"
CLOUD_FILE = ROOT / "data/synthetic/hermes_pointcloud_10s.json"


class _Temp(unittest.TestCase):
    def write(self, document: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "input.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path


class RadarMetadataTests(_Temp):
    def setUp(self) -> None:
        self.points = process_local_detections(
            RADAR_FILE, ORIGIN, loader=load_radar_detection_frames
        )

    def test_every_point_carries_the_sensor_description(self) -> None:
        for point in self.points:
            meta = point.source_meta
            self.assertEqual(meta.sensor_id, "radar1")
            self.assertEqual(meta.sensor_type, "radar")
            self.assertEqual(meta.signal_type, "FMCW")
            self.assertEqual(meta.carrier_frequency_hz, 24e9)
            self.assertEqual(meta.bandwidth_hz, 93090816.0)
            self.assertEqual(meta.range_resolution_m, 1.61)

    def test_position_is_marked_as_assumed_and_has_lat_lng(self) -> None:
        meta = self.points[0].source_meta
        self.assertEqual(meta.sensor_position_m, (0.0, 0.0, 25.0))
        self.assertTrue(meta.sensor_position_assumed)
        self.assertAlmostEqual(meta.sensor_position_wgs84.lat, 37.2284)
        self.assertAlmostEqual(meta.sensor_position_wgs84.alt_m, 655.0)

    def test_old_fields_are_unchanged(self) -> None:
        self.assertEqual({p.uncertainty_m for p in self.points}, {1.61})
        self.assertEqual(len(self.points), 11)

    def test_position_in_file_beats_the_default(self) -> None:
        document = json.loads(RADAR_FILE.read_text(encoding="utf-8"))
        document["sensor"]["position_m"] = [10.0, 20.0, 30.0]
        frames = load_radar_detection_frames(self.write(document))
        meta = frames[0].detections[0].source_meta
        self.assertEqual(meta.sensor_position_m, (10.0, 20.0, 30.0))
        self.assertFalse(meta.sensor_position_assumed)
        self.assertEqual(frames[0].detections[0].position_m, (10.0, 20.0 + 40.73267092391305, 30.0))

    def test_old_file_without_metadata_still_works(self) -> None:
        document = json.loads(RADAR_FILE.read_text(encoding="utf-8"))
        document["sensor"] = {"id": "radar1", "bandwidth_hz": 93090816.0}
        points = process_local_detections(
            self.write(document), ORIGIN, loader=load_radar_detection_frames
        )
        meta = points[0].source_meta
        self.assertIsNone(meta.sensor_type)
        self.assertIsNone(meta.signal_type)
        self.assertIsNone(meta.carrier_frequency_hz)
        self.assertEqual(meta.range_resolution_m, 1.61)
        self.assertEqual(points[0].uncertainty_m, 1.61)

    def test_no_sensor_block_at_all_still_works(self) -> None:
        document = json.loads(RADAR_FILE.read_text(encoding="utf-8"))
        del document["sensor"]
        points = process_local_detections(
            self.write(document), ORIGIN, loader=load_radar_detection_frames
        )
        self.assertEqual(points[0].source_meta.sensor_id, "unknown")
        self.assertEqual(len(points), 11)

    def test_bad_metadata_is_ignored_and_logged_not_fatal(self) -> None:
        document = json.loads(RADAR_FILE.read_text(encoding="utf-8"))
        document["sensor"]["bandwidth_hz"] = -5
        document["sensor"]["carrier_frequency_hz"] = "fast"
        document["sensor"]["position_m"] = [1, 2]
        issues: list[str] = []
        with self.assertLogs("middleware.ingest", level="WARNING"):
            frames = load_radar_detection_frames(self.write(document), issues=issues)
        self.assertEqual(len(issues), 3)
        meta = frames[0].detections[0].source_meta
        self.assertIsNone(meta.bandwidth_hz)
        self.assertIsNone(meta.carrier_frequency_hz)
        self.assertTrue(meta.sensor_position_assumed)
        # With no usable bandwidth the file's own range_resolution_m is used.
        self.assertEqual(frames[0].detections[0].uncertainty_m, 1.61)


class PointCloudMetadataTests(unittest.TestCase):
    def test_point_cloud_file_gives_id_and_position_only(self) -> None:
        points = process_local_detections(CLOUD_FILE, ORIGIN)
        meta = points[0].source_meta
        self.assertEqual(meta.sensor_id, "bs1")
        self.assertEqual(meta.sensor_position_m, (0.0, 0.0, 25.0))
        self.assertFalse(meta.sensor_position_assumed)
        self.assertIsNone(meta.signal_type)


class OutputTests(_Temp):
    def setUp(self) -> None:
        self.points = process_local_detections(
            RADAR_FILE, ORIGIN, loader=load_radar_detection_frames
        )

    def test_written_json_has_source_meta_and_old_keys(self) -> None:
        path = self.write({}).with_name("out.json")
        write_track_points(self.points, path)
        written = json.loads(path.read_text(encoding="utf-8"))["points"][0]
        for key in ("track_id", "time", "lat", "lng", "alt", "speed_mps", "heading_deg",
                    "vertical_speed_mps", "uncertainty_m", "source"):
            self.assertIn(key, written)
        self.assertEqual(written["source_meta"]["signal_type"], "FMCW")

    def test_geocoded_loader_round_trips_the_metadata(self) -> None:
        path = self.write({}).with_name("out.json")
        write_track_points(self.points, path)
        again = load_track_points(path)
        self.assertEqual(again[0].source_meta, self.points[0].source_meta)

    def test_geocoded_file_without_metadata_still_loads(self) -> None:
        again = load_track_points(ROOT / "data/synthetic/campus_3track_10s.json")
        self.assertIsNone(again[0].source_meta)

    def test_report_keeps_its_shape_and_adds_one_text_field(self) -> None:
        with_meta = build_injection_body(self.points)
        without = build_injection_body(self.points, include_metadata=False)
        flight = with_meta["requested_flights"][0]
        plain = without["requested_flights"][0]
        self.assertEqual(flight["telemetry"], plain["telemetry"])
        details = flight["details_responses"][0]["details"]
        self.assertEqual(set(details) - set(plain["details_responses"][0]["details"]),
                         {"operation_description"})
        self.assertIn("signal=FMCW", details["operation_description"])
        self.assertIn("sensor=radar1", details["operation_description"])
        self.assertNotIn("operation_description", plain["details_responses"][0]["details"])

    def test_point_without_metadata_gives_the_old_report(self) -> None:
        from dataclasses import replace
        bare = [replace(p, source_meta=None) for p in self.points]
        details = build_injection_body(bare)["requested_flights"][0]["details_responses"][0]["details"]
        self.assertEqual(set(details), {"id", "uas_id"})

    def test_metadata_survives_the_future_shift_and_area_point(self) -> None:
        body_points = build_injection_body(self.points)["requested_flights"][0]["telemetry"]
        self.assertEqual(len(body_points), 12)  # 11 readings plus the one area point

    def test_adapter_payload_includes_metadata_text(self) -> None:
        payload = build_injection_payload(self.points)
        self.assertIn("signal=FMCW", payload["aircraft"][0]["source_meta"])


if __name__ == "__main__":
    unittest.main()
