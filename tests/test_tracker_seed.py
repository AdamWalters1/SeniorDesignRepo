"""The Doppler speed seeds a new track's first prediction and nothing else."""

import unittest
from datetime import datetime, timedelta, timezone

from middleware.associate.tracker import NearestNeighborTracker
from middleware.models import Detection, SourceMeta

START = datetime(2026, 11, 16, 15, tzinfo=timezone.utc)
SENSOR = (-100.0, 0.0, 0.0)


def reading(second, x, radial=None, assumed=False, sensor=SENSOR):
    """A reading on the line of sight from a sensor 100 m west of the aircraft."""
    meta = SourceMeta(sensor_position_m=sensor, sensor_position_assumed=assumed)
    return Detection(
        time=START + timedelta(seconds=second),
        position_m=(x, 0.0, 0.0),
        velocity_mps=None,
        power=1.0,
        source_meta=meta,
        radial_speed_mps=radial,
    )


def crossing_pair(with_doppler):
    """Two aircraft 12 m apart flying toward each other at 8 m/s, then one update later."""
    first = [reading(0, 0.0, 8.0 if with_doppler else None), reading(0, 12.0, -8.0 if with_doppler else None)]
    second = [reading(1, 8.0, 8.0 if with_doppler else None), reading(1, 4.0, -8.0 if with_doppler else None)]
    return first, second


class DopplerSeedTests(unittest.TestCase):
    def ids(self, with_doppler):
        tracker = NearestNeighborTracker()
        first, second = crossing_pair(with_doppler)
        a, b = (tid for tid, _ in tracker.update(first))
        later = {round(d.position_m[0]): tid for tid, d in tracker.update(second)}
        return a, b, later

    def test_without_doppler_close_aircraft_swap_ids(self) -> None:
        a, b, later = self.ids(with_doppler=False)
        self.assertEqual((later[8], later[4]), (b, a))

    def test_with_doppler_close_aircraft_keep_ids(self) -> None:
        a, b, later = self.ids(with_doppler=True)
        self.assertEqual((later[8], later[4]), (a, b))

    def test_seed_is_not_reported(self) -> None:
        tracker = NearestNeighborTracker()
        first, _ = crossing_pair(with_doppler=True)
        for _, detection in tracker.update(first):
            self.assertEqual(detection.velocity_mps, (0.0, 0.0, 0.0))

    def test_next_update_uses_the_change_in_position(self) -> None:
        tracker = NearestNeighborTracker()
        first, second = crossing_pair(with_doppler=True)
        tracker.update(first)
        speeds = sorted(round(d.velocity_mps[0], 3) for _, d in tracker.update(second))
        self.assertEqual(speeds, [-8.0, 8.0])

    def test_assumed_sensor_position_gives_no_seed(self) -> None:
        tracker = NearestNeighborTracker()
        first = [reading(0, 0.0, 8.0, assumed=True), reading(0, 12.0, -8.0, assumed=True)]
        tracker.update(first)
        self.assertEqual({s.velocity_mps for s in tracker._tracks.values()}, {(0, 0, 0)})

    def test_missing_sensor_position_gives_no_seed(self) -> None:
        tracker = NearestNeighborTracker()
        detection = reading(0, 0.0, 8.0)
        detection = Detection(
            time=detection.time, position_m=detection.position_m, velocity_mps=None,
            power=1.0, radial_speed_mps=8.0,
        )
        tracker.update([detection])
        self.assertEqual(tracker._tracks["t1"].velocity_mps, (0, 0, 0))

    def test_detection_with_its_own_velocity_ignores_the_seed(self) -> None:
        tracker = NearestNeighborTracker()
        detection = reading(0, 0.0, 8.0)
        detection = Detection(
            time=detection.time, position_m=detection.position_m, velocity_mps=(1.0, 0.0, 0.0),
            power=1.0, source_meta=detection.source_meta, radial_speed_mps=8.0,
        )
        ((_, out),) = tracker.update([detection])
        self.assertEqual(out.velocity_mps, (1.0, 0.0, 0.0))
        self.assertEqual(tracker._tracks["t1"].velocity_mps, (1.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
