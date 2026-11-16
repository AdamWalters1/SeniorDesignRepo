// Source sensor and antenna details for the selected UAS side panel.
// Every field is optional. A missing value shows as a dash, never as a blank or "null".
import {
  MISSING,
  formatElementList,
  formatInputType,
  formatPolarization,
  formatPositionAssumed,
  formatScaled,
  formatValue,
  formatVector,
} from '../utils/format.js'

function Row({ label, value }) {
  return (
    <p>
      <strong>{label}:</strong>{' '}
      <span className={value === MISSING ? 'uas-missing' : undefined}>{value}</span>
    </p>
  )
}

function elementRole(index, tx, rx) {
  const sends = Array.isArray(tx) && tx.includes(index)
  const listens = Array.isArray(rx) && rx.includes(index)
  if (sends && listens) return 'Sends+Listens'
  if (sends) return 'Sends'
  if (listens) return 'Listens'
  return MISSING
}

function ElementTable({ array }) {
  const positions = array?.element_positions_m
  if (!Array.isArray(positions) || positions.length === 0) return null
  return (
    <table className="element-table">
      <thead>
        <tr>
          <th>#</th>
          <th>East (m)</th>
          <th>North (m)</th>
          <th>Up (m)</th>
          <th>Role</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((position, index) => (
          <tr key={index}>
            <td>{index}</td>
            {[0, 1, 2].map((axis) => (
              <td key={axis}>{formatValue(position?.[axis], '', 2)}</td>
            ))}
            <td>{elementRole(index, array.tx_elements, array.rx_elements)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function SourceDetails({ point }) {
  const meta = point?.source_meta ?? null
  const array = meta?.antenna_array ?? null
  const wgs = meta?.sensor_position_wgs84 ?? null

  return (
    <>
      <h4 className="uas-section">Sensor that detected this aircraft</h4>
      <Row label="Input type" value={formatInputType(point?.source)} />
      <Row label="Sensor name" value={formatValue(meta?.sensor_id)} />
      <Row label="Sensor type" value={formatValue(meta?.sensor_type)} />
      <Row label="Waveform" value={formatValue(meta?.signal_type)} />
      <Row label="Carrier frequency" value={formatScaled(meta?.carrier_frequency_hz, 1e9, 'GHz', 2)} />
      <Row label="Bandwidth" value={formatScaled(meta?.bandwidth_hz, 1e6, 'MHz', 1)} />
      <Row label="Range resolution" value={formatValue(meta?.range_resolution_m, 'm', 2)} />
      <Row label="Sensor position (east, north, up)" value={formatVector(meta?.sensor_position_m, 'm')} />
      <Row label="Position assumed" value={formatPositionAssumed(meta?.sensor_position_assumed)} />
      <Row label="Sensor latitude" value={formatValue(wgs?.lat, '°', 6)} />
      <Row label="Sensor longitude" value={formatValue(wgs?.lng, '°', 6)} />
      <Row label="Sensor altitude" value={formatValue(wgs?.alt_m, 'm', 1)} />

      <h4 className="uas-section">Sensor antennas</h4>
      <Row label="Layout (rows x columns)" value={formatValue(array?.layout)} />
      <Row label="Elements" value={formatValue(array?.num_elements)} />
      <Row label="Sending elements (TX)" value={formatElementList(array?.tx_elements)} />
      <Row label="Listening elements (RX)" value={formatElementList(array?.rx_elements)} />
      <Row label="Polarization" value={formatPolarization(array?.polarization)} />
      {Array.isArray(array?.element_positions_m) && array.element_positions_m.length > 0 ? (
        <>
          <p>
            <strong>Element positions</strong> (from array center)
          </p>
          <ElementTable array={array} />
        </>
      ) : (
        <Row label="Element positions" value={MISSING} />
      )}
    </>
  )
}
