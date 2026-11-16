"""Fly drones through the campus Sionna scene and write radar detections for the pipeline.

Sionna ray tracing supplies the environment: what the radar can see (buildings block
the view), the direction each echo arrives from, and the Doppler shift. The radar
measurement error comes from the Doppler study (see tools/README.md), not from Sionna.
Output is a `--format local` file. No prompts and no plots.

    python tools/sionna_scene_run.py scenarios/campus_2drone_10s.json --scene <path>/burrus-test-3.xml
"""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

C = 299_792_458.0

# --- Sensor (same radar as tools/radar_intake.py and the Doppler study) ---------------
SENSOR_ID = "bs1"
SENSOR_POS_M = np.array([-17.0, 4.0, 19.0])  # scene metres, from the Sionna notebooks
RX_OFFSET_M = 0.5            # receive antenna sits this far east of transmit (Sionna needs two points)
POLARIZATION = "V"           # PlanarArray polarization in build_scene, vertical
CARRIER_HZ = 24e9            # Sionna accepts up to 40 GHz. 24 GHz matches the Doppler study
BANDWIDTH_HZ = 1024 * 90.909e3
OBSERVE_S = 6.4e-3           # listening time per frame in the Doppler study

# --- Drone stand-in: a metal sphere --------------------------------------------------
# Sphere radius 0.15 m with scattering coefficient 0.3 gives about -18 dBsm in Sionna.
# Published small-quadcopter figures at K band are about -20 to -15 dBsm.
DRONE_SCALE = 0.15
DRONE_SCATTERING = 0.3

# --- Ray tracing ---------------------------------------------------------------------
# Depth 1, diffuse only. With specular on or depth above 1 the drone echo was lost in
# most runs (0 to 3 paths against a steady 11). HermesPy's own Sionna channel turns
# diffuse off, so it cannot see the drone at all. That is why this calls Sionna directly.
SAMPLES_PER_SRC = 10_000_000

# --- Detection (ASSUMPTIONS. Replace with the real radar's numbers) -------------------
TX_POWER_DBM = 20.0
ANTENNA_GAIN_DBI = 20.0      # each of transmit and receive
NOISE_FIGURE_DB = 6.0
DETECT_SNR_DB = 13.0
MIN_SPEED_MPS = 1.0          # slower than this is treated as static (a hovering drone is invisible)
ANGLE_CELL_DEG = 5.0         # echoes closer than this in angle and range share one detection

# --- Measurement error added to Sionna's exact values ---------------------------------
# Range and speed error are the Doppler study results at B = 93 MHz and 6.4 ms.
# Angle error is an assumption. The study had no angle measurement.
NOISE = {
    "ofdm": {"range_m": 0.11, "speed_mps": 0.4},
    "fmcw": {"range_m": 0.59, "speed_mps": 0.5},
}
ANGLE_SIGMA_DEG = 1.0


def build_scene(scene_path):
    import sionna.rt as rt
    from sionna.rt import ITURadioMaterial, PlanarArray, Receiver, SceneObject, Transmitter
    import sionna.rt.scene as scene_assets

    scene = rt.load_scene(str(scene_path))
    scene.frequency = CARRIER_HZ
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization=POLARIZATION)
    scene.rx_array = scene.tx_array
    scene.add(Transmitter("tx", SENSOR_POS_M.tolist()))
    scene.add(Receiver("rx", (SENSOR_POS_M + [RX_OFFSET_M, 0.0, 0.0]).tolist()))
    material = ITURadioMaterial(
        name="drone-material", itu_type="metal", thickness=0.01,
        scattering_coefficient=DRONE_SCATTERING,
    )
    return scene, material, SceneObject, scene_assets.sphere


def add_drones(scene, material, scene_object, mesh, ids):
    scene.edit(add=[scene_object(fname=mesh, name=f"drone-{i}", radio_material=material) for i in ids])
    for i in ids:
        scene.objects[f"drone-{i}"].scaling = DRONE_SCALE


def trace(scene, seed):
    """Return moving paths as arrays: delay (s), doppler (Hz), power, unit vector toward source."""
    import sionna.rt as rt

    paths = rt.PathSolver()(
        scene, max_depth=1, los=True, specular_reflection=False, diffuse_reflection=True,
        refraction=False, samples_per_src=SAMPLES_PER_SRC, seed=seed,
    )
    tau = np.array(paths.tau).ravel()
    a = np.array(paths.a)
    power = (a[0] ** 2 + a[1] ** 2).ravel()
    doppler = np.array(paths.doppler).ravel()
    theta = np.array(paths.theta_r).ravel()
    phi = np.array(paths.phi_r).ravel()
    keep = (np.array(paths.valid).ravel() > 0) & (tau > 0)
    unit = np.stack([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)], axis=1)
    return tau[keep], doppler[keep], power[keep], unit[keep]


def cluster(tau, doppler, power, unit):
    """Merge echoes that one radar could not tell apart. Strongest echo first."""
    wavelength = C / CARRIER_HZ
    moving = np.abs(doppler) * wavelength / 2 >= MIN_SPEED_MPS
    idx = list(np.nonzero(moving)[0][np.argsort(-power[moving])])
    cos_cell = math.cos(math.radians(ANGLE_CELL_DEG))
    out = []
    while idx:
        lead = idx[0]
        members = [j for j in idx
                   if abs(tau[j] - tau[lead]) <= 1.0 / BANDWIDTH_HZ and unit[j] @ unit[lead] >= cos_cell]
        idx = [j for j in idx if j not in members]
        w = power[members]
        direction = (unit[members] * w[:, None]).sum(axis=0)
        out.append({
            "delay_s": float((tau[members] * w).sum() / w.sum()),
            "doppler_hz": float((doppler[members] * w).sum() / w.sum()),
            "power": float(w.sum()),
            "unit": direction / np.linalg.norm(direction),
        })
    return out


def snr_db(echo_power):
    noise_dbm = -174.0 + 10 * math.log10(BANDWIDTH_HZ) + NOISE_FIGURE_DB
    gain_db = 10 * math.log10(BANDWIDTH_HZ * OBSERVE_S)
    return TX_POWER_DBM + 2 * ANTENNA_GAIN_DBI + 10 * math.log10(echo_power) - noise_dbm + gain_db


def run(scenario, scene_path, waveform="ofdm", seed=1, noise=True):
    rng = np.random.default_rng(seed)
    scene, material, scene_object, mesh = build_scene(scene_path)
    drones = scenario["drones"]
    add_drones(scene, material, scene_object, mesh, [d["id"] for d in drones])
    start = datetime.fromisoformat(scenario["start_time"].replace("Z", "+00:00"))
    wavelength = C / CARRIER_HZ
    sigma = NOISE[waveform]
    frames, truth = [], []

    for k in range(scenario["num_frames"]):
        t = k * scenario["frame_period_s"]
        frame_truth = {}
        for d in drones:
            pos = np.array(d["start_m"], float) + np.array(d["velocity_mps"], float) * t
            obj = scene.objects[f"drone-{d['id']}"]
            obj.position = pos.tolist()
            obj.velocity = list(map(float, d["velocity_mps"]))
            frame_truth[d["id"]] = {"position_m": pos.tolist(), "velocity_mps": list(d["velocity_mps"])}

        detections = []
        for echo in cluster(*trace(scene, seed + k)):
            level = snr_db(echo["power"])
            if level < DETECT_SNR_DB:
                continue
            range_m = C * echo["delay_s"] / 2
            speed = -wavelength * echo["doppler_hz"] / 2  # positive means moving away
            unit = echo["unit"]
            if noise:
                range_m += rng.normal(0, sigma["range_m"])
                speed += rng.normal(0, sigma["speed_mps"])
                unit = _jitter(unit, rng)
            detections.append({
                "position_m": (SENSOR_POS_M + range_m * unit).tolist(),
                "radial_speed_mps": float(speed),
                "power": float(10 ** (level / 10)),
            })
        stamp = (start + timedelta(seconds=t)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        frames.append({"time": stamp, "detections": detections})
        truth.append({"time": stamp, "drones": frame_truth})

    document = {
        "description": "Sionna scene echoes: range, direction and Doppler from ray tracing, "
                       "measurement error from the Doppler study.",
        "units": {"position": "m", "radial_speed": "m/s, positive away from the sensor"},
        "sensor": {
            "id": SENSOR_ID, "type": "radar", "signal_type": waveform.upper(),
            "carrier_frequency_hz": CARRIER_HZ, "bandwidth_hz": BANDWIDTH_HZ,
            "position_m": SENSOR_POS_M.tolist(),
            # Same values build_scene gives Sionna: one transmit antenna at the sensor
            # position and one receive antenna RX_OFFSET_M east of it. Offsets are
            # measured from the sensor position.
            "antenna_array": {
                "layout": "1x1 TX + 1x1 RX",
                "num_elements": 2,
                "tx_elements": [0],
                "rx_elements": [1],
                "polarization": POLARIZATION,
                "element_positions_m": [[0.0, 0.0, 0.0], [RX_OFFSET_M, 0.0, 0.0]],
            },
        },
        "axes": "x=east, y=north, z=up, origin at scene origin (not the antenna)",
        "frames": frames,
    }
    return document, truth


def _jitter(unit, rng):
    """Tilt a unit vector by a random angle with the configured standard deviation."""
    azimuth = math.atan2(unit[1], unit[0]) + math.radians(rng.normal(0, ANGLE_SIGMA_DEG))
    zenith = math.acos(np.clip(unit[2], -1, 1)) + math.radians(rng.normal(0, ANGLE_SIGMA_DEG))
    return np.array([math.sin(zenith) * math.cos(azimuth), math.sin(zenith) * math.sin(azimuth), math.cos(zenith)])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("scenario", type=Path, help="scenario JSON (drones, frames, start time)")
    parser.add_argument("--scene", type=Path, required=True, help="Sionna scene XML, for example burrus-test-3.xml")
    parser.add_argument("--output", type=Path, default=Path("sionna_detections.json"))
    parser.add_argument("--truth-output", type=Path, help="also write the true drone positions")
    parser.add_argument("--waveform", choices=sorted(NOISE), default="ofdm", help="picks the measurement error")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--no-noise", action="store_true", help="write Sionna's exact values")
    args = parser.parse_args()

    document, truth = run(json.loads(args.scenario.read_text()), args.scene, args.waveform, args.seed, not args.no_noise)
    args.output.write_text(json.dumps(document, indent=1))
    if args.truth_output:
        args.truth_output.write_text(json.dumps(truth, indent=1))
    counts = [len(f["detections"]) for f in document["frames"]]
    print(f"Wrote {args.output}: {len(counts)} frames, detections per frame {counts}")


if __name__ == "__main__":
    main()
