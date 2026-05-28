import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'

export default function Batches() {
  const [batches, setBatches] = useState([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(null)

  async function refresh() {
    try {
      const r = await api.batches()
      setBatches(r.results || r)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { refresh() }, [])

  async function lock(id) {
    setBusy(id); setErr('')
    try {
      await api.lockBatch(id)
      await refresh()
    } catch (e) { setErr(e.message) }
    finally { setBusy(null) }
  }

  return (
    <div className="page">
      <h2>Ingestion batches</h2>
      {err && <div className="error">{err}</div>}
      <table className="table">
        <thead>
          <tr>
            <th>#</th><th>File</th><th>Source</th><th>Status</th>
            <th>OK</th><th>Errors</th><th>Uploaded</th><th>By</th><th></th>
          </tr>
        </thead>
        <tbody>
          {batches.map(b => (
            <tr key={b.id}>
              <td>#{b.id}</td>
              <td>{b.filename}</td>
              <td><span className="tag">{b.source_type}</span></td>
              <td><span className={`pill pill-${b.status}`}>{b.status}</span></td>
              <td>{b.success_count}</td>
              <td className={b.error_count > 0 ? 'err' : ''}>{b.error_count}</td>
              <td>{new Date(b.uploaded_at).toLocaleString()}</td>
              <td>{b.uploaded_by_username || '—'}</td>
              <td>
                <Link to={`/review/${b.id}`}>Review</Link>
                {b.status !== 'locked' && (
                  <button
                    className="link"
                    onClick={() => lock(b.id)}
                    disabled={busy === b.id}
                  >{busy === b.id ? '…' : 'Lock'}</button>
                )}
              </td>
            </tr>
          ))}
          {batches.length === 0 && (
            <tr><td colSpan={9} className="muted">No batches yet. <Link to="/upload">Upload one</Link>.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
