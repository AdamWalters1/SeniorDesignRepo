"""Small nearest-neighbor tracker for proof-of-concept scenarios."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import dist, sqrt

from middleware.models import Detection


@dataclass
class _TrackState:
    position_m: tuple[float, float, float]
    velocity_mps: tuple[float, float, float]
    last_time_s: float
    seen: bool = False
    velocity_known: bool = False


class NearestNeighborTracker:
    """Associate detections with at most ``max_tracks`` temporary IDs.

    This is intentionally simple and does not claim physical aircraft
    identification. It predicts each track with constant velocity and performs
    one-to-one nearest-neighbor matching inside a distance gate.

    When a detection has no velocity of its own (``velocity_mps is None``), the
    tracker estimates it from how far the track moved since the last update.
    The first point of a track has no earlier point, so its reported velocity is
    zero. Later estimates are smoothed with ``smoothing`` (1.0 means no smoothing).

    When the first detection of a track carries a Doppler speed and the sensor
    position is given, the track predicts its second point with that speed along
    the line of sight, not with zero. Doppler sees only the toward or away part of
    the motion, so the seed is used for the first prediction only. It is never
    reported, and the next update replaces it with the change in position.
    """

    def __init__(
        self,
        max_tracks: int = 3,
        gate_m: float = 25.0,
        smoothing: float = 0.5,
    ) -> None:
        if max_tracks < 1 or gate_m <= 0:
            raise ValueError("max_tracks and gate_m must be positive")
        if not 0 < smoothing <= 1:
            raise ValueError("smoothing must be between 0 and 1")
        self.max_tracks = max_tracks
        self.gate_m = gate_m
        self.smoothing = smoothing
        self._tracks: dict[str, _TrackState] = {}
        self._next_id = 1

    def update(self, detections: list[Detection]) -> list[tuple[str, Detection]]:
        """Return confirmed ``(track_id, detection)`` assignments."""
        if not detections:
            return []

        candidates: list[tuple[float, str, int]] = []
        for track_id, state in self._tracks.items():
            for index, detection in enumerate(detections):
                dt = max(0.0, detection.time.timestamp() - state.last_time_s)
                predicted = tuple(
                    state.position_m[axis] + state.velocity_mps[axis] * dt
                    for axis in range(3)
                )
                distance = dist(predicted, detection.position_m)
                if distance <= self.gate_m:
                    candidates.append((distance, track_id, index))

        assignments: dict[int, str] = {}
        used_tracks: set[str] = set()
        for _, track_id, index in sorted(candidates):
            if index not in assignments and track_id not in used_tracks:
                assignments[index] = track_id
                used_tracks.add(track_id)

        for index in range(len(detections)):
            if index in assignments or len(self._tracks) >= self.max_tracks:
                continue
            track_id = f"t{self._next_id}"
            self._next_id += 1
            assignments[index] = track_id
            self._tracks[track_id] = _TrackState((0, 0, 0), (0, 0, 0), 0)

        output: list[tuple[str, Detection]] = []
        for index, track_id in sorted(assignments.items()):
            detection = detections[index]
            state = self._tracks[track_id]
            velocity = detection.velocity_mps
            velocity_known = True
            if velocity is None:
                velocity, velocity_known = self._estimate_velocity(state, detection)
            predict_velocity = velocity
            if detection.velocity_mps is None and not state.seen:
                predict_velocity = _doppler_seed(detection) or velocity
            detection = replace(detection, velocity_mps=velocity)
            self._tracks[track_id] = _TrackState(
                detection.position_m,
                predict_velocity,
                detection.time.timestamp(),
                seen=True,
                velocity_known=velocity_known,
            )
            output.append((track_id, detection))
        return output

    def _estimate_velocity(
        self, state: _TrackState, detection: Detection
    ) -> tuple[tuple[float, float, float], bool]:
        """Return ``(velocity, is_known)`` from the change since the last update."""
        dt = detection.time.timestamp() - state.last_time_s
        if not state.seen or dt <= 0:
            return (0.0, 0.0, 0.0), False
        raw = tuple(
            (detection.position_m[axis] - state.position_m[axis]) / dt
            for axis in range(3)
        )
        if not state.velocity_known:
            return raw, True
        blended = tuple(
            self.smoothing * raw[axis] + (1 - self.smoothing) * state.velocity_mps[axis]
            for axis in range(3)
        )
        return blended, True


def _doppler_seed(detection: Detection) -> tuple[float, float, float] | None:
    """Velocity along the sensor line of sight from a Doppler speed, or None."""
    meta = detection.source_meta
    if (
        detection.radial_speed_mps is None
        or meta is None
        or meta.sensor_position_m is None
        or meta.sensor_position_assumed
    ):
        return None
    offset = [detection.position_m[a] - meta.sensor_position_m[a] for a in range(3)]
    length = sqrt(sum(c * c for c in offset))
    if length == 0:
        return None
    scale = detection.radial_speed_mps / length
    return (offset[0] * scale, offset[1] * scale, offset[2] * scale)
