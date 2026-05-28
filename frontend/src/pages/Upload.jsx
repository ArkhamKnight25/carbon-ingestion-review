import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

const SOURCES = [
  { v: 'SAP_FUEL', label: 'SAP fuel movements (MB51 CSV)', sample: '/samples/sap_fuel_sample.csv' },
  { v: 'UTILITY_ELEC', label: 'Utility electricity (portal CSV)', sample: '/samples/utility_electricity_sample.csv' },
  { v: 'TRAVEL', label: 'Corporate travel (Navan-style CSV)', sample: '/samples/travel_sample.csv' },
]

export default function Upload() {
  const nav = useNavigate()
  const [source, setSource] = useState('SAP_FUEL')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setErr(''); setResult(null); setBusy(true)
    try {
      const r = await api.upload(file, source)
      setResult(r)
    } catch (e) {
      setErr(e.message + (e.data?.existing_batch_id ? ` (batch #${e.data.existing_batch_id})` : ''))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <h2>Ingest a file</h2>

      <form onSubmit={submit} className="form-card">
        <label>Source type</label>
        <select value={source} onChange={e => setSource(e.target.value)}>
          {SOURCES.map(s => <option key={s.v} value={s.v}>{s.label}</option>)}
        </select>

        <label>CSV file</label>
        <input type="file" accept=".csv,.txt" onChange={e => setFile(e.target.files[0])} required />

        {err && <div className="error">{err}</div>}
        <button disabled={busy || !file} type="submit">
          {busy ? 'Parsing…' : 'Upload & parse'}
        </button>
      </form>

      {result && (
        <div className="result-card">
          <h3>Batch #{result.id} — {result.status}</h3>
          <p>
            <strong>{result.success_count}</strong> records parsed,{' '}
            <strong>{result.error_count}</strong> errors
          </p>
          {result.parse_errors && result.parse_errors.length > 0 && (
            <details>
              <summary>Parse errors ({result.parse_errors.length})</summary>
              <table className="table">
                <thead><tr><th>Row</th><th>Field</th><th>Message</th></tr></thead>
                <tbody>
                  {result.parse_errors.map((e, i) => (
                    <tr key={i}><td>{e.row}</td><td><code>{e.field}</code></td><td>{e.message}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
          <button onClick={() => nav(`/review/${result.id}`)}>Review records →</button>
        </div>
      )}

      <div className="samples-card">
        <h3>Sample CSVs</h3>
        <p className="muted" style={{ margin: '0 0 12px' }}>
          Download a realistic sample for each source type. Each file exercises happy-path
          and edge cases (negative quantities, missing plant codes, unknown materials,
          zero-kWh meters, unrecognized IATA codes, missing distances, outliers).
        </p>
        <ul className="samples-list">
          {SOURCES.map(s => (
            <li key={s.v}>
              <span className="tag">{s.v}</span>
              <a href={s.sample} download>{s.sample.split('/').pop()}</a>
              <button className="link" type="button" onClick={() => setSource(s.v)}>Use this</button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
