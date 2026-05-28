const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

function authHeaders() {
  const t = localStorage.getItem('token')
  return t ? { Authorization: `Token ${t}` } : {}
}

async function request(path, opts = {}) {
  const headers = { ...(opts.headers || {}), ...authHeaders() }
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${BASE}${path}`, { ...opts, headers })
  const ct = res.headers.get('content-type') || ''
  const data = ct.includes('application/json') ? await res.json() : await res.text()
  if (!res.ok) {
    const err = new Error(typeof data === 'string' ? data : data.detail || 'Request failed')
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export const api = {
  base: BASE,
  login: (username, password) =>
    request('/api/auth/token/', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  health: () => request('/api/health/'),
  dashboard: () => request('/api/dashboard/'),
  facilities: () => request('/api/facilities/'),
  batches: () => request('/api/batches/'),
  batch: (id) => request(`/api/batches/${id}/`),
  lockBatch: (id) => request(`/api/batches/${id}/lock/`, { method: 'POST', body: JSON.stringify({}) }),
  batchAudit: (id) => request(`/api/batches/${id}/audit/`),
  records: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/api/records/${qs ? `?${qs}` : ''}`)
  },
  approve: (id, note = '') =>
    request(`/api/records/${id}/approve/`, { method: 'POST', body: JSON.stringify({ note }) }),
  reject: (id, note = '') =>
    request(`/api/records/${id}/reject/`, { method: 'POST', body: JSON.stringify({ note }) }),
  flag: (id, reason = 'manual_flag', note = '') =>
    request(`/api/records/${id}/flag/`, { method: 'POST', body: JSON.stringify({ reason, note }) }),
  recordAudit: (id) => request(`/api/records/${id}/audit/`),
  plantCodes: () => request('/api/plant-codes/'),
  createPlantCode: (plant_code, facility) =>
    request('/api/plant-codes/', {
      method: 'POST',
      body: JSON.stringify({ plant_code, facility }),
    }),
  deletePlantCode: (id) =>
    request(`/api/plant-codes/${id}/`, { method: 'DELETE' }),
  editRecord: (id, patch) =>
    request(`/api/records/${id}/`, { method: 'PATCH', body: JSON.stringify(patch) }),
  upload: (file, sourceType) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('source_type', sourceType)
    return request('/api/upload/', { method: 'POST', body: fd })
  },
}

export function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  window.location.href = '/login'
}
