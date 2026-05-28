import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'

const SCOPE_LABELS = {
  1: 'Scope 1 — Direct',
  2: 'Scope 2 — Electricity',
  3: 'Scope 3 — Value chain',
}
const SCOPE_COLORS = { 1: '#ef6c4a', 2: '#f0b341', 3: '#3aa17a' }

function num(n) {
  if (n == null) return '—'
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 })
  return n.toFixed(2)
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.dashboard().then(setStats).catch(e => setErr(e.message))
  }, [])

  if (err) return <div className="error">{err}</div>
  if (!stats) return <div className="muted">Loading…</div>

  const total = stats.total_co2e_tonnes
  const totalKg = stats.total_co2e_kg
  const max = Math.max(...Object.values(stats.by_scope), 1)

  return (
    <div className="page">
      <h2>Emissions overview</h2>

      <div className="cards">
        <div className="card big">
          <div className="card-label">Total CO₂e</div>
          <div className="card-value">{num(total)} <small>tCO₂e</small></div>
          <div className="card-sub">{num(totalKg)} kg</div>
        </div>
        <div className="card">
          <div className="card-label">Pending review</div>
          <div className="card-value">{stats.pending_review}</div>
          <div className="card-sub">{stats.total_records} total records</div>
        </div>
        <div className="card">
          <div className="card-label">Batches</div>
          <div className="card-value">{stats.total_batches}</div>
          <div className="card-sub"><Link to="/batches">View all →</Link></div>
        </div>
      </div>

      <h3>By scope (kgCO₂e)</h3>
      <div className="bars">
        {[1, 2, 3].map(s => (
          <div className="bar-row" key={s}>
            <div className="bar-label">{SCOPE_LABELS[s]}</div>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{
                  width: `${(stats.by_scope[s] / max) * 100}%`,
                  background: SCOPE_COLORS[s],
                }}
              />
            </div>
            <div className="bar-val">{num(stats.by_scope[s])}</div>
          </div>
        ))}
      </div>

      <h3>By category</h3>
      <table className="table">
        <thead>
          <tr><th>Category</th><th>Records</th><th>kgCO₂e</th></tr>
        </thead>
        <tbody>
          {stats.by_category.map(c => (
            <tr key={c.category}>
              <td><code>{c.category}</code></td>
              <td>{c.n}</td>
              <td>{num(c.total)}</td>
            </tr>
          ))}
          {stats.by_category.length === 0 && (
            <tr><td colSpan={3} className="muted">No emissions yet. <Link to="/upload">Upload a file</Link>.</td></tr>
          )}
        </tbody>
      </table>

      <h3>Status</h3>
      <div className="status-pills">
        {Object.entries(stats.by_status || {}).map(([k, v]) => (
          <span key={k} className={`pill pill-${k}`}>{k}: {v}</span>
        ))}
      </div>
    </div>
  )
}
