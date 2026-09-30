"""Simple demo of converting middleware aircraft data into a USS payload."""

import json
from pathlib import Path

from middleware.ingest.synthetic import load_track_points
from middleware.publish.interuss_adapter import build_injection_payload


# Loads example aircraft tracking data
points = load_track_points("data/synthetic/campus_3track_10s.json")

# Converts the tracking data into our prototype USS payload
payload = build_injection_payload(points)

# Chooses where the output will be saved
output_path = Path("build/interuss_payload.json")

# Creates the build folder if it does not exist
output_path.parent.mkdir(parents=True, exist_ok=True)

# Saves the payload as JSON
with output_path.open("w", encoding="utf-8") as file:
    json.dump(payload, file, indent=2)

print(f"Converted {len(points)} tracking points.")
print(f"USS prototype payload saved to: {output_path}")