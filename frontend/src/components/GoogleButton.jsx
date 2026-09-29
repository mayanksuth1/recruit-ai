import { useState } from 'react'
import { supabase } from '../lib/supabase'

/* "Continue with Google" for both sign-in and sign-up — with OAuth they are
 * the same action. Supabase creates the account on first use; App then sees a
 * session with no organization and asks for a workspace name.
 *
 * redirectTo is the page's own origin rather than a baked-in URL so the same
 * bundle works on localhost and behind a tunnel. The origin must be in
 * additional_redirect_urls (supabase/config.toml) or Supabase silently falls
 * back to site_url.
 */
export default function GoogleButton({ label = 'Continue with Google' }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const go = async () => {
    setBusy(true)
    setError('')
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    })
    // On success the browser is already navigating to Google, so only the
    // failure path needs to reset state.
    if (error) {
      setError(
        error.message.includes('provider is not enabled')
          ? 'Google sign-in is not set up on this server yet.'
          : error.message,
      )
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button" onClick={go} disabled={busy}
        className="w-full flex items-center justify-center gap-2 rounded-full border border-blush bg-white text-cocoa shadow-sm hover:scale-[1.03] active:scale-95 transition-transform py-2 text-sm font-semibold disabled:opacity-50"
      >
        <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
          <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
          <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
          <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
          <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
        </svg>
        {busy ? 'Redirecting to Google…' : label}
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}

export function OrDivider() {
  return (
    <div className="flex items-center gap-3 text-xs text-cocoa/50">
      <span className="h-px flex-1 bg-blush" />
      or
      <span className="h-px flex-1 bg-blush" />
    </div>
  )
}
