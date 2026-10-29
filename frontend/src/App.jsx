
import { useState, useEffect } from 'react'
import MapView from './components/MapView.jsx'
import './App.css'

export default function App() {
  const [selectedUAS, setSelectedUAS] = useState(null)
  const [currentTracks, setCurrentTracks] = useState([])
  const [currentFrame, setCurrentFrame] = useState(0)
  const [totalFrames, setTotalFrames] = useState(1)
  const [isPlaying, setIsPlaying] = useState(false)
  const [backendConnected, setBackendConnected] = useState(false)

  const displayedUAS = selectedUAS 
    ? currentTracks.find(
      (track) => track.track_id === selectedUAS.track_id
      )
    : null


  useEffect(() => {
    const checkBackend = async () => {
      try {
        const response = await fetch('/api/status')
        if (!response.ok) {
          throw new Error('Backend unavailable')
        }

        const data = await response.json()
        setBackendConnected(data.ok === true)
      } catch (error) {
        setBackendConnected(false)
      }
    }

    checkBackend()

    const interval = setInterval(checkBackend, 5000)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (!isPlaying) return

    const timer = setInterval(() => {
      setCurrentFrame((previous) => {
        if (previous >= totalFrames - 1) {
          setIsPlaying(false)
          return previous
        }

        return previous + 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [isPlaying, totalFrames])

  return (
    <div className="app">
      <header className="app-header">
        <h1>VT UAS Airspace Monitor</h1>

        <div className="header-status">
          <span className="badge">SIMULATION</span>

          <span className={backendConnected ? 'status-connected ' : 'status-disconnected'}>
            {backendConnected ? '● Backend Connected' : '● Backend Disconnected'}
            </span>
          </div>
      </header>

      <main className="app-content">
        <div className="app-main">

          {/* Interactive Map */}
          <div className="app-map">
            <MapView
              onSelectUAS={setSelectedUAS}
              currentFrame={currentFrame}
              onFramesLoaded={setTotalFrames}
              onTracksUpdated={setCurrentTracks}
            />
          </div>

          {/* Selected UAS Panel */}
          <aside className="uas-panel">
            <h2>Selected UAS</h2>

            {displayedUAS ? (
              <div className="uas-details">
                <h3>Track {displayedUAS.track_id}</h3>

                <p><strong>Latitude:</strong> {displayedUAS.lat.toFixed(6)}°</p>
                <p><strong>Longitude:</strong> {displayedUAS.lng.toFixed(6)}°</p>
                <p><strong>Speed:</strong> {displayedUAS.speed_mps} m/s</p>
                <p><strong>Heading:</strong> {displayedUAS.heading_deg}°</p>
                <p><strong>Altitude:</strong> {displayedUAS.alt} m</p>
                <p><strong>Uncertainty:</strong> {displayedUAS.uncertainty_m} m</p>
                <p><strong>Timestamp:</strong> {displayedUAS.time}</p>

                <button onClick={() => setSelectedUAS(null)}>
                  Clear Selection
                </button>
              </div>
            ) : (
              <p className="uas-empty">
                Click a UAS marker on the map to view its information.
              </p>
            )}
          </aside>

        </div>

        {/* Playback Controls - Below Map and Panel */}
        <div className="playback-controls">
          <button onClick={() => setIsPlaying(!isPlaying)}>
            {isPlaying ? 'Pause' : 'Play'}
          </button>

          <button
            onClick={() => {
              setIsPlaying(false)
              setCurrentFrame(0)
            }}
          >
            Restart
          </button>

          <input
            type="range"
            min="0"
            max={Math.max(0, totalFrames - 1)}
            value={currentFrame}
            onChange={(e) => {
              setIsPlaying(false)
              setCurrentFrame(Number(e.target.value))
            }}
          />

          <span>
            Frame {currentFrame + 1} / {totalFrames}
          </span>
        </div>

      </main>
    </div>
  )
}
