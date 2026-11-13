# Architecture

This file shows how the pieces of the repo connect: who calls whom, and what passes between them. The exact fields of every file and message are in [INTERFACES.md](INTERFACES.md). Setup and run steps are in the [README](../README.md) and [SETUP.md](../SETUP.md).

**Keep this file current.** Update it in the same pull request as any change that adds, removes, or renames a module, changes who calls whom, or changes a file or message. The table at the bottom says which part to update. The diagrams are text (Mermaid). GitHub draws them, and a change to a diagram shows up in the pull request like any other change. To preview one while editing, paste it into <https://mermaid.live>.

## 1. The system

```mermaid
flowchart LR
    subgraph IN["Input files"]
        L["Local frames JSON"]
        R["Radar frames JSON<br/>from tools/radar_intake.py"]
        G["Geocoded points JSON"]
    end
    subgraph MW["middleware (Python, standard library only)"]
        ING["ingest"] --> ASC["associate"] --> GEO["geocode"] --> UNC["uncertainty"]
    end
    T[("build/normalized_tracks.json")]
    PUB["publish"]
    OA["OAuth server<br/>port 8085"]
    SP["mock Service Provider<br/>port 8081"]
    DSS["InterUSS DSS"]
    API["dashboard_api<br/>FastAPI, port 8000"]
    FE["frontend<br/>React and Leaflet, port 5173"]
    L --> ING
    R --> ING
    UNC --> T
    G --> T
    T --> PUB
    PUB --> OA
    PUB --> SP
    SP --> DSS
    T --> API
    API --> FE
    FE -. planned: discover and poll .-> SP
```

Geocoded input is already latitude and longitude, so it skips `associate`, `geocode`, and `uncertainty` and goes straight to the track file. The dotted line is designed but not built: today the frontend reads the track file through the dashboard API, not InterUSS.

## 2. Design names and code

The design documents and slides use the names in the left column.

| Design name | Code | Folder or file |
|---|---|---|
| Sensing intake | Readers for each input shape and the source metadata reader | `middleware/ingest/` (`synthetic.py` for local and geocoded files, `sionna.py` for radar) |
| Track builder | Tracker, coordinate conversion, uncertainty, run in order by the pipeline | `middleware/associate/tracker.py`, `middleware/geocode/wgs84.py`, `middleware/uncertainty/estimate.py`, `middleware/pipeline.py` |
| USS publisher | Track file writer and the InterUSS injection | `middleware/publish/mock_uss.py` |
| Dashboard API | Serves the track file to the map | `dashboard_api/` |
| Frontend | The map | `frontend/` |
| Radar input tool | Runs HermesPy and writes a radar input file | `tools/radar_intake.py` |

`middleware/publish/interuss_adapter.py` and `interuss_demo.py` are an earlier prototype payload. `--publish` does not use them.

## 3. What each module does

Each has one job.

| Module | Job | Reads | Gives back |
|---|---|---|---|
| `ingest/synthetic.py` | Read local or geocoded files, build `SourceMeta`, skip invalid readings | Input file | `DetectionFrame` list or `TrackPoint` list |
| `ingest/sionna.py` | Read radar range and power, place each reading on the map | Radar file | `DetectionFrame` list |
| `associate/tracker.py` | Give detections track ids, estimate speed | Detections of one frame | `(track_id, Detection)` pairs |
| `geocode/wgs84.py` | East, north, up metres to latitude, longitude, altitude | Position and scene origin | `GeoPoint` |
| `uncertainty/estimate.py` | Estimate uncertainty from power, compute range resolution from bandwidth | Power or bandwidth | Metres |
| `pipeline.py` | Run the steps in order, build `TrackPoint`s, write the file, optionally publish | Command line arguments | Track file |
| `publish/mock_uss.py` | Write the track file, build and send the injection | `TrackPoint` list | Track file, sandbox reply |
| `dashboard_api/` | Group the track file by track and serve it | Track file, scene origin | JSON for the frontend |
| `frontend/` | Draw positions, paths, and uncertainty, play back by time | Dashboard API | The map |

## 4. A pipeline run

```mermaid
sequenceDiagram
    actor Op as Operator
    participant PL as pipeline.py
    participant IN as ingest
    participant TR as associate tracker
    participant GE as geocode
    participant UN as uncertainty
    participant WR as publish write_track_points
    Op->>PL: python -m middleware.pipeline input with format and origin
    PL->>IN: loader(input_path, issues)
    loop each reading
        alt valid reading
            IN->>IN: build Detection with source_meta
        else invalid reading
            IN->>IN: skip_reading logs it and adds it to issues
        end
    end
    IN-->>PL: frames
    loop each frame
        PL->>TR: update(frame.detections)
        TR-->>PL: track_id and detection pairs
        PL->>GE: local_to_wgs84(position_m, origin)
        GE-->>PL: GeoPoint
        alt detection already has uncertainty_m
            Note over PL: keep it (radar range resolution)
        else no uncertainty yet
            PL->>UN: estimate_uncertainty_m(power)
            UN-->>PL: metres
        end
    end
    PL->>WR: write_track_points(points, output)
```

## 5. Publishing to InterUSS

```mermaid
sequenceDiagram
    participant PL as pipeline.py
    participant PU as publish mock_uss
    participant OA as OAuth server port 8085
    participant SP as mock Service Provider port 8081
    participant DSS as InterUSS DSS
    PL->>PU: publish_tracks(points, test_id, lead_s, include_metadata)
    PU->>PU: shift_to_future(points, lead_s)
    PU->>PU: build_injection_body(points)
    Note right of PU: one flight per track, one extra point if the flight has no area, accuracy class from uncertainty
    PU->>OA: GET /token with scope rid.inject_test_data
    OA-->>PU: access_token
    PU->>SP: PUT /ridsp/injection/tests/test_id with Bearer token
    SP->>DSS: registers the ISA (inside the sandbox)
    SP-->>PU: injected_flights
    PU-->>PL: reply
```

## 6. Showing tracks on the map

```mermaid
sequenceDiagram
    participant FE as frontend in the browser
    participant API as dashboard_api
    participant FS as file_source
    participant F as normalized_tracks.json
    loop every 5 seconds
        FE->>API: GET /api/status
        API-->>FE: ok, server_time, tracks_file_found
    end
    FE->>API: GET /api/tracks when the map loads
    API->>FS: load_tracks_file(tracks_path, origin_path)
    FS->>F: read
    F-->>FS: points
    FS-->>API: origin, tracks, skipped_points
    alt track file is missing
        API-->>FE: 404
    else file has no points list
        API-->>FE: 422
    else file is good
        API-->>FE: 200 with tracks
    end
    loop each second of playback
        FE->>FE: draw positions, paths, and uncertainty circles for the current time
    end
```

The Vite dev server forwards requests that start with `/api` to port 8000.

## 7. Data types

```mermaid
classDiagram
    class DetectionFrame {
        +str time
        +list detections
    }
    class Detection {
        +datetime time
        +tuple position_m
        +tuple velocity_mps
        +float power
        +str sensor_id
        +float uncertainty_m
    }
    class SourceMeta {
        +str sensor_id
        +str sensor_type
        +str signal_type
        +float carrier_frequency_hz
        +float bandwidth_hz
        +float range_resolution_m
        +tuple sensor_position_m
        +bool sensor_position_assumed
        +describe() str
    }
    class GeoPoint {
        +float lat
        +float lng
        +float alt_m
    }
    class TrackPoint {
        +str track_id
        +datetime time
        +float speed_mps
        +float heading_deg
        +float vertical_speed_mps
        +float uncertainty_m
        +str source
        +to_dict() dict
    }
    class NearestNeighborTracker {
        +int max_tracks
        +float gate_m
        +float smoothing
        +update(detections) list
    }
    DetectionFrame --> Detection : holds many
    Detection --> SourceMeta : optional
    SourceMeta --> GeoPoint : sensor_position_wgs84, optional
    TrackPoint --> GeoPoint : position
    TrackPoint --> SourceMeta : optional
    NearestNeighborTracker ..> Detection : reads
```

## 8. Not built yet

- Reading Sionna output. Today the input is a HermesPy radar file, a local frames file, or a geocoded file.
- The frontend finding the Service Provider through the DSS and polling it. Today it reads the track file.
- A real DSS client. The sandbox injection route is the publish path.
- Direction from a single radar. Each range is placed straight north.
- Using Doppler speed in the tracker. Speed comes from position changes.

## 9. Which file to update

| You changed | Update |
|---|---|
| A field in an input file or the track file | `INTERFACES.md` (the section for that file), and the data types diagram above |
| An HTTP call or the API response | `INTERFACES.md` (sections 4 and 5), and the matching sequence diagram |
| Who calls whom, or the order of steps | The matching sequence diagram, and the table in section 3 |
| A new module, folder, or top-level file | The table in section 3, the system diagram, and the README layout |
| A feature that is now built | Remove it from section 8, and draw its line solid in section 1 |
