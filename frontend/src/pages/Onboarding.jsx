import { useState } from 'react'
import { api } from '../lib/api'

/* Shown when someone is signed in but belongs to no organization — in
 * practice, a first-time "Continue with Google" user. Password sign-up creates
 * the org in the same request, so those users never see this page.
 */
export default function Onboarding({ email, onDone, onSignOut }) {
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api('/api/organizations/bootstrap', {
        method: 'POST',
        body: { organization_name: orgName.trim() },
      })
      onDone()
    } catch (err) {
      // 409 means a workspace already exists (e.g. created in another tab) —
      // that is the state we wanted, so carry on.
      if (err.message.includes('already belongs')) onDone()
      else setError(err.message)
    }
    setBusy(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm card p-8 space-y-4">
        <h1 className="text-xl font-extrabold text-cocoa">Name your workspace</h1>
        <p className="text-sm text-cocoa/70">
          Signed in as <strong>{email}</strong>. One last step: what's your organization called?
        </p>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <input
          required autoFocus placeholder="Organization name" value={orgName}
          onChange={(e) => setOrgName(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm"
        />
        <button disabled={busy || !orgName.trim()} className="w-full rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform py-2 text-sm font-medium disabled:opacity-50">
          {busy ? 'Creating…' : 'Create workspace'}
        </button>
        <p className="text-sm text-cocoa/60">
          Wrong account?{' '}
          <button type="button" onClick={onSignOut} className="text-cocoa underline">Sign out</button>
        </p>
      </form>
    </div>
  )
}
