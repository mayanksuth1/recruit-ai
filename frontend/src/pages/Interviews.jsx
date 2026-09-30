import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { EmptyState, PageFrame, PageHeader } from '../components/Page'

const statusStyles = {
  proposed: 'bg-butter/80 text-amber-800',
  scheduled: 'bg-babyblue/70 text-sky-800',
  completed: 'bg-green-50 text-green-700',
  cancelled: 'bg-blush/40 text-cocoa/60',
}

function InterviewCard({ iv, onChanged }) {
  const [feedback, setFeedback] = useState(iv.feedback || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const saveFeedback = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/api/interviews/${iv.id}/feedback`, { method: 'PATCH', body: { feedback } })
      onChanged()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const cancel = async () => {
    if (!window.confirm('Cancel this interview? The calendar event will be removed.')) return
    setBusy(true)
    try {
      await api(`/api/interviews/${iv.id}/cancel`, { method: 'POST' })
      onChanged()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium text-cocoa">{iv.candidates?.full_name}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${statusStyles[iv.status] || ''}`}>{iv.status}</span>
          {iv.roles?.title && <span className="text-sm text-cocoa/45">· {iv.roles.title}</span>}
        </div>
        {iv.status !== 'cancelled' && iv.status !== 'completed' && (
          <button onClick={cancel} disabled={busy}
            className="text-xs text-red-500 underline disabled:opacity-50">Cancel</button>
        )}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="text-sm text-cocoa/70 space-y-1">
        {iv.status === 'proposed' && (
          <p>{(iv.proposed_slots || []).length} slots proposed — waiting for the candidate to pick.</p>
        )}
        {iv.scheduled_start && (
          <p>Scheduled: {new Date(iv.scheduled_start).toLocaleString()} ({iv.duration_minutes} min)</p>
        )}
        {iv.meet_link && (
          <p>Meet: <a href={iv.meet_link} target="_blank" rel="noreferrer" className="text-blue-600 underline">{iv.meet_link}</a></p>
        )}
        {iv.reminder_drafted_at && <p className="text-xs text-cocoa/45">Reminder drafted {new Date(iv.reminder_drafted_at).toLocaleString()}</p>}
        {iv.nudge_sent_at && <p className="text-xs text-cocoa/45">Feedback nudge sent {new Date(iv.nudge_sent_at).toLocaleString()}</p>}
      </div>
      {(iv.status === 'scheduled' || iv.status === 'completed') && (
        <div className="space-y-2">
          <textarea rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)}
            placeholder="Interview feedback…"
            className="w-full rounded-2xl border border-blush px-3 py-2 text-sm" />
          <button onClick={saveFeedback} disabled={busy || !feedback.trim()}
            className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-1.5 text-sm font-medium disabled:opacity-50">
            {iv.feedback ? 'Update feedback' : 'Log feedback'}
          </button>
        </div>
      )}
    </div>
  )
}

export default function Interviews() {
  const [interviews, setInterviews] = useState([])
  const [error, setError] = useState('')
  const [checkResult, setCheckResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      setInterviews(await api('/api/interviews'))
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [])

  const runChecks = async () => {
    setBusy(true)
    setError('')
    try {
      setCheckResult(await api('/api/scheduler/run-checks', { method: 'POST' }))
      await load()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <PageFrame wide>
      <PageHeader title="Interviews" section="interviews"
        subtitle="Scheduled interviews, with reminders and feedback nudges drafted for you."
        actions={<button onClick={runChecks} disabled={busy} className="btn-primary">{busy ? 'Running…' : 'Run checks now'}</button>} />
      <div className="grid gap-4 md:grid-cols-2">
        {[['24H', 'Reminders draft 24h before', 'A reminder to the candidate is drafted a day before each interview.'],
          ['48H', 'Feedback nudges 48h after', 'If an interviewer hasn\u2019t left feedback after two days, a nudge is drafted.']].map(([h, t, d]) => (
          <div key={h} className="card grid grid-cols-[auto_minmax(0,1fr)] items-center gap-[18px] px-[22px] py-5">
            <div className="dot-num text-[40px] text-accent">{h}</div>
            <div className="flex flex-col gap-1"><div className="text-base font-semibold text-ink">{t}</div><div className="text-sm leading-normal text-ink-muted">{d}</div></div>
          </div>
        ))}
      </div>
      {checkResult && (
        <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">
          {checkResult.reminders_drafted} reminder draft(s) created, {checkResult.nudges_sent} feedback nudge(s) sent.
        </p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="space-y-4">
        {interviews.map((iv) => <InterviewCard key={iv.id} iv={iv} onChanged={load} />)}
        {interviews.length === 0 && (
          <EmptyState className="min-h-[380px] bg-surface p-12" title="No upcoming interviews"
            actions={<a href="/settings" className="btn-ghost h-10 bg-surface no-underline">Connect Google Calendar</a>}>
            Connect Google Calendar, then use "Schedule interview" on a candidate in a role. Reminder and
            feedback emails are drafted in the Outbox for you to approve.
          </EmptyState>
        )}
      </div>

      <ManualSection section="interviews" />
    </PageFrame>
  )
}
