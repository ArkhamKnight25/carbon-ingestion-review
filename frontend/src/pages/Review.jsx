import { Fragment, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api.js'

const STATUSES = ['', 'pending', 'flagged', 'approved', 'rejected', 'locked']

export default function Review() {
  const { batchId } = useParams()
  const [records, setRecords] = useState([])
  const [err, setErr] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [scopeFilter, setScopeFilter] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [modal, setModal] = useState(null) // {id, action}
  const [note, setNote] = useState('')

  async function refresh() {
    try {
      const params = {}
      if (batchId) params.batch = batchId
      if (statusFilter) params.status = statusFilter
      if (scopeFilter) params.scope = scopeFilter
      const r = await api.records(params)
      setRecords(r.results || r)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { refresh() }, [batchId, statusFilter, scopeFilter])

  async function act(id, action) {
    try {
      if (action === 'approve') await api.approve(id, note)
      else if (action === 'reject') await api.reject(id, note)
      else if (action === 'flag') await api.flag(id, 'manual_flag', note)
      setModal(null); setNote('')
      await refresh()
    } catch (e) { setErr(e.message) }
  }

  return (
    <div className="page">
      <h2>Review {batchId ? `— batch #${batchId}` : ''}</h2>

      <div className="filters">
        <label>Status</label>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          {STATUSES.map(s => <option key={s} value={s}>{s || 'all'}</option>)}
        </select>
        <label>Scope</label>
        <select value={scopeFilter} onChange={e => setScopeFilter(e.target.value)}>
          <option value="">all</option>
          <option value="1">1</option><option value="2">2</option><option value="3">3</option>
        </select>
        <button className="link" onClick={refresh}>Refresh</button>
      </div>

      {err && <div className="error">{err}</div>}

      <table className="table">
        <thead>
          <tr>
            <th></th><th>Row</th><th>Scope</th><th>Category</th><th>Period</th>
            <th>Quantity</th><th>kgCO₂e</th><th>Facility</th><th>Status</th><th>Flags</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {records.map(r => (
            <Fragment key={r.id}>
              <tr className={`row row-${r.status}`}>
                <td>
                  <button className="link" onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                    {expanded === r.id ? '▾' : '▸'}
                  </button>
                </td>
                <td>#{r.source_row_number}</td>
                <td>{r.scope}</td>
                <td><code>{r.category}</code></td>
                <td>{r.activity_start} → {r.activity_end}</td>
                <td>{Number(r.quantity_normalized).toLocaleString()} {r.unit_normalized}</td>
                <td>{Number(r.co2e_kg).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                <td>{r.facility_name || '—'}</td>
                <td><span className={`pill pill-${r.status}`}>{r.status}</span></td>
                <td>{(r.flags || []).map(f => <span key={f} className="flag">{f}</span>)}</td>
                <td>
                  {r.status !== 'locked' && (
                    <>
                      <button className="link ok" onClick={() => setModal({ id: r.id, action: 'approve' })}>✓</button>
                      <button className="link warn" onClick={() => setModal({ id: r.id, action: 'flag' })}>⚑</button>
                      <button className="link err" onClick={() => setModal({ id: r.id, action: 'reject' })}>✕</button>
                    </>
                  )}
                </td>
              </tr>
              {expanded === r.id && (
                <tr className="expand">
                  <td colSpan={11}>
                    <div className="expand-grid">
                      <div>
                        <h4>Raw source row</h4>
                        <pre>{JSON.stringify(r.raw_data, null, 2)}</pre>
                      </div>
                      <div>
                        <h4>Extra (source-specific)</h4>
                        <pre>{JSON.stringify(r.extra, null, 2)}</pre>
                        <p className="muted">Factor: {r.emission_factor_label || '—'}</p>
                        <p className="muted">Source: {r.source_type} — file: {r.batch_filename}</p>
                        {r.review_note && <p>Note: {r.review_note}</p>}
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {records.length === 0 && (
            <tr><td colSpan={11} className="muted">No records.</td></tr>
          )}
        </tbody>
      </table>

      {modal && (
        <div className="modal-bg" onClick={() => setModal(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>{modal.action} record #{modal.id}</h3>
            <label>Review note (optional)</label>
            <textarea value={note} onChange={e => setNote(e.target.value)} rows={4} />
            <div className="modal-actions">
              <button className="link" onClick={() => setModal(null)}>Cancel</button>
              <button onClick={() => act(modal.id, modal.action)}>Confirm</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
