"""Optional antenna array metadata (layout, transmit and receive elements,
polarization, element positions) travels from the input file to the outputs.
Nothing may break when it is absent or malformed."""

import json
import tempfile
import unittest
from pathlib import Path

from middleware.ingest.sionna import load_radar_detection_frames
from middleware.ingest.synthetic import (
    load_detection_frames,
    load_track_points,
    read_antenna_array,
)
from middleware.models import AntennaArray
from middleware.pipeline import process_local_detections
from middleware.publish.interuss_adapter import build_injection_payload
from middleware.publish.mock_uss import build_injection_body, write_track_points

from dashboard_api.sources.file_source import load_tracks_file

ROOT = Path(__file__).parents[1]
ORIGIN = ROOT / "scenarios/campus_origin.json"
RADAR_FILE = ROOT / "data/hermespy/radar_fmcw_11s.json"
CLOUD_FILE = ROOT / "data/synthetic/hermes_pointcloud_10s.json"
SIONNA_FILE = ROOT / "data/sionna/campus_2drone_10s.json"

ARRAY_2X2 = {
    "layout": "2x2",
    "num_elements": 4,
    "tx_elements": [0, 1],
    "rx_elements": [2, 3],
    "polarization": "V",
    "element_positions_m": [
        [-0.25, 0.0, 0.25],
        [0.25, 0.0, 0.25],
        [-0.25, 0.0, -0.25],
        [0.25, 0.0, -0.25],
    ],
}


class _Temp(unittest.TestCase):
    def write(self, document: dict, name: str = "input.json") -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def cloud_with(self, antenna_array) -> Path:
        document = json.loads(CLOUD_FILE.read_text(encoding="utf-8"))
        document["sensor"] = dict(document.get("sensor") or {"id": "bs1"})
        document["sensor"]["antenna_array"] = antenna_array
        return self.write(document)


class FullArrayTests(_Temp):
    def setUp(self) -> None:
        self.points = process_local_detections(self.cloud_with(ARRAY_2X2), ORIGIN)

    def test_every_field_is_read(self) -> None:
        array = self.points[0].source_meta.antenna_array
        self.assertEqual(array.layout, "2x2")
        self.assertEqual(array.num_elements, 4)
        self.assertEqual(array.tx_elements, (0, 1))
        self.assertEqual(array.rx_elements, (2, 3))
        self.assertEqual(array.polarization, "V")
        self.assertEqual(array.element_positions_m[0], (-0.25, 0.0, 0.25))
        self.assertEqual(len(array.element_positions_m), 4)

    def test_every_point_carries_it(self) -> None:
        self.assertTrue(all(p.source_meta.antenna_array is not None for p in self.points))

    def test_track_file_has_the_block_and_round_trips(self) -> None:
        path = self.write({}, "out.json")
        write_track_points(self.points, path)
        written = json.loads(path.read_text(encoding="utf-8"))["points"][0]
        block = written["source_meta"]["antenna_array"]
        self.assertEqual(block["layout"], "2x2")
        self.assertEqual(block["tx_elements"], [0, 1])
        self.assertEqual(block["element_positions_m"][3], [0.25, 0.0, -0.25])
        again = load_track_points(path)
        self.assertEqual(again[0].source_meta, self.points[0].source_meta)

    def test_dashboard_api_passes_the_block_through(self) -> None:
        path = self.write({}, "out.json")
        write_track_points(self.points, path)
        document = load_tracks_file(path, ORIGIN)
        block = document["tracks"][0]["points"][0]["source_meta"]["antenna_array"]
        self.assertEqual(block["rx_elements"], [2, 3])
        self.assertEqual(block["polarization"], "V")

    def test_report_text_names_the_array(self) -> None:
        details = build_injection_body(self.points)["requested_flights"][0]["details_responses"][0]["details"]
        text = details["operation_description"]
        for part in ("array=2x2", "elements=4", "tx=0,1", "rx=2,3", "pol=V"):
            self.assertIn(part, text)
        self.assertIn("array=2x2", build_injection_payload(self.points)["aircraft"][0]["source_meta"])

    def test_report_text_can_still_be_switched_off(self) -> None:
        body = build_injection_body(self.points, include_metadata=False)
        details = body["requested_flights"][0]["details_responses"][0]["details"]
        self.assertNotIn("operation_description", details)


class RealDataTests(unittest.TestCase):
    def test_sionna_scene_has_one_transmit_and_one_receive_antenna(self) -> None:
        points = process_local_detections(SIONNA_FILE, ORIGIN)
        array = points[0].source_meta.antenna_array
        self.assertEqual(array.layout, "1x1 TX + 1x1 RX")
        self.assertEqual(array.num_elements, 2)
        self.assertEqual(array.tx_elements, (0,))
        self.assertEqual(array.rx_elements, (1,))
        self.assertEqual(array.polarization, "V")
        self.assertEqual(array.element_positions_m, ((0.0, 0.0, 0.0), (0.5, 0.0, 0.0)))

    def test_hermespy_radar_has_one_element_that_sends_and_listens(self) -> None:
        points = process_local_detections(RADAR_FILE, ORIGIN, loader=load_radar_detection_frames)
        array = points[0].source_meta.antenna_array
        self.assertEqual(array.layout, "1x1")
        self.assertEqual(array.tx_elements, (0,))
        self.assertEqual(array.rx_elements, (0,))
        self.assertIsNone(array.polarization)  # HermesPy does not record it

    def test_old_files_without_the_block_still_work(self) -> None:
        points = process_local_detections(CLOUD_FILE, ORIGIN)
        self.assertIsNone(points[0].source_meta.antenna_array)
        again = load_track_points(ROOT / "data/synthetic/campus_3track_10s.json")
        self.assertIsNone(again[0].source_meta)

    def test_report_text_is_unchanged_without_an_array(self) -> None:
        points = process_local_detections(CLOUD_FILE, ORIGIN)
        text = build_injection_body(points)["requested_flights"][0]["details_responses"][0]["details"]["operation_description"]
        self.assertNotIn("array=", text)

    def test_missing_block_adds_a_null_in_the_track_file(self) -> None:
        points = process_local_detections(CLOUD_FILE, ORIGIN)
        self.assertIn("antenna_array", points[0].to_dict()["source_meta"])
        self.assertIsNone(points[0].to_dict()["source_meta"]["antenna_array"])


class PartialArrayTests(_Temp):
    def test_a_few_fields_are_enough(self) -> None:
        points = process_local_detections(self.cloud_with({"layout": "2x2", "polarization": "H"}), ORIGIN)
        array = points[0].source_meta.antenna_array
        self.assertEqual((array.layout, array.polarization), ("2x2", "H"))
        self.assertIsNone(array.num_elements)
        self.assertIsNone(array.tx_elements)
        self.assertIsNone(array.element_positions_m)

    def test_element_numbers_are_not_range_checked_without_a_count(self) -> None:
        array = read_antenna_array({"tx_elements": [0, 9]})
        self.assertEqual(array.tx_elements, (0, 9))

    def test_an_empty_list_means_none_transmit(self) -> None:
        array = read_antenna_array({"num_elements": 2, "tx_elements": [], "rx_elements": [0, 1]})
        self.assertEqual(array.tx_elements, ())
        self.assertEqual(array.rx_elements, (0, 1))

    def test_empty_block_gives_none(self) -> None:
        self.assertIsNone(read_antenna_array({}))
        self.assertIsNone(read_antenna_array(None))


class BadValueTests(_Temp):
    """A bad field is ignored and logged. Other fields stay. No reading is skipped."""

    def load(self, antenna_array):
        issues: list[str] = []
        path = self.cloud_with(antenna_array)
        with self.assertLogs("middleware.ingest", level="WARNING") as logs:
            frames = load_detection_frames(path, issues=issues)
        self.assertEqual(issues, [])  # nothing counted as a skipped reading
        self.assertEqual(sum(len(f.detections) for f in frames), 34)  # every reading kept
        return frames[0].detections[0].source_meta.antenna_array, "\n".join(logs.output)

    def test_bad_layout_and_polarization_text(self) -> None:
        array, log = self.load({**ARRAY_2X2, "layout": 22, "polarization": "  "})
        self.assertIsNone(array.layout)
        self.assertIsNone(array.polarization)
        self.assertEqual(array.num_elements, 4)
        self.assertIn("antenna_array.layout", log)
        self.assertIn("antenna_array.polarization", log)

    def test_bad_element_count(self) -> None:
        for bad in (0, -2, "four", 2.5, True):
            with self.subTest(bad=bad):
                array, log = self.load({**ARRAY_2X2, "num_elements": bad})
                self.assertIsNone(array.num_elements)
                self.assertIn("antenna_array.num_elements", log)
                # Without a count the other fields are not cross-checked against it.
                self.assertEqual(array.tx_elements, (0, 1))
                self.assertEqual(len(array.element_positions_m), 4)

    def test_element_number_outside_the_count(self) -> None:
        array, log = self.load({**ARRAY_2X2, "tx_elements": [0, 4]})
        self.assertIsNone(array.tx_elements)
        self.assertEqual(array.rx_elements, (2, 3))
        self.assertIn("antenna_array.tx_elements", log)

    def test_bad_element_lists(self) -> None:
        for bad in ("0,1", [0, "x"], [-1], [0.5], [True], 3):
            with self.subTest(bad=bad):
                array, log = self.load({**ARRAY_2X2, "rx_elements": bad})
                self.assertIsNone(array.rx_elements)
                self.assertIn("antenna_array.rx_elements", log)

    def test_bad_positions(self) -> None:
        cases = {
            "wrong count": ARRAY_2X2["element_positions_m"][:3],
            "two numbers": [[0, 0]] * 4,
            "text": [["a", "b", "c"]] * 4,
            "not a list": "centered",
            "null number": [[0, 0, None]] * 4,
        }
        for label, bad in cases.items():
            with self.subTest(case=label):
                array, log = self.load({**ARRAY_2X2, "element_positions_m": bad})
                self.assertIsNone(array.element_positions_m)
                self.assertEqual(array.layout, "2x2")
                self.assertIn("antenna_array.element_positions_m", log)

    def test_whole_block_not_an_object(self) -> None:
        for bad in ("2x2", [1, 2], 5):
            with self.subTest(bad=bad):
                array, log = self.load(bad)
                self.assertIsNone(array)
                self.assertIn("antenna_array", log)

    def test_block_with_only_bad_fields_gives_none(self) -> None:
        array, _ = self.load({"layout": 1, "num_elements": "x"})
        self.assertIsNone(array)

    def test_radar_loader_ignores_bad_block_too(self) -> None:
        document = json.loads(RADAR_FILE.read_text(encoding="utf-8"))
        document["sensor"]["antenna_array"] = {"layout": 3}
        with self.assertLogs("middleware.ingest", level="WARNING"):
            frames = load_radar_detection_frames(self.write(document))
        self.assertEqual(len(frames[0].detections), 1)
        self.assertIsNone(frames[0].detections[0].source_meta.antenna_array)


class ModelTests(unittest.TestCase):
    def test_describe_leaves_out_unknown_parts(self) -> None:
        self.assertEqual(AntennaArray().describe(), [])
        self.assertEqual(AntennaArray(layout="1x1 TX + 1x1 RX").describe(), ["array=1x1_TX+1x1_RX"])


if __name__ == "__main__":
    unittest.main()
