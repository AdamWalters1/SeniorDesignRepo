"""Fixed-scenario FMCW radar run that writes raw detections to JSON.

No prompts and no plots. One target moves away from the radar at a constant
speed and the radar measures it once per frame. Output is saved for the
senior design pipeline to read.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from hermespy.channel import SingleTargetRadarChannel
from hermespy.radar import FMCW, MaxDetector, Radar
from hermespy.simulation import SimulatedDevice

# Scenario settings (change these to change the test)
START_RANGE_M = 40.0      # target distance from the radar at frame 0
RANGE_RATE_MPS = 3.0      # m/s away from radar (keep end range under ~75 m)
NUM_FRAMES = 11           # number of measurements
FRAME_PERIOD_S = 1.0      # time between measurements
OUTPUT_PATH = Path("radar_detections.json")

# Radar settings (same as Fiona's FMCW option)
device = SimulatedDevice(
    carrier_frequency=24e9,
    bandwidth=1024 * 90.909e3,
    oversampling_factor=4,
)
radar = Radar()
radar.waveform = FMCW(num_chirps=3, chirp_duration=1e-6, pulse_rep_interval=1.1e-6)
radar.detector = MaxDetector()
device.add_dsp(radar)

# HermesPy 1.6.0 builds each pulse from two truncated sample counts but slices
# the received frame with a third. When they differ by one sample the chirps
# drift and the range comes out wrong (see tools/README.md). Warn if so.
_fs = device.bandwidth * device.oversampling_factor
_tx_len = int(radar.waveform.chirp_duration * _fs) + int(
    (radar.waveform.pulse_rep_interval - radar.waveform.chirp_duration) * _fs
)
_rx_len = int(radar.waveform.pulse_rep_interval * _fs)
if _tx_len != _rx_len:
    print(
        f"WARNING: pulse length mismatch ({_tx_len} sent vs {_rx_len} sliced). "
        "Ranges will drift. Change pulse_rep_interval slightly."
    )

start_time = datetime(2026, 10, 12, 18, 0, 0, tzinfo=timezone.utc)
frames = []
print(f"{'frame':>5} {'true range (m)':>15} {'measured (m)':>13} {'error (m)':>10}")

for k in range(NUM_FRAMES):
    t = k * FRAME_PERIOD_S
    true_range = START_RANGE_M + RANGE_RATE_MPS * t
    channel = SingleTargetRadarChannel(true_range, 1.0, attenuate=True, seed=k)
    reception = device.receive(channel.propagate(device.transmit(), device, device))
    cloud = reception.operator_receptions[0].cloud

    detections = [
        {
            "range_m": float(np.linalg.norm(point.position)),
            "power": float(point.power),
        }
        for point in cloud.points
    ]
    frames.append(
        {
            "time": (start_time + timedelta(seconds=t)).isoformat().replace("+00:00", "Z"),
            "true_range_m": true_range,
            "detections": detections,
        }
    )
    measured = detections[0]["range_m"] if detections else float("nan")
    print(f"{k:>5} {true_range:>15.2f} {measured:>13.2f} {measured - true_range:>10.2f}")

document = {
    "description": "Raw HermesPy FMCW detections: range and power only, one radar.",
    "sensor": {
        "id": "radar1",
        "type": "radar",
        "signal_type": "FMCW",
        "carrier_frequency_hz": 24e9,
        "bandwidth_hz": device.bandwidth,
        "range_resolution_m": round(299_792_458.0 / (2 * device.bandwidth), 2),
    },
    "frames": frames,
}
# Write bytes so the file has LF line endings on every operating system.
OUTPUT_PATH.write_bytes((json.dumps(document, indent=2) + "\n").encode("utf-8"))
print(f"Wrote {len(frames)} frames to {OUTPUT_PATH}")