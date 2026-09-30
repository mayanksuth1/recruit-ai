import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { EmptyState, Label, PageFrame, PageHeader } from '../components/Page'

const MON = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const hm = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`

/* The reminder chip: what the scheduler has done, or will do, for this one. */
function reminderState(iv) {
  if (iv.status === 'cancelled') return ['Cancelled', 'bg-ink-subtle']
  if (iv.status === 'proposed') return [`${(iv.proposed_slots || []).length} slots proposed`, 'bg-accent']
  if (iv.nudge_sent_at) return ['Feedback nudge sent', 'bg-accent']
  if (iv.feedback_logged_at) return ['Feedback logged', 'bg-positive']
  if (iv.reminder_drafted_at) return ['Reminder draft ready', 'bg-accent']
  if (iv.scheduled_start) {
    const at = new Date(new Date(iv.scheduled_start).getTime() - 24 * 3600 * 1000)
    return [`Drafts ${at.getDate()} ${MON[at.getMonth()][0]}${MON[at.getMonth()].slice(1).toLowerCase()}, ${hm(at)}`, 'bg-accent']
  }
  return [iv.status, 'bg-ink-subtle']
}

function InterviewCard({ iv, onChanged }) {
  const [feedback, setFeedback] = useState(iv.feedback || '')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const saveFeedback = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/api/interviews/${iv.id}/feedback`, { method: 'PATCH', body: { feedback } })
      setOpen(false)
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

  const start = iv.scheduled_start ? new Date(iv.scheduled_start) : null
  const end = iv.scheduled_end ? new Date(iv.scheduled_end) : null
  const [chip, dot] = reminderState(iv)
  const panel = [iv.interviewer_email, ...(iv.attendee_emails || [])].filter(Boolean)
  const canFeedback = iv.status === 'scheduled' || iv.status === 'completed'
  const live = iv.status !== 'cancelled' && iv.status !== 'completed'

  return (
    <div className="row-inset flex flex-col gap-3 px-4 py-3.5">
      <div className="grid grid-cols-[72px_minmax(0,1fr)] items-center gap-5 md:grid-cols-[72px_minmax(0,1.3fr)_minmax(0,1fr)_150px_220px]">
        <div className="flex flex-col items-center gap-1 border-r border-line py-2">
          <span className="dot-num text-[28px] text-ink">{start ? String(start.getDate()).padStart(2, '0') : '—'}</span>
          <span className="font-mono text-[12px] font-medium tracking-[0.08em] text-ink-muted">{start ? MON[start.getMonth()] : 'TBD'}</span>
        </div>
        <div className="flex min-w-0 flex-col gap-[3px]">
          <span className="text-base font-semibold text-ink">{iv.candidates?.full_name}</span>
          <span className="text-sm text-ink-muted">{iv.roles?.title || 'Interview'}</span>
        </div>
        <div className="hidden min-w-0 flex-col gap-[3px] md:flex">
          <span className="truncate text-sm text-ink-2" title={panel.join(', ')}>With {panel.join(', ') || 'you'}</span>
          <span className="text-sm text-ink-muted">{iv.meet_link ? 'Video · Google Meet' : `${iv.duration_minutes} min`}</span>
        </div>
        <span className="hidden font-mono text-[15px] font-medium text-ink md:inline">
          {start ? `${hm(start)}${end ? `–${hm(end)}` : ''}` : 'Awaiting pick'}
        </span>
        <span className="chip col-span-2 justify-self-start md:col-span-1 md:justify-self-end">
          <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />{chip}
        </span>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {(canFeedback || live || iv.meet_link) && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
          {iv.meet_link && <a href={iv.meet_link} target="_blank" rel="noreferrer" className="btn-ghost h-[34px] no-underline">Open Meet</a>}
          {canFeedback && (
            <button onClick={() => setOpen((o) => !o)} className="btn-ghost h-[34px]">
              {iv.feedback ? 'Edit feedback' : 'Log feedback'}
            </button>
          )}
          {live && (
            <button onClick={cancel} disabled={busy}
              className="ml-auto h-[34px] rounded-lg px-3 text-sm font-medium text-ink-2 transition-colors hover:text-accent-soft disabled:opacity-50">
              Cancel interview
            </button>
          )}
        </div>
      )}
      {open && (
        <div className="flex flex-col gap-2">
          <textarea rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Interview feedback…"
            className="resize-y rounded-[10px] border px-3 py-2.5 text-[15px] text-ink" />
          <button onClick={saveFeedback} disabled={busy || !feedback.trim()} className="btn-primary h-[38px] self-start text-sm">
            {iv.feedback ? 'Update feedback' : 'Save feedback'}
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
      {interviews.length > 0 && (
        <section className="card flex flex-col gap-3 px-6 py-[22px]">
          <div className="pb-1.5"><Label n={3} right={`${interviews.filter((i) => i.status === 'scheduled').length} scheduled`}>
            Interviews · {interviews.length}
          </Label></div>
          {interviews.map((iv) => <InterviewCard key={iv.id} iv={iv} onChanged={load} />)}
        </section>
      )}
      <div>
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
