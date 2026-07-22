import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { api, apiUrl } from '../lib/api'

export default function Signup() {
  const [orgName, setOrgName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      // Account is created server-side, already activated — no confirmation
      // email round-trip, so sign-in works immediately.
      const res = await fetch(apiUrl('/api/auth/signup'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, organization_name: orgName }),
      })
      if (!res.ok) {
        let detail = 'Sign-up failed — please try again.'
        try { detail = (await res.json()).detail || detail } catch { /* not json */ }
        if (Array.isArray(detail)) detail = 'Please enter a valid email and a password of 8+ characters.'
        throw new Error(detail)
      }
      const { error: signInErr } = await supabase.auth.signInWithPassword({ email, password })
      if (signInErr) throw signInErr
      navigate('/')
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm card p-8 space-y-4">
        <h1 className="text-xl font-extrabold text-cocoa">Create your workspace</h1>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <input
          required placeholder="Organization name" value={orgName}
          onChange={(e) => setOrgName(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm"
        />
        <input
          type="email" required placeholder="Email" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm"
        />
        <input
          type="password" required minLength={8} placeholder="Password (8+ characters)" value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm"
        />
        <button disabled={busy} className="w-full rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform py-2 text-sm font-medium disabled:opacity-50">
          {busy ? 'Creating…' : 'Sign up'}
        </button>
        <p className="text-sm text-cocoa/60">
          Have an account? <Link to="/login" className="text-cocoa underline">Sign in</Link>
        </p>
      </form>
    </div>
  )
}
