# SeniorDesignRepo

Team **S27-50** — publishing ISAC (or synthetic) tracks through InterUSS so a dashboard can display them. This is a data-compatibility pipeline, not a rewrite of Sionna, HermesPy, or InterUSS, and not a Remote ID implementation.

## Layout
How the pieces connect is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Every file and message format is in [docs/INTERFACES.md](docs/INTERFACES.md). Frontend and dashboard API details are in [frontend/README.md](frontend/README.md).

```
middleware/          Pipeline we write (Python, standard library only)
  models.py          Shared types: Detection, TrackPoint, GeoPoint, SourceMeta
  pipeline.py        Wires ingest → associate → geocode → uncertainty → track file → publish
  ingest/            Reads input files: local metres, HermesPy radar frames, geocoded points
  associate/         Nearest-neighbor tracker: up to 3 tracks, 25 m gate, speed from position change
  geocode/           Local x/y/z + scene origin → lat/lng/alt
  uncertainty/       Position uncertainty (radar keeps its range resolution, other input is estimated from power)
  publish/           mock_uss.py writes the track file and PUTs the injection to the sandbox
                     interuss_adapter.py is a prototype payload converter used by interuss_demo.py, not by --publish
dashboard_api/       FastAPI service that serves build/normalized_tracks.json to the map
frontend/            React and Leaflet map (see frontend/README.md)
tools/               radar_intake.py runs HermesPy and writes a radar input file (see tools/README.md)
data/hermespy/       radar_fmcw_11s.json = HermesPy FMCW range and power, with a sensor block
data/synthetic/      hermes_pointcloud_10s.json = HermesPy-like local metres
                     campus_3track_10s.json = after geocode (lat/lng), for publish tests
                     example_track.json = single-point smoke test
scenarios/           campus_origin.json = scene origin (WGS84) used to geocode local metres
tests/               Unit tests, run with: python -m unittest discover -s tests
docs/                ARCHITECTURE.md (how the pieces connect) and INTERFACES.md (every file and message format)
.github/             Pull request checklist: update the docs when a file, call, or module changes
```

Sionna, HermesPy, and InterUSS stay outside this repo. Talk to them through adapters.

## Data flow

```
input file (local metres, HermesPy radar, or geocoded)
   →  ingest → associate → geocode → uncertainty  →  build/normalized_tracks.json
                                                      →  publish  →  InterUSS mock_uss
                                                      →  dashboard API  →  map
```

Internal contract (not Remote ID): `track_id`, UTC `time`, `lat`/`lng`/`alt`, optional speed/heading, `uncertainty`, `source`, and an optional `source_meta` block that says which sensor the point came from. Every field is listed in [docs/INTERFACES.md](docs/INTERFACES.md).

A reading with a missing or invalid field is skipped and logged as `Skipped reading: ...`. It never becomes a track and the run continues. The pipeline prints how many were skipped. Geocoded input is not covered yet: a bad point there stops the run.

## Build order

1. Models + a synthetic file
2. `publish/mock_uss.py` so one point appears in InterUSS
3. Ingest → publish
4. Geocode, uncertainty, then association for up to 3 aircraft
5. Dashboard last (can poll mock_uss display data)

## Run the current pipeline

Machine setup, including the InterUSS sandbox, is in [SETUP.md](SETUP.md).

From the repository root:

```bash
python -m middleware.pipeline data/synthetic/hermes_pointcloud_10s.json \
  --origin scenarios/campus_origin.json \
  --output build/normalized_tracks.json

python -m middleware.pipeline data/hermespy/radar_fmcw_11s.json \
  --format radar \
  --origin scenarios/campus_origin.json \
  --publish

python -m unittest discover -s tests
```

The radar input file comes from `tools/radar_intake.py`, which needs HermesPy (see [tools/README.md](tools/README.md)). `data/hermespy/radar_fmcw_11s.json` is its output.

`--publish` writes the JSON file and also PUTs the tracks to the local
mock Service Provider at `http://localhost:8081`. Sample timestamps are shifted
so the first one starts two minutes in the future, because the DSS rejects a
past start time. Each run uses a new test id. The sandbox from
`interuss/monitoring` must already be running.

`--no-metadata-in-report` leaves the one-line source description out of the published flight details.
