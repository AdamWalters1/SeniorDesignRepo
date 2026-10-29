
import { useEffect, useState } from 'react'
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Circle,
  Tooltip,
  ScaleControl,
  Polyline,
} from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

const CAMPUS_CENTER = [37.2275, -80.4225]
const INITIAL_ZOOM = 17
const SCENE_ORIGIN = [37.2284, -80.4234]

export default function MapView({
  onSelectUAS,
  currentFrame,
  onFramesLoaded,
  onTracksUpdated,
}) {
  const [allPoints, setAllPoints] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/tracks')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Unable to load tracking data')
        }
        return response.json()
      })
      .then((data) => {
        const points = data.tracks.flatMap(track => track.points)

        setAllPoints(points)

        // Count unique simulation timestamps
        const timestamps = [
          ...new Set(points.map((point) => point.time)),
        ].sort()

        onFramesLoaded(timestamps.length)
      })
      .catch((err) => setError(err.message))
  }, [onFramesLoaded])

  // All available simulation timestamps
  const timestamps = [
    ...new Set(allPoints.map((point) => point.time)),
  ].sort()

  // Current playback timestamp
  const currentTime = timestamps[currentFrame]

  // Positions of all UAS at the selected timestamp
  const currentTracks = allPoints.filter(
    (point) => point.time === currentTime
  )

  useEffect(() => {
    onTracksUpdated(currentTracks)
  }, [allPoints, currentFrame, onTracksUpdated])

  // Flight paths up to the selected timestamp
  const visiblePaths = {}

  for (const point of allPoints) {
    if (currentTime && point.time <= currentTime) {
      if (!visiblePaths[point.track_id]) {
        visiblePaths[point.track_id] = []
      }

      visiblePaths[point.track_id].push([
        point.lat,
        point.lng,
      ])
    }
  }

  return (
    <MapContainer
      center={CAMPUS_CENTER}
      zoom={INITIAL_ZOOM}
      minZoom={14}
      maxZoom={19}
      className="map"
    >
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        maxZoom={19}
      />

      <ScaleControl position="bottomleft" imperial={false} />

      {/* Radar origin */}
      <CircleMarker
        center={SCENE_ORIGIN}
        radius={6}
        pathOptions={{
          color: '#f97316',
          fillColor: '#f97316',
          fillOpacity: 0.9,
        }}
      >
        <Tooltip>Scene origin (radar reference)</Tooltip>
      </CircleMarker>

      {/* Position uncertainty circles */}
      {currentTracks.map((track) => (
        <Circle
          key={`uncertainty-${track.track_id}`}
          center={[track.lat, track.lng]}
          radius={track.uncertainty_m}
          pathOptions={{
            color: '#2563eb',
            fillColor: '#60a5fa',
            fillOpacity: 0.12,
            weight: 1.5,
            dashArray: '5, 5',
          }}
        />
      ))}

      {/* Simulated UAS positions */}
      {currentTracks.map((track) => (
        <CircleMarker
          key={track.track_id}
          center={[track.lat, track.lng]}
          radius={8}
          eventHandlers={{
            click: () => onSelectUAS(track),
          }}
          pathOptions={{
            color: '#2563eb',
            fillColor: '#2563eb',
            fillOpacity: 0.9,
          }}
        >
          <Tooltip permanent direction="top">
            {track.track_id}
          </Tooltip>
        </CircleMarker>
      ))}

      {/* Flight paths */}
      {Object.entries(visiblePaths).map(([trackId, positions]) => (
        <Polyline
          key={trackId}
          positions={positions}
          pathOptions={{
            color: '#1d4ed8',
            weight: 5,
            opacity: 1,
          }}
        />
      ))}
    </MapContainer>
  )
}
