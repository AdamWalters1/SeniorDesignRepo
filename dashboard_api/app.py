"""Dashboard API: serves middleware track output to the React frontend.

Run from the repository root:
    python -m uvicorn dashboard_api.app:app --reload --port 8000
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

from dashboard_api.sources.file_source import load_tracks_file
from middleware.models import format_utc

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACKS_FILE = REPO_ROOT / "build" / "normalized_tracks.json"
ORIGIN_FILE = REPO_ROOT / "scenarios" / "campus_origin.json"

app = FastAPI(title="S27-50 Dashboard API")


@app.get("/api/status")
def get_status() -> dict:
    """Quick health check the frontend can show in its header."""
    return {
        "ok": True,
        "server_time": format_utc(datetime.now(timezone.utc)),
        "tracks_file_found": TRACKS_FILE.exists(),
    }


@app.get("/api/tracks")
def get_tracks() -> dict:
    """Return every track, grouped by track_id and sorted by time."""
    try:
        result = load_tracks_file(TRACKS_FILE, ORIGIN_FILE)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=f"{error.filename} not found. Run the middleware pipeline first.",
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"Bad track file: {error}") from error
    result["fetched_at"] = format_utc(datetime.now(timezone.utc))
    return result