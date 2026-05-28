import { useEffect, useState } from 'react'
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Upload from './pages/Upload.jsx'
import Batches from './pages/Batches.jsx'
import Review from './pages/Review.jsx'
import Settings from './pages/Settings.jsx'
import { api, logout } from './api.js'

function useKeepAlive() {
  useEffect(() => {
    const ping = () => {
      if (localStorage.getItem('token')) {
        api.health().catch(() => {})
      }
    }
    ping()
    const id = setInterval(ping, 10 * 60 * 1000)
    return () => clearInterval(id)
  }, [])
}

function RequireAuth({ children }) {
  const t = localStorage.getItem('token')
  if (!t) return <Navigate to="/login" replace />
  return children
}

function NavBar() {
  const loc = useLocation()
  const u = localStorage.getItem('username')
  const [open, setOpen] = useState(false)
  if (loc.pathname === '/login') return null
  const links = [
    ['/', 'Dashboard', loc.pathname === '/'],
    ['/upload', 'Upload', loc.pathname === '/upload'],
    ['/batches', 'Batches', loc.pathname.startsWith('/batches')],
    ['/review', 'Review', loc.pathname.startsWith('/review')],
    ['/settings', 'Settings', loc.pathname.startsWith('/settings')],
  ]
  return (
    <header className="nav">
      <div className="brand">
        <span className="brand-mark">CT</span>
        <span>CarbonTrace</span>
      </div>
      <button
        className="nav-toggle"
        aria-label="Toggle menu"
        onClick={() => setOpen(o => !o)}
      >{open ? '✕' : '☰'}</button>
      <nav className={open ? 'open' : ''}>
        {links.map(([to, label, active]) => (
          <Link key={to} to={to} className={active ? 'active' : ''} onClick={() => setOpen(false)}>{label}</Link>
        ))}
      </nav>
      <div className="user">
        <span>{u || 'user'}</span>
        <button onClick={logout} className="link">Logout</button>
      </div>
    </header>
  )
}

export default function App() {
  useKeepAlive()
  return (
    <div className="app">
      <NavBar />
      <main className="main">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/upload" element={<RequireAuth><Upload /></RequireAuth>} />
          <Route path="/batches" element={<RequireAuth><Batches /></RequireAuth>} />
          <Route path="/review" element={<RequireAuth><Review /></RequireAuth>} />
          <Route path="/review/:batchId" element={<RequireAuth><Review /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
