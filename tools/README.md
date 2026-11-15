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
