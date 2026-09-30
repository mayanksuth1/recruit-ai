import { useState } from 'react'
import AuthLayout from '../components/AuthLayout'
import { Link } from 'react-router-dom'
import { supabase } from '../lib/supabase'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    /* redirectTo is computed from the current origin rather than hard-coded,
       for the same reason the Supabase URL is: this app is served from
       whatever hostname it happens to be behind, and a baked-in link would
       send people to the wrong host. The origin must also be listed in
       Supabase's allowed redirect URLs or the link silently will not work. */
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    /* Deliberately show the same confirmation whether or not the address is
       registered. Saying "no such account" would turn this form into a way for
       anyone to test which email addresses have accounts here. */
    if (error && !/rate|limit/i.test(error.message)) {
      setSent(true)
    } else if (error) {
      setError('Too many attempts — wait a minute and try again.')
    } else {
      setSent(true)
    }
    setBusy(false)
  }

  if (sent) {
    return (
      <AuthLayout>
        <div className="w-full max-w-sm card p-8 space-y-4">
          <h1 className="text-xl font-extrabold text-cocoa">Check your email</h1>
          <p className="text-sm text-cocoa/70">
            If an account exists for <strong>{email}</strong>, we've sent a link to
            reset your password. It expires in an hour.
          </p>
          <p className="text-sm text-cocoa/60">
            Nothing arrived? Check spam, then{' '}
            <button
              onClick={() => { setSent(false); setError('') }}
              className="text-cocoa underline"
            >
              try again
            </button>.
          </p>
          <p className="text-sm text-cocoa/60">
            <Link to="/login" className="text-cocoa underline">Back to sign in</Link>
          </p>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <form onSubmit={submit} className="w-full max-w-sm card p-8 space-y-4">
        <h1 className="text-xl font-extrabold text-cocoa">Reset your password</h1>
        <p className="text-sm text-cocoa/70">
          Enter the email you signed up with and we'll send you a reset link.
        </p>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <input
          type="email" required placeholder="Email" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm"
        />
        <button disabled={busy} className="w-full rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform py-2 text-sm font-medium disabled:opacity-50">
          {busy ? 'Sending…' : 'Send reset link'}
        </button>
        <p className="text-sm text-cocoa/60">
          Remembered it? <Link to="/login" className="text-cocoa underline">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  )
}
