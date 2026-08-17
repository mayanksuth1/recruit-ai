import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import ManualHelp, { ManualSection } from '../components/ManualHelp'

const EMPTY_PROFILE = {
  company_name: '', what_we_do: '', culture_benefits: '', location: '', extra_notes: '',
}

function CompanyProfileSection() {
  const [form, setForm] = useState(EMPTY_PROFILE)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/company-profile')
      .then((p) => setForm({ ...EMPTY_PROFILE, ...p }))
      .catch((err) => setError(err.message))
      .finally(() => setLoaded(true))
  }, [])

  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); setSaved(false) }

  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { company_name, what_we_do, culture_benefits, location, extra_notes } = form
      const next = await api('/api/company-profile', {
        method: 'PUT',
        body: { company_name, what_we_do, culture_benefits, location, extra_notes },
      })
      setForm({ ...EMPTY_PROFILE, ...next })
      setSaved(true)
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const field = 'w-full rounded-2xl border border-blush px-3 py-2 text-sm'

  return (
    <form onSubmit={save} className="card p-6 space-y-3">
      <h2 className="font-medium text-cocoa/80">Company profile</h2>
      <p className="text-sm text-cocoa/60">
        Written once, then used as context whenever you generate a LinkedIn post for a
        role. The more specific this is, the less generic the posts.
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <input placeholder="Company name" value={form.company_name}
        onChange={set('company_name')} disabled={!loaded} className={field} />
      <textarea rows={3} placeholder="What does the company do?" value={form.what_we_do}
        onChange={set('what_we_do')} disabled={!loaded} className={field} />
      <textarea rows={3} placeholder="Culture and benefits" value={form.culture_benefits}
        onChange={set('culture_benefits')} disabled={!loaded} className={field} />
      <input placeholder="Location" value={form.location}
        onChange={set('location')} disabled={!loaded} className={field} />
      <textarea rows={3} placeholder="Anything else worth telling candidates"
        value={form.extra_notes} onChange={set('extra_notes')} disabled={!loaded} className={field} />

      <div className="flex items-center gap-3">
        <button disabled={busy || !loaded}
          className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-medium disabled:opacity-50">
          {busy ? 'Saving…' : 'Save company profile'}
        </button>
        {saved && <span className="text-sm text-cocoa/60">Saved.</span>}
      </div>
    </form>
  )
}

function AtsSection() {
  const [conn, setConn] = useState(null)
  const [url, setUrl] = useState('')
  const [secret, setSecret] = useState('')
  const [events, setEvents] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const c = await api('/api/ats/connection')
      setConn(c)
      setUrl(c.outbound_url || '')
      setEvents(await api('/api/ats/events'))
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api('/api/ats/connection', {
        method: 'PUT',
        body: { outbound_url: url.trim() || null, ...(secret ? { secret } : {}), active: true },
      })
      setSecret('')
      setNotice('ATS connection saved.')
      await load()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const test = async () => {
    setBusy(true)
    setError('')
    try {
      await api('/api/ats/test-outbound', { method: 'POST' })
      setNotice('Test event sent — check the event log below and your endpoint.')
      await load()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <div className="card p-6 space-y-4">
      <h2 className="font-medium text-cocoa/80">ATS sync (generic webhooks)</h2>
      <p className="text-sm text-cocoa/60">
        Works with any ATS that speaks webhooks (Greenhouse, Lever, …). Stage
        changes are pushed to your outbound URL; your ATS pushes changes back to
        the inbound URL. Workday needs its paid enterprise API tier — arranged
        separately.
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {notice && <p className="text-sm text-green-700">{notice}</p>}
      <label className="block text-xs text-cocoa/60">
        Outbound webhook URL (we POST events here)
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-ats.example.com/hooks/recruit-ai"
          className="mt-1 w-full rounded-2xl border border-blush px-3 py-2 text-sm" />
      </label>
      <label className="block text-xs text-cocoa/60">
        Shared secret (HMAC signing, both directions{conn?.has_secret ? ' — already set, enter to replace' : ''})
        <input value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={conn?.has_secret ? '••••••••' : 'optional'}
          className="mt-1 w-full rounded-2xl border border-blush px-3 py-2 text-sm" />
      </label>
      {conn && (
        <p className="text-xs text-cocoa/60">
          Inbound URL for your ATS: <code className="bg-cream/70 border border-blush/60 rounded px-1.5 py-0.5">{window.location.origin.replace(':5173', ':8000')}{conn.inbound_webhook_path}</code>
        </p>
      )}
      <div className="flex gap-2">
        <button onClick={save} disabled={busy}
          className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-medium disabled:opacity-50">Save</button>
        <button onClick={test} disabled={busy || !conn?.outbound_url}
          className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-4 py-2 text-sm disabled:opacity-50">Send test event</button>
      </div>
      {events.length > 0 && (
        <div className="border-t border-blush/40 pt-3">
          <h3 className="text-xs font-medium text-cocoa/60 mb-2">Recent sync events</h3>
          <div className="space-y-1 max-h-56 overflow-y-auto">
            {events.map((e) => (
              <div key={e.id} className="flex items-center gap-2 text-xs">
                <span className={`px-1.5 py-0.5 rounded ${e.direction === 'outbound' ? 'bg-babyblue/70 text-sky-800' : 'bg-lavender/70 text-indigo-800'}`}>{e.direction}</span>
                <span className="text-cocoa/70">{e.event_type}</span>
                <span className={e.result === 'failed' || e.result === 'rejected' ? 'text-red-600' : 'text-green-600'}>{e.result}</span>
                <span className="text-cocoa/45 truncate">{e.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Settings() {
  const [conn, setConn] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [params] = useSearchParams()
  const flash = params.get('calendar')

  const load = async () => {
    try {
      setConn(await api('/api/calendar/connection'))
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [])

  const connect = async () => {
    setBusy(true)
    setError('')
    try {
      const { url } = await api('/api/calendar/oauth/start')
      window.location.href = url
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const disconnect = async () => {
    setBusy(true)
    try {
      await api('/api/calendar/connection', { method: 'DELETE' })
      await load()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <div className="max-w-2xl mx-auto p-8 space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-extrabold text-cocoa">Settings</h1>
        <ManualHelp section="settings" />
      </div>
      {flash === 'connected' && (
        <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">
          Google Calendar connected.
        </p>
      )}
      {flash === 'error' && (
        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          Calendar connection failed ({params.get('reason')}). Try again.
        </p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card p-6 space-y-3">
        <h2 className="font-medium text-cocoa/80">Google Calendar</h2>
        <p className="text-sm text-cocoa/60">
          Connect your calendar so interview slots can be proposed from your real
          availability and events land on your calendar automatically.
        </p>
        {conn?.connected ? (
          <div className="flex items-center gap-3">
            <span className="text-sm text-green-700">
              Connected as <strong>{conn.google_email || 'your Google account'}</strong>
            </span>
            <button onClick={disconnect} disabled={busy}
              className="rounded-full border-2 border-rosy/70 bg-white text-rose-500 px-3 py-1.5 text-sm disabled:opacity-50">
              Disconnect
            </button>
          </div>
        ) : (
          <button onClick={connect} disabled={busy}
            className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-medium disabled:opacity-50">
            {busy ? 'Redirecting…' : 'Connect Google Calendar'}
          </button>
        )}
      </div>

      <CompanyProfileSection />

      <AtsSection />

      <ManualSection section="settings" />
    </div>
  )
}
