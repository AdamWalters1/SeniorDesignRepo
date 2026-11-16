"""Tests for the Sionna scene input path (tools/sionna_scene_run.py output)."""

import json
import math
import os
import unittest
from importlib.util import find_spec
from pathlib import Path

from middleware.pipeline import process_local_detections

ROOT = Path(__file__).parents[1]
SIONNA = ROOT / "data/sionna"
ORIGIN = ROOT / "scenarios/campus_origin.json"
EARTH_RADIUS_M = 6_378_137.0


def to_scene_metres(lat: float, lng: float, origin: dict) -> tuple[float, float]:
    """Invert the geocoder: WGS84 back to east and north metres from the scene origin."""
    east = math.radians(lng - origin["lng"]) * EARTH_RADIUS_M * math.cos(math.radians(origin["lat"]))
    north = math.radians(lat - origin["lat"]) * EARTH_RADIUS_M
    return east, north


class TwoAircraftCrossingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = SIONNA / "campus_2drone_10s.json"
        self.truth = json.loads((SIONNA / "campus_2drone_10s_truth.json").read_text())
        self.points = process_local_detections(self.data, ORIGIN)
        self.origin = json.loads(ORIGIN.read_text())["origin"]

    def nearest_truth(self, point):
        """Name of the true aircraft nearest to this track point, and the 2D miss in metres."""
        east, north = to_scene_metres(point.position.lat, point.position.lng, self.origin)
        by_time = {frame["time"]: frame["drones"] for frame in self.truth}
        drones = by_time[point.time.isoformat().replace("+00:00", "Z")]
        name = min(drones, key=lambda n: math.hypot(east - drones[n]["position_m"][0], north - drones[n]["position_m"][1]))
        miss = math.hypot(east - drones[name]["position_m"][0], north - drones[name]["position_m"][1])
        return name, miss

    def test_tracks_land_on_the_true_positions(self) -> None:
        """Every track point is within 5 m of a true aircraft after the geocode round trip."""
        for point in self.points:
            self.assertLess(self.nearest_truth(point)[1], 5.0)

    def test_each_track_stays_on_one_aircraft(self) -> None:
        owners = {}
        for point in self.points:
            owners.setdefault(point.track_id, set()).add(self.nearest_truth(point)[0])
        for track, names in owners.items():
            self.assertEqual(len(names), 1, f"{track} jumped between aircraft {names}")

    def test_speed_comes_from_position_changes(self) -> None:
        """After the first point, track speed is within 1.5 m/s of the true speed."""
        for point in self.points:
            name, _ = self.nearest_truth(point)
            if point.speed_mps == 0.0:
                continue
            frame = next(f for f in self.truth if f["time"] == point.time.isoformat().replace("+00:00", "Z"))
            vx, vy, vz = frame["drones"][name]["velocity_mps"]
            self.assertLess(abs(math.hypot(vx, vy) - point.speed_mps), 1.5)

    def test_origin_is_the_blender_scene_origin(self) -> None:
        """The scene was built from OpenStreetMap, and Blender stores that extent's centre."""
        self.assertAlmostEqual(self.origin["lat"], 37.22859, places=5)
        self.assertAlmostEqual(self.origin["lng"], -80.42490, places=5)

    def test_sensor_position_is_given_not_assumed(self) -> None:
        meta = self.points[0].source_meta
        self.assertFalse(meta.sensor_position_assumed)
        self.assertEqual(meta.sensor_position_m, (-17.0, 4.0, 19.0))

    def test_file_carries_radial_speed_but_no_velocity_vector(self) -> None:
        for frame in json.loads(self.data.read_text())["frames"]:
            for detection in frame["detections"]:
                self.assertIn("radial_speed_mps", detection)
                self.assertNotIn("velocity_mps", detection)

    def test_two_tracks_through_the_crossing(self) -> None:
        self.assertEqual({point.track_id for point in self.points}, {"t1", "t2"})
        self.assertEqual(len(self.points), 22)

    def test_both_aircraft_are_heard_every_second(self) -> None:
        counts = [len(frame["detections"]) for frame in json.loads(self.data.read_text())["frames"]]
        self.assertEqual(counts, [2] * 11)


@unittest.skipUnless(
    find_spec("sionna") and os.environ.get("SIONNA_SCENE"),
    "needs sionna-rt installed and SIONNA_SCENE set to burrus-test-3.xml",
)
class SionnaRegenerationTests(unittest.TestCase):
    def test_script_reproduces_the_data_file(self) -> None:
        """Positions match to 1 cm. Exact bytes can differ between GPUs and drivers."""
        import sys

        sys.path.insert(0, str(ROOT / "tools"))
        from sionna_scene_run import run

        name = "campus_2drone_10s"
        scenario = json.loads((ROOT / f"scenarios/{name}.json").read_text())
        document, _ = run(scenario, os.environ["SIONNA_SCENE"])
        saved = json.loads((SIONNA / f"{name}.json").read_text())
        self.assertEqual(
            [len(f["detections"]) for f in document["frames"]],
            [len(f["detections"]) for f in saved["frames"]],
        )
        for new, old in zip(document["frames"], saved["frames"]):
            for a, b in zip(new["detections"], old["detections"]):
                for x, y in zip(a["position_m"], b["position_m"]):
                    self.assertAlmostEqual(x, y, delta=0.01)


if __name__ == "__main__":
    unittest.main()
