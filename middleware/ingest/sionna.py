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

from dataclasses import replace
from math import hypot
from pathlib import Path

from middleware.ingest.synthetic import (
    DetectionFrame,
    _read_json,
    read_frame_time,
    read_number,
    read_power,
    read_source_meta,
    skip_reading,
)
from middleware.models import Detection

DEFAULT_SENSOR_POSITION_M = (0.0, 0.0, 25.0)
DEFAULT_BORESIGHT_ENU = (0.0, 1.0, 0.0)  # facing north


def load_radar_detection_frames(
    path: str | Path,
    *,
    sensor_position_m: tuple[float, float, float] | None = None,
    boresight_enu: tuple[float, float, float] = DEFAULT_BORESIGHT_ENU,
    issues: list[str] | None = None,
) -> list[DetectionFrame]:
    """Load range/power frames and return local-metre detection frames.

    A reading with a missing or null field, a negative range or a
    non-positive power is skipped and logged. It never becomes a track. Pass a
    list as ``issues`` to collect the messages.
    """
    length = hypot(boresight_enu[0], boresight_enu[1])
    if length == 0:
        raise ValueError("Boresight must have a horizontal component")
    direction = (boresight_enu[0] / length, boresight_enu[1] / length)

    document = _read_json(path)
    source_meta = read_source_meta(
        document.get("sensor"), issues, default_position_m=DEFAULT_SENSOR_POSITION_M
    )
    if sensor_position_m is not None:
        # An explicit argument beats the file and the default.
        source_meta = replace(
            source_meta, sensor_position_m=tuple(sensor_position_m), sensor_position_assumed=False
        )
    sensor_position_m = source_meta.sensor_position_m
    sensor_id = source_meta.sensor_id
    uncertainty_m = source_meta.range_resolution_m
    frames: list[DetectionFrame] = []
    for frame_index, raw_frame in enumerate(document.get("frames", [])):
        time = read_frame_time(raw_frame, frame_index, issues)
        if time is None:
            continue
        detections = []
        for item_index, item in enumerate(raw_frame.get("detections", [])):
            try:
                if not isinstance(item, dict):
                    raise ValueError("reading is not an object")
                range_m = read_number(item, "range_m")
                if range_m < 0:
                    raise ValueError(f"range must not be negative, got {range_m!r}")
                detections.append(
                    Detection(
                        time=time,
                        position_m=(
                            sensor_position_m[0] + range_m * direction[0],
                            sensor_position_m[1] + range_m * direction[1],
                            sensor_position_m[2],
                        ),
                        velocity_mps=None,
                        power=read_power(item),
                        sensor_id=sensor_id,
                        uncertainty_m=uncertainty_m,
                        source_meta=source_meta,
                    )
                )
            except ValueError as error:
                skip_reading(issues, f"frame {frame_index} reading {item_index}: {error}")
        frames.append(DetectionFrame(raw_frame["time"], detections))
    if not frames:
        raise ValueError(f"{path} contains no detection frames")
    return frames
