"""Small nearest-neighbor tracker for proof-of-concept scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from math import dist

from middleware.models import Detection


@dataclass
class _TrackState:
    position_m: tuple[float, float, float]
    velocity_mps: tuple[float, float, float]
    last_time_s: float


class NearestNeighborTracker:
    """Associate detections with at most ``max_tracks`` temporary IDs.

    This is intentionally simple and does not claim physical aircraft
    identification. It predicts each track with constant velocity and performs
    one-to-one nearest-neighbor matching inside a distance gate.
    """

    def __init__(self, max_tracks: int = 3, gate_m: float = 25.0) -> None:
        if max_tracks < 1 or gate_m <= 0:
            raise ValueError("max_tracks and gate_m must be positive")
        self.max_tracks = max_tracks
        self.gate_m = gate_m
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
            self._tracks[track_id] = _TrackState(
                detection.position_m,
                detection.velocity_mps,
                detection.time.timestamp(),
            )
            output.append((track_id, detection))
        return output
