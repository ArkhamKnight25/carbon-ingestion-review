import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Upload from './pages/Upload.jsx'
import Batches from './pages/Batches.jsx'
import Review from './pages/Review.jsx'
import Settings from './pages/Settings.jsx'
import { logout } from './api.js'

function RequireAuth({ children }) {
  const t = localStorage.getItem('token')
  if (!t) return <Navigate to="/login" replace />
  return children
}

function NavBar() {
  const loc = useLocation()
  const u = localStorage.getItem('username')
  if (loc.pathname === '/login') return null
  return (
    <header className="nav">
      <div className="brand">
        <span className="brand-mark">CT</span>
        <span>CarbonTrace</span>
      </div>
      <nav>
        <Link to="/" className={loc.pathname === '/' ? 'active' : ''}>Dashboard</Link>
        <Link to="/upload" className={loc.pathname === '/upload' ? 'active' : ''}>Upload</Link>
        <Link to="/batches" className={loc.pathname.startsWith('/batches') ? 'active' : ''}>Batches</Link>
        <Link to="/review" className={loc.pathname.startsWith('/review') ? 'active' : ''}>Review</Link>
        <Link to="/settings" className={loc.pathname.startsWith('/settings') ? 'active' : ''}>Settings</Link>
      </nav>
      <div className="user">
        <span>{u || 'user'}</span>
        <button onClick={logout} className="link">Logout</button>
      </div>
    </header>
  )
}

export default function App() {
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
