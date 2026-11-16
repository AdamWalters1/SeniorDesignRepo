# tools/radar_intake.py

Runs one fixed HermesPy FMCW radar scenario and writes the raw detections to JSON.
The middleware reads that file with `--format radar`.

The scenario: one small UAS moves straight away from the radar at 3 m/s, from 40 m to 70 m,
with one reading per second (11 readings). Each reading is range and power only.

## Setup

HermesPy needs Python 3.12 (not 3.14). Use a separate environment from the middleware,
which has no dependencies.

```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install hermespy==1.6.0 numpy==2.4.6
```

## Run

Run it from the folder where you want `radar_detections.json` to appear.

```
python tools/radar_intake.py
```

It prints true range, measured range and error for each frame, then writes
`radar_detections.json`. The run is repeatable because each frame uses `seed=k`.

To feed the middleware:

```
python -m middleware.pipeline radar_detections.json --format radar --origin scenarios/campus_origin.json --output build/radar_tracks.json
```

## What it matches

The output is byte for byte the same as `data/hermespy/radar_fmcw_11s.json`.

## Settings you can change

The constants at the top of the script: start range, range rate, number of frames,
frame period. Keep the end range under about 75 m. Past that the detector locks onto noise.

The radar settings (`num_chirps`, `chirp_duration`, `pulse_rep_interval`) need care.
With 3 chirps the radar cannot measure speed. With more chirps some `pulse_rep_interval`
values give a wrong range because of a sample rounding mismatch in HermesPy 1.6.0.
The script prints a WARNING when your settings hit it.

## Sensor block written to the file

`id`, `type`, `signal_type`, `carrier_frequency_hz`, `bandwidth_hz`, `range_resolution_m`.
The radar position is not written because the simulation has no position.
The middleware assumes (0, 0, 25) m east, north, up and marks it as assumed.

## Doppler (speed) findings

The Doppler study compared FMCW, OFDM and OTFS in HermesPy 1.6.0 with equal bandwidth and
listening time. This script keeps the 3-chirp setting so `data/hermespy/radar_fmcw_11s.json`
stays reproducible. It reads range only. For speed, use these settings instead:

- FMCW needs `chirp_duration = pulse_rep_interval` and many chirps (the study used 64).
- Chirp spacing sets the largest speed that does not wrap. 100 us wraps above 31.25 m/s,
  50 us wraps above 62.5 m/s. Drones fly up to 44.7 m/s (FAA Part 107), so use 50 us.
- HermesPy returns FMCW speed with the opposite sign to the tracker. Flip it on intake.
- OFDM and OTFS give identical results in HermesPy. They search speeds on a grid
  (`velocity_resolution`, default 1 m/s) and the run time grows with the number of speeds tried.
- Telling two aircraft apart depends on listening time. About 6.4 ms separates speeds 1 m/s apart.
- Distance accuracy depends on bandwidth. 93 MHz gave about 0.1 m (OFDM), 11.6 MHz about 1.2 m.
- Each HermesPy trial leaks about 0.6 to 1 GB of memory. Run each trial in its own process.


# tools/sionna_scene_run.py

Flies drones through the campus Sionna scene and writes radar detections for the middleware
(`--format local`, the default). It is the first step of the demo chain: scene, detections,
tracks, map.

What comes from where:

- **Sionna ray tracing:** which drones the radar can see (buildings block the view), the
  direction each echo arrives from, the echo delay (range) and the Doppler shift (radial speed).
- **The Doppler study:** the measurement error. Range 0.11 m and speed 0.4 m/s for OFDM,
  0.59 m and 0.5 m/s for FMCW (`--waveform`). Sionna itself has no noise.
- **Assumptions, marked in the script:** radar power, antenna gain and noise figure (they set
  how far the radar sees), and a 1 degree angle error (the study had no angle).

## Setup

Sionna needs its own Python environment, separate from the middleware and HermesPy.

```
python -m venv .venv-sionna
.venv-sionna/bin/pip install sionna-rt numpy
```

The scene is not in this repo. It is `scenes/vt_campus/burrus-test-3.xml` plus its `meshes/`
folder in the S27-50 working folder.

## Run

```
python tools/sionna_scene_run.py scenarios/campus_2drone_10s.json --scene <path>/burrus-test-3.xml \
  --output build/sionna_detections.json --truth-output build/sionna_truth.json
python -m middleware.pipeline build/sionna_detections.json --origin scenarios/campus_origin.json --output build/sionna_tracks.json
```

Takes about 12 s for 11 frames. The same seed gives the same output on the same machine.
`data/sionna/campus_2drone_10s.json` (two aircraft that cross paths) is the result with the
defaults. To check the script still reproduces it, run the tests with
`SIONNA_SCENE=<path>/burrus-test-3.xml` set. Positions are compared to 1 cm because exact bytes
can differ between GPUs and drivers.

The scenario file lists the drones (start position, constant velocity in scene metres, x east,
y north, z up), the frame period and the start time.

## Choices that were tested

| Choice | Setting | Why |
|---|---|---|
| Carrier | 24 GHz | Sionna stops at 40 GHz (70 GHz fails). 24 GHz is what the Doppler study and `radar_intake.py` use |
| Drone | Sphere, radius 0.15 m, scattering 0.3 | About -18 dBsm. Small quadcopters measure about -20 to -15 dBsm at K band |
| Ray tracing | Depth 1, diffuse only, 10 million rays | Specular on with depth 2 found the drone in 2 of 6 runs, with 0 to 3 paths. This setting found it in 6 of 6, with 11 paths every time. 100 thousand rays found it in 0 of 30 |
| Not HermesPy's Sionna channel | Calls Sionna directly | HermesPy's channel switches diffuse reflection off, so a drone never shows up in it |
| Echo cluster | Same 10.7 ns delay cell and 5 degrees | Echoes the radar could not separate become one detection |
| Moving only | Radial speed of 1 m/s or more | If buildings scatter, their static returns are about 29 dB above a drone's. The Doppler study's speed grid is 1 m/s |
| Scene check | 60 random points | A direct line-of-sight test and the Sionna echo agreed on every point (23 blocked, 37 seen) |

## What the demo should expect

- **Radial speed is not velocity.** Doppler gives only the speed toward or away from the radar.
  The file carries it as `radial_speed_mps` and leaves out `velocity_mps`, so the tracker
  estimates velocity from position changes, as it does for radar input. Velocity error against
  the truth, mean over three noise seeds: 0.96 m/s (OFDM) and 1.08 m/s (FMCW). The speed number
  alone is within about 0.3 m/s. The rest is sideways error from the assumed 1 degree angle error,
  which Doppler cannot see. Writing the radial speed as a velocity vector gave 3.5 m/s on the
  saved file. Joining Doppler (toward or away) with position (sideways) was no better than position
  alone (1.06 and 1.10 m/s), because range changes are already precise. The toward-or-away part
  alone: position 0.08 m/s and Doppler 0.32 m/s (OFDM), 0.36 and 0.39 (FMCW).
- **Doppler seeds the first prediction.** A new track has no earlier point, so without help it
  predicts "not moving". With the Doppler speed along the line of sight it predicts the second
  point better. Simulated tracker test, 400 runs per case, 1 s between updates (swaps are
  places where a track jumps to the other aircraft, and the numbers are without and with the seed):
  two aircraft starting 8 to 18 m apart, 133 and 74 swaps, 7.3 and 5.7 m miss. Three random
  aircraft, 11 and 9 swaps. Random pairs, 1 and 1. Aircraft moving across the line of sight, no
  change, since Doppler reads near zero. At 2 s between updates the gain is about twice as large.
  The seed is never reported as the track's speed, and the next update replaces it.
- **Gaps.** An aircraft moving across the line of sight has almost no radial speed and drops
  out. The two aircraft case was chosen so that neither does.
- **Position error is about 1 to 1.5 m, 4.4 m at worst.** About 0.5 m is there even with no noise (the echo comes off
  the sphere's surface). The rest is the assumed 1 degree angle error, 1.2 m sideways at 70 m,
  which is bigger than the range difference between FMCW and OFDM.
- **No building clutter or multipath.** The buildings only block the view. Giving them a
  scattering coefficient adds strong static returns, which the Doppler gate removes, but
  Sionna's default limit of 1 million paths per run can then drop drone echoes. Not used.
- **The detection numbers are assumptions.** Replace the radar power, gain, noise figure and
  threshold with the real radar's before quoting a detection range.
