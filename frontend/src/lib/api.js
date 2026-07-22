import { supabase } from './supabase'

// In production the frontend and backend live on different domains (Vercel +
// Render), so calls must target the backend's absolute URL. In local dev
// VITE_API_URL is unset, so paths stay relative and Vite's proxy forwards
// /api to localhost:8000.
const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export function apiUrl(path) {
  return API_BASE + path
}

async function authHeaders() {
  const { data } = await supabase.auth.getSession()
  const token = data?.session?.access_token
  if (!token) throw new Error('Not signed in')
  return { Authorization: `Bearer ${token}` }
}

export async function api(path, { method = 'GET', body, formData } = {}) {
  const headers = await authHeaders()
  const opts = { method, headers }
  if (formData) {
    opts.body = formData
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  let res = await fetch(apiUrl(path), opts)
  // A stale upstream connection can 500 exactly once after idle; one retry
  // is safe for GETs only (retrying mutations could double-execute them).
  if (res.status >= 500 && method === 'GET') {
    await new Promise((r) => setTimeout(r, 600))
    res = await fetch(apiUrl(path), opts)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch { /* not json */ }
    throw new Error(detail)
  }
  return res.json()
}

export async function downloadFile(path, filename) {
  const headers = await authHeaders()
  const res = await fetch(apiUrl(path), { headers })
  if (!res.ok) throw new Error(res.statusText)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
