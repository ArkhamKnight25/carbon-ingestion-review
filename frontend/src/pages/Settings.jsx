import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Settings() {
  const [codes, setCodes] = useState([])
  const [facilities, setFacilities] = useState([])
  const [err, setErr] = useState('')
  const [code, setCode] = useState('')
  const [facilityId, setFacilityId] = useState('')

  async function refresh() {
    try {
      const c = await api.plantCodes()
      const f = await api.facilities()
      setCodes(c.results || c)
      setFacilities(f.results || f)
      if (!facilityId && (f.results || f).length) {
        setFacilityId(String((f.results || f)[0].id))
      }
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { refresh() }, [])

  async function add(e) {
    e.preventDefault()
    setErr('')
    try {
      await api.createPlantCode(code.trim().toUpperCase(), Number(facilityId))
      setCode('')
      await refresh()
    } catch (e) { setErr(e.message) }
  }

  async function remove(id) {
    if (!confirm('Delete this mapping?')) return
    try {
      await api.deletePlantCode(id)
      await refresh()
    } catch (e) { setErr(e.message) }
  }

  return (
    <div className="page">
      <h2>SAP plant code mapping</h2>
      <p className="muted">
        SAP plant codes (e.g. <code>BHM1</code>) resolve to a facility for grid-region and Scope 2 factor lookup.
        Records with unmapped plant codes are flagged <code>missing_facility</code> for analyst review.
      </p>

      <form onSubmit={add} className="form-card form-inline">
        <div>
          <label>Plant code</label>
          <input value={code} onChange={e => setCode(e.target.value)} placeholder="e.g. BHM2" required maxLength={8} />
        </div>
        <div>
          <label>Facility</label>
          <select value={facilityId} onChange={e => setFacilityId(e.target.value)} required>
            {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </div>
        <div>
          <label>&nbsp;</label>
          <button type="submit">Add mapping</button>
        </div>
      </form>

      {err && <div className="error">{err}</div>}

      <table className="table">
        <thead>
          <tr><th>Plant code</th><th>Facility</th><th></th></tr>
        </thead>
        <tbody>
          {codes.map(c => (
            <tr key={c.id}>
              <td><code>{c.plant_code}</code></td>
              <td>{c.facility_name}</td>
              <td><button className="link err" onClick={() => remove(c.id)}>Delete</button></td>
            </tr>
          ))}
          {codes.length === 0 && (
            <tr><td colSpan={3} className="muted">No mappings yet. Add one above.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
