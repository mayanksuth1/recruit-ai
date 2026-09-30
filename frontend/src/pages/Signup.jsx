import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { api, apiUrl } from '../lib/api'
import GoogleButton, { OrDivider } from '../components/GoogleButton'

export default function Signup() {
  const [orgName, setOrgName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [checkInbox, setCheckInbox] = useState(false)
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
      // The server decides whether the account is usable immediately or has to
      // be confirmed by email first; signing in blindly would fail with a
      // confusing "Email not confirmed" in the second case.
      const { verification_required: needsVerify } = await res.json().catch(() => ({}))
      if (needsVerify) {
        setCheckInbox(true)
        setBusy(false)
        return
      }
      const { error: signInErr } = await supabase.auth.signInWithPassword({ email, password })
      if (signInErr) throw signInErr
      navigate('/')
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  if (checkInbox) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="w-full max-w-sm card p-8 space-y-4">
          <h1 className="text-xl font-extrabold text-cocoa">Confirm your email</h1>
          <p className="text-sm text-cocoa/70">
            We've sent a confirmation link to <strong>{email}</strong>. Click it and
            you'll be able to sign in.
          </p>
          <p className="text-sm text-cocoa/60">
            <Link to="/login" className="text-cocoa underline">Back to sign in</Link>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm card p-8 space-y-4">
        <h1 className="text-xl font-extrabold text-cocoa">Create your workspace</h1>
        {/* Google sign-up skips the org field here; App asks for the
            workspace name once the account exists. */}
        <GoogleButton label="Sign up with Google" />
        <OrDivider />
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
        <p className="text-xs text-cocoa/55">
          By signing up you agree to how we handle data, described in our{' '}
          <Link to="/privacy" className="underline">privacy notice</Link>.
        </p>
        <p className="text-sm text-cocoa/60">
          Have an account? <Link to="/login" className="text-cocoa underline">Sign in</Link>
        </p>
      </form>
    </div>
  )
}
