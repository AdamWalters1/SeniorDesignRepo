"""Load raw HermesPy radar detections and convert them to local detections.

HermesPy reports distance and power only. This adapter places each detection
on the scene map using two stated assumptions:

1. The radar sits at ``sensor_position_m`` (east, north, up in metres).
2. The target lies straight along ``boresight`` (the direction the radar faces)
   at the same height as the radar, so range is treated as horizontal distance.

A single radar has no angle measurement, so the second assumption is a
placeholder until angle data or a second sensor exists. HermesPy velocity is
not used because the current FMCW settings cannot resolve it, so velocity is
left as None and the tracker works it out from how the position changes.
"""

from __future__ import annotations

from math import hypot
from pathlib import Path

from middleware.ingest.synthetic import DetectionFrame, _read_json
from middleware.models import Detection, parse_utc
from middleware.uncertainty.estimate import range_resolution_m

DEFAULT_SENSOR_POSITION_M = (0.0, 0.0, 25.0)
DEFAULT_BORESIGHT_ENU = (0.0, 1.0, 0.0)  # facing north


def load_radar_detection_frames(
    path: str | Path,
    *,
    sensor_position_m: tuple[float, float, float] = DEFAULT_SENSOR_POSITION_M,
    boresight_enu: tuple[float, float, float] = DEFAULT_BORESIGHT_ENU,
) -> list[DetectionFrame]:
    """Load range/power frames and return local-metre detection frames."""
    length = hypot(boresight_enu[0], boresight_enu[1])
    if length == 0:
        raise ValueError("Boresight must have a horizontal component")
    direction = (boresight_enu[0] / length, boresight_enu[1] / length)

    document = _read_json(path)
    sensor = document.get("sensor", {})
    sensor_id = sensor.get("id", "unknown")
    uncertainty_m = (
        range_resolution_m(float(sensor["bandwidth_hz"]))
        if "bandwidth_hz" in sensor
        else None
    )
    frames: list[DetectionFrame] = []
    for raw_frame in document.get("frames", []):
        time = parse_utc(raw_frame["time"])
        detections = [
            Detection(
                time=time,
                position_m=(
                    sensor_position_m[0] + item["range_m"] * direction[0],
                    sensor_position_m[1] + item["range_m"] * direction[1],
                    sensor_position_m[2],
                ),
                velocity_mps=None,                
                power=float(item["power"]),
                sensor_id=sensor_id,
                uncertainty_m=uncertainty_m,
            )
            for item in raw_frame.get("detections", [])
        ]
        frames.append(DetectionFrame(raw_frame["time"], detections))
    if not frames:
        raise ValueError(f"{path} contains no detection frames")
    return frames