import { MapContainer, TileLayer, CircleMarker, Tooltip, ScaleControl } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// Initial view: between Burruss Hall and the middle of the Drillfield.
const CAMPUS_CENTER = [37.2275, -80.4225]
const INITIAL_ZOOM = 17

// Must match scenarios/campus_origin.json: the point the middleware
// converts local east/north metres from. Later this will come from the API
// instead of being typed here.
const SCENE_ORIGIN = [37.2284, -80.4234]

export default function MapView() {
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

      <CircleMarker
        center={SCENE_ORIGIN}
        radius={6}
        pathOptions={{ color: '#f97316', fillColor: '#f97316', fillOpacity: 0.9 }}
      >
        <Tooltip>
          Scene origin (radar reference)
          <br />
          37.2284, -80.4234
        </Tooltip>
      </CircleMarker>
    </MapContainer>
  )
}