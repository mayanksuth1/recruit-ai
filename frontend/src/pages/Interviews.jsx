import { useEffect, useState } from 'react'
import { api } from '../lib/api'

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
    <div className="max-w-4xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-cocoa">Interviews</h1>
          <p className="text-sm text-cocoa/60">
            Reminders draft automatically 24h before; interviewers are nudged if
            feedback is missing 48h after. Checks also run every 15 minutes.
          </p>
        </div>
        <button onClick={runChecks} disabled={busy}
          className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-3 py-1.5 text-sm disabled:opacity-50">
          {busy ? 'Running…' : 'Run checks now'}
        </button>
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
          <p className="text-sm text-cocoa/45">
            No interviews yet — use "Schedule interview" on a candidate in a role page.
          </p>
        )}
      </div>
    </div>
  )
}
