# SeniorDesignRepo

Team **S27-50** — publishing ISAC (or synthetic) tracks through InterUSS so a dashboard can display them. This is a data-compatibility pipeline, not a rewrite of Sionna, HermesPy, or InterUSS, and not a Remote ID implementation.

## Layout

```
middleware/          Pipeline we write (Python)
  models.py          Shared Detection and Track types
  pipeline.py        Wires ingest → geocode → associate → uncertainty → publish
  ingest/            Synthetic files now; Sionna later
  geocode/           Local x/y/z + scene origin → lat/lng/alt
  associate/         Optional: keep up to 3 tracks (stretch)
  uncertainty/       Attach a position-uncertainty estimate
  publish/           InterUSS mock_uss first; other adapters later
data/synthetic/      Files we own (two shapes)
                     hermes_pointcloud_10s.json = HermesPy-like local metres
                     campus_3track_10s.json = after geocode (lat/lng), for publish tests
                     example_track.json = single-point smoke test
scenarios/           Scene origin (WGS84) used to geocode local metres
scenarios/           Scene origin and 1–3 vehicle paths
tests/
```

Sionna, HermesPy, and InterUSS stay outside this repo. Talk to them through adapters.

## Data flow

```
synthetic JSON or Sionna  →  ingest → geocode → associate
                          →  uncertainty → publish  →  InterUSS mock_uss
                                                    →  dashboard user
```

Internal contract (not Remote ID): `track_id`, UTC `time`, `lat`/`lng`/`alt`, optional speed/heading, `uncertainty`, `source`.

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

`--publish` writes the JSON file and also PUTs the tracks to the local
mock Service Provider at `http://localhost:8081`. Sample timestamps are shifted
so the first one starts two minutes in the future, because the DSS rejects a
past start time. Each run uses a new test id. The sandbox from
`interuss/monitoring` must already be running.
