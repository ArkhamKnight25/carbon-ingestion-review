import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

export default function Login() {
  const nav = useNavigate()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr('')
    setLoading(true)
    try {
      const data = await api.login(username, password)
      localStorage.setItem('token', data.token)
      localStorage.setItem('username', username)
      nav('/')
    } catch (e) {
      setErr(e.message || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="brand-large">
          <span className="brand-mark">CT</span>
          <h1>CarbonTrace</h1>
        </div>
        <p className="muted">Enterprise emissions ingestion</p>

        <label>Username</label>
        <input value={username} onChange={e => setUsername(e.target.value)} autoFocus />

        <label>Password</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} />

        {err && <div className="error">{err}</div>}
        <button disabled={loading} type="submit">{loading ? 'Signing in…' : 'Sign in'}</button>

        <div className="hint">
          Demo: <code>admin</code> / <code>admin123</code> or <code>analyst</code> / <code>analyst123</code>
        </div>
      </form>
    </div>
  )
}
