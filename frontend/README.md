# VT UAS Airspace Monitor — Frontend

## 1. Overview

The VT UAS Airspace Monitor is a React-based dashboard developed for Virginia Tech Senior Design Team S27-50. It visualizes simulated Uncrewed Aircraft System (UAS) tracking data on an interactive map centered around the Virginia Tech campus.

The frontend displays drone positions, flight paths, estimated position uncertainty, and flight information. Users can select individual drones and use playback controls to observe movement over time.

The dashboard is built using React, Vite, and React-Leaflet, with a Python FastAPI backend providing tracking data.

## 2. Project Structure

The main frontend files are:

```text
frontend/
├── public/
├── src/
│   ├── components/
│   │   └── MapView.jsx
│   ├── App.jsx
│   ├── App.css
│   └── main.jsx
├── package.json
├── vite.config.js
└── README.md
```

**Important files:**

- `App.jsx` — Main application component. Manages selected drones, playback controls, timeline state, and backend connection status.
- `components/MapView.jsx` — Displays the interactive map, drone markers, flight paths, uncertainty circles, and altitude legend.
- `App.css` — Controls the dashboard layout, colors, styling, and map saturation.
- `main.jsx` — Entry point for the React application.
- `vite.config.js` — Configures Vite and forwards API requests to the FastAPI backend.
- `package.json` — Contains frontend dependencies and development scripts.

## 3. Prerequisites

Install the following software before running the dashboard:

- Node.js and npm
- Python 3.11 or a compatible Python version
- Required Python dependencies for the FastAPI backend

Docker Desktop and Ubuntu WSL2 are additionally required when running the local InterUSS environment. They are not required for the default file-based dashboard.

Clone the Senior Design repository using Git and navigate to the repository root before running the setup commands. All paths in this README are relative to the repository unless otherwise specified.

## 4. Running the Dashboard

The following instructions assume the user has cloned the Senior Design repository onto their local machine.

All backend and middleware commands should be executed from the repository root directory (the folder containing middleware/, dashboard_api/, and frontend/).

Step 1: Generate Tracking Data

Open a terminal and navigate to the repository root.

Run:

python -m middleware.pipeline data/synthetic/hermes_pointcloud_10s.json --origin scenarios/campus_origin.json

This processes the synthetic sensing data and generates the normalized tracking file:

build/normalized_tracks.json

The file contains drone positions, timestamps, speeds, headings, altitudes, and estimated position uncertainty.

This step can be skipped if the normalized tracking file already exists.

Step 2: Start the FastAPI Backend

From the repository root, install the backend dependencies:

python -m pip install -r dashboard_api/requirements.txt

Start the FastAPI server:

python -m uvicorn dashboard_api.app:app --reload --port 8000

The backend will run at:

http://localhost:8000

To verify that the backend is running, open:

http://localhost:8000/api/status

Keep this terminal running while using the dashboard.

Step 3: Start the React Frontend

Open a second terminal and navigate to the frontend/ directory within the cloned repository:

cd frontend

Install the frontend dependencies:

npm install

Start the Vite development server:

npm run dev

The frontend will typically be available at:

http://localhost:5173

Open this address in a web browser to access the VT UAS Airspace Monitor.

Step 4: Verify the Dashboard

Once both servers are running, the dashboard should display:

An interactive map centered around Virginia Tech.

Simulated drone positions with altitude-based marker colors.

Drone flight paths and position uncertainty circles.

A panel showing information about the selected drone.

Playback controls for viewing drone movement over time.

A backend connection indicator.

The frontend communicates with FastAPI through the Vite development proxy.

Note: The default dashboard uses normalized tracking data stored locally. Running the InterUSS environment is optional for file-based visualization and is only required when testing InterUSS API integration.

## 5. Frontend Features

### Interactive Map

The dashboard uses React-Leaflet and OpenStreetMap to display drone locations around Virginia Tech.

Users can zoom and pan around the map. The radar reference location is also marked.

### Drone Markers and Altitude Colors

Each drone is represented by a colored circular marker with its track ID.

Marker colors are determined by altitude using the `getAltitudeColor()` function in `MapView.jsx`.

| Altitude | Marker Color |
|---|---|
| Below 730 m | Green |
| 730–759 m | Orange |
| 760 m and above | Red |
| Missing or invalid altitude | Gray |

These are demonstration-specific visualization thresholds, not official aviation safety classifications. The current altitude values are absolute altitudes, not heights above ground level.

An altitude legend appears in the bottom-right corner of the map.

### Reduced Map Saturation

The OpenStreetMap basemap has reduced color saturation to make drone markers more visible.

This is implemented in `App.css` using a CSS filter applied to the Leaflet tile pane. Drone markers and other vector overlays retain their original colors.

### Flight Paths

The dashboard draws polylines connecting historical positions for each drone.

As playback advances, the displayed flight paths extend to reflect the positions available up to the selected timestamp.

### Position Uncertainty

Each drone's estimated position uncertainty is displayed as a circle centered on its reported location.

The uncertainty is calculated by the middleware and included in the normalized tracking data as `uncertainty_m`.

The frontend uses this value as the radius, in meters, of a Leaflet `Circle`.

The frontend does not calculate uncertainty itself.

### Selected UAS Information

Clicking a drone marker selects that aircraft and displays its information in the details panel.

Displayed fields include:

- Track ID
- Latitude and longitude
- Altitude
- Speed
- Heading
- Position uncertainty
- Timestamp
- Data source, when available

The selected drone's information updates as playback progresses.

### Playback Controls

The dashboard supports:

- Play and Pause
- Restart
- Timeline slider
- Current frame and total frame count

Playback advances through the unique timestamps available in the loaded tracking data.

The current file-based simulation contains 11 frames and 3 drone tracks.

## 6. API Interactions

The React frontend communicates with the Python FastAPI backend through HTTP requests.

### FastAPI Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/status` | Returns backend status, server timestamp, and whether the normalized track file exists |
| `GET /api/tracks` | Retrieves drone tracks from the local JSON file by default |
| `GET /api/tracks?source=file` | Explicitly retrieves file-based tracks |
| `GET /api/tracks?source=interuss` | Retrieves current simulated drone positions from the InterUSS mock Service Provider |

### Backend Status

`App.jsx` requests `/api/status` periodically to determine whether the backend is available.

The dashboard displays a connection indicator in the header.

### Tracking Data

`MapView.jsx` requests:

```javascript
fetch('/api/tracks')
```

FastAPI returns a JSON response containing tracks grouped by `track_id`.

Example response structure:

```json
{
  "source": "file",
  "tracks": [
    {
      "track_id": "t1",
      "points": [
        {
          "track_id": "t1",
          "time": "2026-09-29T18:00:00Z",
          "lat": 37.2284,
          "lng": -80.4234,
          "alt": 750,
          "speed_mps": 8,
          "heading_deg": 0,
          "uncertainty_m": 30,
          "source": "synthetic"
        }
      ]
    }
  ]
}
```

This example illustrates the response structure; actual values depend on the generated tracking data.

The frontend flattens the grouped points, extracts unique timestamps, and determines which drone positions and paths should appear at the current playback frame.

### Vite Proxy

The frontend development server runs on port `5173`, while FastAPI runs on port `8000`.

`vite.config.js` configures a proxy that forwards requests beginning with `/api` to:

`http://127.0.0.1:8000`

This allows React to use relative API paths such as `/api/tracks` without hardcoding the backend URL throughout the frontend.

## 7. InterUSS Integration

The Senior Design project also integrates with InterUSS, which provides a simulated Remote ID environment.

The middleware can publish normalized drone tracks to the InterUSS mock Remote ID Service Provider.

The relevant API interactions include:

| API | Endpoint | Purpose |
|---|---|---|
| OAuth | `GET localhost:8085/token` | Obtain an access token |
| Remote ID injection | `PUT localhost:8081/ridsp/injection/tests/{test_id}` | Publish simulated drone tracking data |
| Remote ID flight retrieval | `GET localhost:8081/mock/ridsp/v2/uss/flights` | Retrieve flights within a geographic area |

The backend module `dashboard_api/sources/interuss_source.py` requests an OAuth token, retrieves flights from InterUSS, and converts the results into the dashboard's track format.

To test InterUSS-backed retrieval, start the InterUSS services as described in the repository's `SETUP.md`.

Then publish synthetic data from the repository root:

```powershell
python -m middleware.pipeline data/synthetic/hermes_pointcloud_10s.json --origin scenarios/campus_origin.json --publish
```

Retrieve the published flight data through FastAPI:

`http://localhost:8000/api/tracks?source=interuss`

**Current integration status:** InterUSS publishing and flight retrieval have been tested successfully. FastAPI supports the InterUSS data source, but the React frontend still requests file-based tracking data by default.

InterUSS currently supplies individual current drone positions through this integration, rather than the complete historical point sequence used for frontend playback.

## 8. Important Functions and State

### `MapView.jsx`

**`getAltitudeColor(altitude)`**

Returns a marker color based on the drone's altitude.

**`onSelectUAS(track)`**

Notifies the parent application when a user selects a drone marker.

**`onFramesLoaded(count)`**

Notifies the parent application how many unique simulation timestamps are available.

**`onTracksUpdated(currentTracks)`**

Passes the currently displayed drone positions to the parent application so the selected UAS details can be updated.

**`currentTracks`**

Contains the drone positions corresponding to the selected playback timestamp.

**`visiblePaths`**

Groups historical positions by track ID and builds the flight paths visible at the selected timestamp.

### `App.jsx`

The main application manages:

- Selected drone state
- Current playback frame
- Total frame count
- Play/Pause state
- Backend connection status

It coordinates the map, selected UAS details, and playback controls.

## 9. Troubleshooting

**Dashboard shows a backend connection error**

Verify FastAPI is running on port `8000` and that `/api/status` is accessible.

**Map loads but no drones appear**

Check that `build/normalized_tracks.json` exists and that `/api/tracks` returns tracking data.

**InterUSS returns an empty tracks array**

The injected simulated flights may be outside their observation window. Publish a new test and retrieve the flights again.

**React development server does not start**

Run `npm install` from the `frontend/` directory and verify that Node.js and npm are installed.

**Map tiles do not appear**

Check the internet connection and verify that OpenStreetMap tile requests are loading.

## 10. Current Limitations and Future Improvements

- The React frontend currently uses file-based tracking data by default.
- InterUSS-backed tracking is implemented in FastAPI but has not yet been connected to the React display.
- Full playback is supported using historical file-based data; the current InterUSS adapter returns only current positions.
- The InterUSS adapter does not yet populate numerical uncertainty values.
- Altitude color thresholds are currently fixed for the demonstration dataset.
- The current dashboard uses simulated data rather than live physical radar measurements.

Planned improvements include completing the InterUSS-to-React connection, supporting refreshed tracking data, improving altitude visualization, and expanding end-to-end testing.

---

**Virginia Tech Senior Design — Team S27-50**