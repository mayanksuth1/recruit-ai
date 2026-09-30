import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { EmptyState, PageFrame, PageHeader, fmtDate } from '../components/Page'

const KIND_LABEL = {
  outreach: 'Outreach',
  status_update: 'Status update',
  follow_up: 'Follow-up',
  scheduling_link: 'Scheduling',
  reminder: 'Reminder',
  feedback_nudge: 'Feedback nudge',
}

const hhmm = (iso) => {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function CardHead({ msg, when }) {
  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <span className="rounded-md border border-line-strong px-[9px] py-1 font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-accent-soft">
          {KIND_LABEL[msg.kind] || msg.kind.replace('_', ' ')}
        </span>
        <span className="font-mono text-[13px] text-ink-muted">{when}</span>
      </div>
      <div className="text-sm text-ink-muted">
        To <span className="font-medium text-ink">{msg.candidates?.full_name || msg.to_email}</span>
        {msg.roles?.title && <> · {msg.roles.title}</>}
        <span className="ml-1 font-mono text-[12px] text-ink-subtle">({msg.to_email})</span>
      </div>
    </>
  )
}

function DraftCard({ msg, onChanged }) {
  const [subject, setSubject] = useState(msg.subject)
  const [body, setBody] = useState(msg.body)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dirty = subject !== msg.subject || body !== msg.body

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/api/messages/${msg.id}`, { method: 'PATCH', body: { subject, body } })
      setEditing(false)
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
    <article className="card flex flex-col gap-3.5 px-[22px] py-5">
      <CardHead msg={msg} when={`Drafted ${hhmm(msg.created_at)}`} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      {editing ? (
        <>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject"
            className="h-[42px] rounded-[10px] border px-3 text-[15px] font-semibold text-ink" />
          <textarea rows={9} value={body} onChange={(e) => setBody(e.target.value)} aria-label="Body"
            className="resize-y rounded-[10px] border px-4 py-3.5 text-[15px] leading-relaxed text-ink-2" />
        </>
      ) : (
        <>
          <div className="text-[17px] font-semibold leading-snug text-ink">{subject}</div>
          <p className="row-inset m-0 whitespace-pre-line px-4 py-3.5 text-[15px] leading-relaxed text-ink-2">{body}</p>
        </>
      )}
      <div className="flex gap-2">
        <button onClick={send} disabled={busy} className="btn-primary h-[38px] px-4 text-sm">
          {busy ? 'Working…' : 'Approve & send'}
        </button>
        {editing
          ? <button onClick={save} disabled={busy || !dirty} className="btn-ghost disabled:opacity-50">Save edits</button>
          : <button onClick={() => setEditing(true)} disabled={busy} className="btn-ghost">Edit</button>}
        <button onClick={discard} disabled={busy}
          className="ml-auto h-[38px] rounded-[10px] bg-transparent px-3.5 text-sm font-medium text-ink-2 transition-colors hover:text-accent-soft disabled:opacity-50">
          Discard
        </button>
      </div>
    </article>
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
  const sent = msg.status === 'sent'
  return (
    <article className="card flex flex-col gap-3.5 px-[22px] py-5">
      <CardHead msg={msg} when={sent ? `Sent ${fmtDate(msg.sent_at, { year: false })} ${hhmm(msg.sent_at)}` : 'Discarded'} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="text-[17px] font-semibold leading-snug text-ink">{msg.subject}</div>
      <p className="row-inset m-0 line-clamp-4 whitespace-pre-line px-4 py-3.5 text-[15px] leading-relaxed text-ink-2">{msg.body}</p>
      {sent && (
        <div className="flex items-center gap-2">
          {msg.responded_at
            ? <span className="chip"><span className="h-1.5 w-1.5 rounded-full bg-positive" />Replied</span>
            : <button onClick={markResponded} className="btn-ghost">Mark replied</button>}
        </div>
      )}
    </article>
  )
}

export default function Outbox() {
  const [tab, setTab] = useState('draft')
  const [messages, setMessages] = useState([])
  const [error, setError] = useState('')
  const [fuBusy, setFuBusy] = useState(false)
  const [fuResult, setFuResult] = useState(null)
  const [fuDays, setFuDays] = useState(4)
  const [counts, setCounts] = useState({})

  const load = async () => {
    try {
      const [draft, sent, discarded] = await Promise.all(
        ['draft', 'sent', 'discarded'].map((st) => api(`/api/messages?status=${st}`)),
      )
      const all = { draft, sent, discarded }
      setCounts({ draft: draft.length, sent: sent.length, discarded: discarded.length })
      // Drafts oldest first: the one waiting longest is reviewed first.
      setMessages(tab === 'draft' ? [...all.draft].reverse() : all[tab])
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
            {t === 'draft' ? 'Drafts' : t[0].toUpperCase() + t.slice(1)}{' '}
            <span className={`font-mono ${t === 'draft' && counts.draft ? 'text-accent-soft' : 'text-ink-muted'}`}>{counts[t] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className={messages.length ? 'grid gap-4 lg:grid-cols-2' : ''}>
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
