import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'

/* Where the reset link lands.
 *
 * Supabase turns the emailed link into a short-lived recovery SESSION and fires
 * a PASSWORD_RECOVERY event. From that point the user is technically signed in,
 * which is why App.jsx must not bounce this route to "/" the way it does other
 * logged-in traffic — otherwise the person lands on the dashboard having never
 * been asked for a new password, and the reset silently does nothing. */
export default function ResetPassword() {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [ready, setReady] = useState(false)
  const [done, setDone] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    /* The recovery session may already exist by the time this mounts (Supabase
       processes the URL fragment on load), or arrive a moment later. Handle
       both rather than racing it. */
    supabase.auth.getSession().then(({ data }) => {
      if (data?.session) setReady(true)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY' || session) setReady(true)
    })
    return () => sub.subscription.unsubscribe()
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    if (password !== confirm) { setError('The two passwords do not match.'); return }
    if (password.length < 8) { setError('Use at least 8 characters.'); return }
    setBusy(true)
    setError('')
    const { error } = await supabase.auth.updateUser({ password })
    if (error) {
      setError(
        /expired|invalid/i.test(error.message)
          ? 'This reset link has expired. Request a new one.'
          : error.message,
      )
      setBusy(false)
      return
    }
    /* Sign out so the new password is actually used to get back in, rather than
       leaving them on a session minted by an emailed link. */
    await supabase.auth.signOut()
    setDone(true)
    setBusy(false)
    setTimeout(() => navigate('/login'), 2500)
  }

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="w-full max-w-sm card p-8 space-y-4">
          <h1 className="text-xl font-extrabold text-cocoa">Password changed</h1>
          <p className="text-sm text-cocoa/70">Taking you to sign in…</p>
          <p className="text-sm text-cocoa/60">
            <Link to="/login" className="text-cocoa underline">Go now</Link>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm card p-8 space-y-4">
        <h1 className="text-xl font-extrabold text-cocoa">Choose a new password</h1>
        {!ready && (
          <p className="text-sm text-amber-700">
            Open this page from the link in your reset email — without it there's
            nothing to reset.
          </p>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <input
          type="password" required placeholder="New password (8+ characters)"
          value={password} onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm"
        />
        <input
          type="password" required placeholder="Repeat new password"
          value={confirm} onChange={(e) => setConfirm(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm"
        />
        <button disabled={busy || !ready} className="w-full rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform py-2 text-sm font-medium disabled:opacity-50">
          {busy ? 'Saving…' : 'Set new password'}
        </button>
        <p className="text-sm text-cocoa/60">
          <Link to="/forgot-password" className="text-cocoa underline">Request a new link</Link>
        </p>
      </form>
    </div>
  )
}
