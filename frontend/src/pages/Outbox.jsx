import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { EmptyState, PageFrame, PageHeader } from '../components/Page'

const kindStyles = {
  outreach: 'bg-babyblue/70 text-sky-800',
  status_update: 'bg-lavender/70 text-indigo-800',
  follow_up: 'bg-butter/80 text-amber-800',
}

function DraftCard({ msg, onChanged }) {
  const [subject, setSubject] = useState(msg.subject)
  const [body, setBody] = useState(msg.body)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dirty = subject !== msg.subject || body !== msg.body

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/api/messages/${msg.id}`, { method: 'PATCH', body: { subject, body } })
      onChanged()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const send = async () => {
    if (!window.confirm(`Send this email to ${msg.to_email}? This is the real send.`)) return
    setBusy(true)
    setError('')
    try {
      if (dirty) await api(`/api/messages/${msg.id}`, { method: 'PATCH', body: { subject, body } })
      await api(`/api/messages/${msg.id}/send`, { method: 'POST' })
      onChanged()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const discard = async () => {
    setBusy(true)
    try {
      await api(`/api/messages/${msg.id}/discard`, { method: 'POST' })
      onChanged()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          <span className={`text-xs px-2 py-0.5 rounded-full ${kindStyles[msg.kind] || ''}`}>{msg.kind.replace('_', ' ')}</span>
          <span className="font-medium text-cocoa">{msg.candidates?.full_name}</span>
          <span className="text-cocoa/45">→ {msg.to_email}</span>
          {msg.roles?.title && <span className="text-cocoa/45">· {msg.roles.title}</span>}
        </div>
        <span className="text-xs text-cocoa/45">{new Date(msg.created_at).toLocaleString()}</span>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <input value={subject} onChange={(e) => setSubject(e.target.value)}
        className="w-full rounded-2xl border border-blush px-3 py-2 text-sm font-medium" />
      <textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)}
        className="w-full rounded-2xl border border-blush px-3 py-2 text-sm" />
      <div className="flex gap-2">
        <button onClick={send} disabled={busy}
          className="rounded-full bg-mint text-teal-900 hover:scale-[1.03] active:scale-95 transition-transform px-4 py-1.5 text-sm font-medium disabled:opacity-50">
          {busy ? 'Working…' : 'Send'}
        </button>
        {dirty && (
          <button onClick={save} disabled={busy}
            className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-4 py-1.5 text-sm disabled:opacity-50">
            Save edits
          </button>
        )}
        <button onClick={discard} disabled={busy}
          className="rounded-full border-2 border-rosy/70 bg-white text-rose-500 px-4 py-1.5 text-sm disabled:opacity-50">
          Discard
        </button>
      </div>
    </div>
  )
}

function SentCard({ msg, onChanged }) {
  const [error, setError] = useState('')
  const markResponded = async () => {
    try {
      await api(`/api/messages/${msg.id}/mark-responded`, { method: 'POST' })
      onChanged()
    } catch (err) { setError(err.message) }
  }
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          <span className={`text-xs px-2 py-0.5 rounded-full ${kindStyles[msg.kind] || ''}`}>{msg.kind.replace('_', ' ')}</span>
          <span className="font-medium text-cocoa">{msg.candidates?.full_name}</span>
          <span className="text-cocoa/45">→ {msg.to_email}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-cocoa/45">
          {msg.responded_at
            ? <span className="text-green-600 font-medium">replied</span>
            : <button onClick={markResponded} className="underline hover:text-cocoa/80">mark replied</button>}
          <span>sent {new Date(msg.sent_at).toLocaleString()}</span>
        </div>
      </div>
      {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
      <p className="text-sm font-medium text-cocoa/80 mt-2">{msg.subject}</p>
      <p className="text-sm text-cocoa/60 mt-1 whitespace-pre-wrap line-clamp-3">{msg.body}</p>
    </div>
  )
}

export default function Outbox() {
  const [tab, setTab] = useState('draft')
  const [messages, setMessages] = useState([])
  const [error, setError] = useState('')
  const [fuBusy, setFuBusy] = useState(false)
  const [fuResult, setFuResult] = useState(null)
  const [fuDays, setFuDays] = useState(4)

  const load = async () => {
    try {
      setMessages(await api(`/api/messages?status=${tab}`))
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [tab])

  const generateFollowUps = async () => {
    setFuBusy(true)
    setError('')
    setFuResult(null)
    try {
      const res = await api('/api/engagement/follow-ups', { method: 'POST', body: { days: Number(fuDays) } })
      setFuResult(res.drafted)
      if (tab === 'draft') await load()
    } catch (err) { setError(err.message) }
    setFuBusy(false)
  }

  return (
    <PageFrame wide>
      <PageHeader title="Outbox" section="outbox"
        subtitle="Every email is drafted for review. Nothing sends until you approve it."
        actions={<>
          <label className="flex h-[42px] items-center gap-2.5 rounded-[10px] border border-line-strong bg-surface pl-3.5 pr-1.5 text-sm font-medium text-ink-2">
            Follow up after
            <input type="number" min={1} max={60} value={fuDays} onChange={(e) => setFuDays(e.target.value)}
              aria-label="Days before follow-up"
              className="h-[30px] w-14 rounded-lg border px-2 text-center text-[15px] font-semibold text-ink" />
            <span className="pr-2">days</span>
          </label>
          <button onClick={generateFollowUps} disabled={fuBusy} className="btn-primary">
            {fuBusy ? 'Checking…' : 'Draft follow-ups'}
          </button>
        </>} />
      {fuResult !== null && (
        <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">
          {fuResult} follow-up draft(s) created.
        </p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div role="tablist" className="flex w-fit gap-1 rounded-[12px] border border-line bg-surface p-1">
        {['draft', 'sent', 'discarded'].map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`h-9 rounded-lg px-4 text-sm ${tab === t ? 'bg-line font-semibold text-ink' : 'font-medium text-ink-2'}`}>
            {t === 'draft' ? 'Drafts' : t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        {messages.map((m) =>
          m.status === 'draft'
            ? <DraftCard key={m.id} msg={m} onChanged={load} />
            : <SentCard key={m.id} msg={m} onChanged={load} />,
        )}
        {messages.length === 0 && (
          <EmptyState className="min-h-[420px] bg-surface p-12"
            title={tab === 'draft' ? 'No drafts waiting for review' : tab === 'sent' ? 'Nothing sent yet' : 'Nothing discarded'}
            actions={tab === 'draft' && <a href="/" className="btn-primary h-10 no-underline">Go to Roles</a>}>
            {tab === 'draft'
              ? 'Outreach drafts appear here when you contact candidates from a role. Follow-ups are drafted for anyone who hasn\'t replied after the number of days you set above.'
              : 'Emails move here once they are approved or discarded.'}
          </EmptyState>
        )}
      </div>

      <ManualSection section="outbox" />
    </PageFrame>
  )
}
