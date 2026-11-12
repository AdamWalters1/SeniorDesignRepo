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
