# Interfaces

These are the files, messages, and functions that cross a module boundary. They are written from the code in this repo. If a field or a call changes, change this file in the same pull request. How the pieces connect is in [ARCHITECTURE.md](ARCHITECTURE.md).

Contents: [1 Input files](#1-input-files) | [2 Scene origin](#2-scene-origin-file) | [3 Track file](#3-track-file-output) | [4 Publish to InterUSS](#4-publish-to-interuss) | [5 Dashboard API](#5-dashboard-api) | [6 Python functions](#6-python-functions)

## 1. Input files

Every input is one JSON object. Times are ISO 8601 UTC with a timezone, for example `2026-09-29T18:00:00Z`. The pipeline chooses the reader with `--format`.

| `--format` | Reader | What the file holds |
|---|---|---|
| `local` (default) | `ingest/synthetic.py: load_detection_frames` | Frames of detections in local metres |
| `radar` | `ingest/sionna.py: load_radar_detection_frames` | Frames of HermesPy range and power |
| `geocoded` | `ingest/synthetic.py: load_track_points` | Finished latitude and longitude points |

### 1.1 Local frames (`--format local`)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `frames` | list | yes | One entry per time step. A file with no usable frames is rejected |
| `frames[].time` | text | yes | Frame time |
| `frames[].detections` | list | no | Readings in that frame |
| `...detections[].position_m` | `[x, y, z]` metres | yes | East, north, up, from the scene origin |
| `...detections[].velocity_mps` | `[x, y, z]` m/s | yes | Velocity |
| `...detections[].power` | number above 0 | yes | Detection power |
| `sensor` | object | no | See 1.4 |

### 1.2 Radar frames (`--format radar`)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `frames[].time` | text | yes | Frame time |
| `frames[].detections[].range_m` | number, 0 or more | yes | Distance from the radar in metres |
| `frames[].detections[].power` | number above 0 | yes | Detection power |
| `sensor` | object | no | See 1.4 |

The middleware does not read any other field, such as `true_range_m`. A single radar gives no angle, so the adapter places every reading straight north of the sensor at the sensor's height. The sensor position comes from `sensor.position_m`, or defaults to `(0, 0, 25)` metres (east, north, up) and is marked as assumed. Velocity is left empty and the tracker works it out from position changes.

### 1.3 Geocoded points (`--format geocoded`)

A `points` list. Each point needs `track_id`, `time`, `lat`, `lng`, `alt`. These are optional: `speed_mps` (default 0), `heading_deg`, `vertical_speed_mps` (default 0), `uncertainty_m` (default 100), `source` (default `synthetic`), `source_meta`. These points skip the tracker, the geocoder, and the uncertainty step. A point with a missing required field stops the run.

### 1.4 The `sensor` block

Describes where the readings came from. It is optional and every field in it is optional.

| Field | Type | Meaning |
|---|---|---|
| `id` | text | Sensor name. Default `unknown` |
| `type` | text | For example `radar` |
| `signal_type` | text | For example `FMCW` |
| `carrier_frequency_hz` | number above 0 | Carrier frequency |
| `bandwidth_hz` | number above 0 | Used to compute the range resolution, c / (2 x bandwidth) |
| `range_resolution_m` | number above 0 | Used only when `bandwidth_hz` is absent |
| `position_m` | `[x, y, z]` metres | Sensor position. If absent, the default above is used and flagged as assumed |

A field that is missing or invalid is ignored and logged. It never stops the run.

### 1.5 Skipped readings

A reading is skipped, logged as `Skipped reading: ...`, and never becomes a track when:

- it is not a JSON object
- `position_m` or `velocity_mps` is missing, not a list of three numbers, or holds a non-finite value (local)
- `range_m` is missing, null, not a number, not finite, or negative (radar)
- `power` is missing, null, not a number, or 0 or below

A whole frame is skipped when it is not an object, `time` is missing or not text, or `detections` is not a list. The run continues, and the pipeline prints how many readings were skipped.

## 2. Scene origin file

`scenarios/campus_origin.json` holds an `origin` object with `lat`, `lng`, and `alt_m` (WGS84). Local and radar positions are east, north, up from this point. `--origin` is required for `local` and `radar` input, and the run stops before writing any output without it.

## 3. Track file (output)

`build/normalized_tracks.json`:

```json
{
  "description": "Normalized middleware output; not UAV-provided identity.",
  "points": [ { "track_id": "t1", "time": "2026-10-12T18:00:00Z", "...": "..." } ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `track_id` | text | `t1`, `t2`, `t3`. Not an aircraft serial or registration |
| `time` | text | UTC time |
| `lat`, `lng` | degrees | WGS84 position |
| `alt` | metres | Altitude |
| `speed_mps` | number | Horizontal speed. 0 on a track's first point |
| `heading_deg` | number or null | Compass angle of horizontal velocity. Null when there is none |
| `vertical_speed_mps` | number | Vertical speed |
| `uncertainty_m` | number | Position uncertainty. Radar points keep the range resolution. Local points are estimated from power |
| `source` | text | Where the point came from |
| `source_meta` | object | Optional. Present when the input described its sensor |

`source_meta` fields: `sensor_id`, `sensor_type`, `signal_type`, `carrier_frequency_hz`, `bandwidth_hz`, `range_resolution_m`, `sensor_position_m`, `sensor_position_assumed` (true when the position was a default), and `sensor_position_wgs84` (`lat`, `lng`, `alt_m`).

## 4. Publish to InterUSS

Used by `--publish`. Defaults: mock Service Provider `http://localhost:8081`, token server `http://localhost:8085`.

1. **Token.** `GET {oauth}/token?grant_type=client_credentials&intended_audience=localhost&scope=rid.inject_test_data`. The reply holds `access_token`.
2. **Inject.** `PUT {mock_uss}/ridsp/injection/tests/{test_id}` with `Authorization: Bearer {token}` and `Content-Type: application/json`. A new `test_id` is made on each run.

Before sending, sample times are shifted so the first sample starts `--lead-seconds` (default 120) ahead of the clock, because the DSS rejects a start in the past. If a flight changes by less than 0.0001 degrees in latitude or longitude, one extra point is added 1 second after the last, because the DSS rejects an area with no width.

Request body, one entry per track:

```json
{ "requested_flights": [ {
    "injection_id": "t1",
    "telemetry": [ {
      "timestamp": "...", "timestamp_accuracy": 0.1,
      "operational_status": "Airborne",
      "position": { "lat": 0, "lng": 0, "alt": 0, "accuracy_h": "HA3m", "accuracy_v": "VAUnknown" },
      "track": 0, "speed": 0, "speed_accuracy": "SAUnknown", "vertical_speed": 0 } ],
    "details_responses": [ {
      "effective_after": "...",
      "details": { "id": "t1", "uas_id": { "utm_id": "t1" }, "operation_description": "..." } } ]
} ] }
```

- `operational_status` is `Airborne` when altitude is above 0, otherwise `Ground`.
- `track` is `heading_deg`, or 0 when the heading is null.
- `operation_description` holds the one-line source description (from `source_meta`). It is left out when there is no metadata or when `--no-metadata-in-report` is set.
- `accuracy_h` comes from `uncertainty_m` and is never tighter than the metre value:

| `uncertainty_m` | `accuracy_h` |
|---|---|
| 1 or less | `HA1m` |
| above 1, up to 3 | `HA3m` |
| above 3, up to 10 | `HA10m` |
| above 10, up to 30 | `HA30m` |
| above 30 | `HAUnknown` |

If the server answers with an error, the pipeline raises an error that includes the status code and the reply body. If nothing is listening on the port (for example the sandbox is not running), the connection error is raised as is. The track file has already been written by then.

`middleware/publish/interuss_adapter.py` builds a different, prototype payload. Only `interuss_demo.py` and the tests use it. `--publish` does not.

## 5. Dashboard API

FastAPI, started from the repo root with `python -m uvicorn dashboard_api.app:app --port 8000`. It reads `build/normalized_tracks.json` and `scenarios/campus_origin.json`. It never writes to them.

`GET /api/status` returns `{ "ok": true, "server_time": "...", "tracks_file_found": true }`.

`GET /api/tracks` returns:

```json
{
  "source": "file",
  "file": "normalized_tracks.json",
  "origin": { "lat": 37.2284, "lng": -80.4234, "alt_m": 630.0 },
  "tracks": [ { "track_id": "t1", "points": [ ] } ],
  "skipped_points": 0,
  "fetched_at": "..."
}
```

Each point has `track_id`, `time`, `lat`, `lng`, `alt`, `speed_mps`, `heading_deg`, `vertical_speed_mps`, `uncertainty_m`, `source`, and `source_meta`. A numeric field that is missing or not finite comes back as `null`. `source_meta` is `null` when the file point has none. A point without a valid `track_id`, `time`, `lat`, or `lng` is dropped and counted in `skipped_points`. Points are grouped by `track_id` and sorted by time.

Errors: `404` when the track file is missing (run the pipeline first), `422` when the file has no `points` list.

## 6. Python functions

| Function | Takes | Returns |
|---|---|---|
| `ingest.synthetic.load_detection_frames(path, *, issues=None)` | local file path, optional list that collects skip messages | `list[DetectionFrame]` |
| `ingest.sionna.load_radar_detection_frames(path, *, sensor_position_m=None, boresight_enu=(0, 1, 0), issues=None)` | radar file path | `list[DetectionFrame]` |
| `ingest.synthetic.load_track_points(path)` | geocoded file path | `list[TrackPoint]` |
| `ingest.synthetic.load_origin(path)` | origin file path | `GeoPoint` |
| `ingest.synthetic.read_source_meta(sensor, issues=None, *, default_position_m=None)` | a `sensor` block | `SourceMeta` |
| `associate.tracker.NearestNeighborTracker(max_tracks=3, gate_m=25.0, smoothing=0.5).update(detections)` | the detections of one frame | `list[(track_id, Detection)]` |
| `geocode.wgs84.local_to_wgs84(position_m, origin)` | east, north, up metres and a `GeoPoint` | `GeoPoint` |
| `uncertainty.estimate.estimate_uncertainty_m(power, ...)` | detection power | metres, between 3 and 100 by default |
| `uncertainty.estimate.range_resolution_m(bandwidth_hz)` | bandwidth in Hz | metres |
| `publish.mock_uss.write_track_points(points, path)` | `list[TrackPoint]`, output path | none. Writes the track file |
| `publish.mock_uss.publish_tracks(points, *, mock_uss_url, oauth_url, test_id, lead_s=120, include_metadata=True)` | `list[TrackPoint]` | the sandbox reply (`dict`) |
| `pipeline.process_local_detections(input_path, origin_path, *, max_tracks=3, gate_m=25.0, loader=..., announce=False)` | input and origin paths | `list[TrackPoint]` |

Data types are in `middleware/models.py`: `Detection`, `DetectionFrame`, `TrackPoint`, `GeoPoint`, `SourceMeta`.
