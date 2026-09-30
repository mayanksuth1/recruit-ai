import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { Label, PageFrame, PageHeader } from '../components/Page'

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
      <Label n={3}>Company profile</Label>
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

function AiProviderSection() {
  const [state, setState] = useState(null)
  const [provider, setProvider] = useState('openai')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [qualityModel, setQualityModel] = useState('')
  const [models, setModels] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')

  const apply = (s) => {
    setState(s)
    if (s.config) {
      setProvider(s.config.provider)
      setBaseUrl(s.config.base_url || '')
      setModel(s.config.model)
      setQualityModel(s.config.quality_model || '')
    }
  }

  useEffect(() => {
    api('/api/ai-provider').then(apply).catch((err) => setError(err.message))
  }, [])

  const preset = state?.providers.find((p) => p.id === provider)
  const saved = state?.config
  // A saved key is reused only for the same endpoint; switching provider needs a new one.
  const keyRequired = !saved || saved.provider !== provider || (provider === 'custom' && saved.base_url !== baseUrl.trim())

  const run = async (label, fn) => {
    setBusy(label); setError(''); setNotice('')
    try { await fn() } catch (err) { setError(err.message) }
    setBusy('')
  }

  const loadModels = () => run('models', async () => {
    const { models } = await api('/api/ai-provider/models', {
      method: 'POST',
      body: { provider, base_url: baseUrl.trim() || null, api_key: apiKey.trim() || null },
    })
    setModels(models)
    if (!models.length) setNotice('The provider returned no models — type the model name instead.')
  })

  const save = (e) => {
    e.preventDefault()
    return run('save', async () => {
      const res = await api('/api/ai-provider', {
        method: 'PUT',
        body: {
          provider, base_url: baseUrl.trim() || null, api_key: apiKey.trim() || null,
          model: model.trim(), quality_model: qualityModel.trim() || null,
        },
      })
      apply(res)
      setApiKey('')
      setNotice(`Connected. Test call answered by ${res.test.model} in ${res.test.seconds}s — every AI feature now uses your key.`)
    })
  }

  const remove = () => run('remove', async () => {
    if (!window.confirm('Disconnect your AI provider? The workspace goes back to the limited free allowance.')) return
    apply(await api('/api/ai-provider', { method: 'DELETE' }))
    setModel(''); setQualityModel(''); setModels([]); setBaseUrl('')
    setNotice('Disconnected. The workspace is back on the free allowance.')
  })

  if (!state) {
    return <div className="card p-6 text-sm text-cocoa/60">{error || 'Loading AI provider…'}</div>
  }

  const { usage } = state
  const pct = Math.min(100, Math.round((usage.used / Math.max(usage.limit, 1)) * 100))
  const field = 'mt-1 w-full rounded-2xl border border-blush px-3 py-2 text-sm'

  return (
    <form onSubmit={save} className="card p-6 space-y-4">
      <Label n={2} right={<span className="chip"><span className={`h-1.5 w-1.5 rounded-full ${saved ? 'bg-positive' : 'bg-accent'}`} />{saved ? 'Key verified' : 'Free allowance'}</span>}>AI provider</Label>

      {usage.using_free_allowance ? (
        <div className="space-y-1.5">
          <p className="text-sm text-cocoa/70">
            You're on the free allowance: <strong>{usage.used} of {usage.limit}</strong> AI
            calls used this month. Connect your own provider for unlimited use — you pay
            your provider directly, at their prices.
          </p>
          <div className="h-2 rounded-full bg-blush/40 overflow-hidden">
            <div className={`h-full ${pct >= 100 ? 'bg-rose-500' : pct >= 80 ? 'bg-amber-400' : 'bg-cocoa/70'}`}
              style={{ width: `${pct}%` }} />
          </div>
          {pct >= 100 && (
            <p className="text-sm text-rose-600">
              The free allowance is used up. AI features stay off until you connect a key below
              or the month resets.
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-green-700">
          Using your own <strong>{saved.label}</strong> key — model <code>{saved.model}</code>
          {saved.quality_model ? <> (careful tasks: <code>{saved.quality_model}</code>)</> : null}
          {saved.key_last4 ? <>, key ending …{saved.key_last4}</> : null}.
        </p>
      )}

      {!state.can_edit ? (
        <p className="text-sm text-cocoa/60">Only the workspace owner can change the AI provider.</p>
      ) : (
        <>
          {error && <p className="text-sm text-red-600">{error}</p>}
          {notice && <p className="text-sm text-green-700">{notice}</p>}

          <label className="block text-xs text-cocoa/60">
            Provider
            <select value={provider} className={field}
              onChange={(e) => { setProvider(e.target.value); setModels([]); setModel(''); setQualityModel('') }}>
              {state.providers.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </label>

          {provider === 'custom' && (
            <label className="block text-xs text-cocoa/60">
              Base URL (OpenAI-compatible, https only)
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required
                placeholder="https://api.yourprovider.com/v1" className={field} />
            </label>
          )}

          <label className="block text-xs text-cocoa/60">
            API key {!keyRequired && '(saved — leave blank to keep it)'}
            {preset?.key_url && (
              <> · <a href={preset.key_url} target="_blank" rel="noreferrer" className="underline">get a key</a></>
            )}
            <input type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
              required={keyRequired} placeholder={keyRequired ? 'Paste your API key' : `••••${saved?.key_last4 || ''}`}
              className={field} />
          </label>

          <div className="flex items-end gap-2">
            <label className="block flex-1 text-xs text-cocoa/60">
              Model
              <input list="ai-models" value={model} onChange={(e) => setModel(e.target.value)} required
                placeholder="Load the list, or type a model name" className={field} />
            </label>
            <button type="button" onClick={loadModels} disabled={!!busy || (keyRequired && !apiKey.trim())}
              className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-3 py-2 text-sm disabled:opacity-50">
              {busy === 'models' ? 'Loading…' : 'Load models'}
            </button>
          </div>
          <label className="block text-xs text-cocoa/60">
            Stronger model for LinkedIn posts and interview scoring (optional)
            <input list="ai-models" value={qualityModel} onChange={(e) => setQualityModel(e.target.value)}
              placeholder="Same as above if left blank" className={field} />
          </label>
          <datalist id="ai-models">{models.map((m) => <option key={m} value={m} />)}</datalist>

          <p className="text-xs text-cocoa/50">
            Saving sends one tiny test request, so a wrong key or model is caught now rather
            than in the middle of your work. The key is stored encrypted and is never shown again.
          </p>

          <div className="flex gap-2">
            <button disabled={!!busy}
              className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-medium disabled:opacity-50">
              {busy === 'save' ? 'Testing…' : saved ? 'Test & update' : 'Test & connect'}
            </button>
            {saved && (
              <button type="button" onClick={remove} disabled={!!busy}
                className="rounded-full border-2 border-rosy/70 bg-white text-rose-500 px-4 py-2 text-sm disabled:opacity-50">
                Disconnect
              </button>
            )}
          </div>
        </>
      )}
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
      <Label n={4}>ATS sync (generic webhooks)</Label>
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
    <PageFrame wide>
      <PageHeader title="Settings" section="settings"
        subtitle="Connect your calendar and choose the AI model that drafts and scores." />
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

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <div className="card flex flex-col gap-[18px] p-6">
        <Label n={1} right={
          <span className="chip"><span className={`h-1.5 w-1.5 rounded-full ${conn?.connected ? 'bg-positive' : 'bg-ink-subtle'}`} />{conn?.connected ? 'Connected' : 'Not connected'}</span>
        }>Google Calendar</Label>
        <div className="text-xl font-semibold text-ink">Sync interviews with your calendar</div>
        <p className="m-0 text-[15px] leading-relaxed text-ink-muted">
          Interview slots are proposed from your real availability, and booked
          interviews land on your calendar with a Meet link.
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
            className="h-[42px] self-start rounded-[10px] border border-line-strong bg-ink px-4 text-[15px] font-semibold text-[#141312] transition-opacity hover:opacity-90 disabled:opacity-50">
            {busy ? 'Redirecting…' : 'Connect Google Calendar'}
          </button>
        )}
      </div>

      <AiProviderSection />
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <CompanyProfileSection />
        <AtsSection />
      </div>

      <ManualSection section="settings" />
    </PageFrame>
  )
}
