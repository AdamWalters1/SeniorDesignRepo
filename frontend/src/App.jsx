import MapView from './components/MapView.jsx'
import './App.css'

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>VT UAS Airspace Monitor</h1>
        <span className="badge">SIMULATION</span>
      </header>
      <main className="app-map">
        <MapView />
      </main>
    </div>
  )
}