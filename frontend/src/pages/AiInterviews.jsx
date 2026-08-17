import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import ManualHelp, { ManualSection } from '../components/ManualHelp'

export const statusStyles = {
  issued: 'bg-butter/80 text-amber-800',
  in_progress: 'bg-babyblue/70 text-sky-800',
  completed: 'bg-lavender/70 text-indigo-900',
  scored: 'bg-green-50 text-green-700',
  scoring_rejected: 'bg-rosy/70 text-rose-900',
}

export const statusLabel = {
  issued: 'link issued',
  in_progress: 'in progress',
  completed: 'awaiting scoring',
  scored: 'scored',
  scoring_rejected: 'scoring rejected',
}

export default function AiInterviews() {
  const [sessions, setSessions] = useState([])
  const [error, setError] = useState('')
  const [backlog, setBacklog] = useState(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  const load = async () => {
    try {
      const [s, b] = await Promise.all([api('/api/ai-interviews'), api('/api/embeddings/backlog')])
      setSessions(s)
      setBacklog(b)
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [])

  const refreshEmbeddings = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const r = await api('/api/embeddings/refresh', { method: 'POST' })
      setNotice(`Embedded ${r.profiles} profile(s) and ${r.transcripts} transcript(s) — ${r.chunks} chunks total.`)
      await load()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-extrabold text-cocoa">AI interviews</h1>
            <ManualHelp section="ai-interviews" />
          </div>
          <p className="text-sm text-cocoa/60">
            Five questions, each one written from the previous answer. Links are
            single-use and expire 72 hours after they are issued. Issue one from a
            candidate on any <Link to="/" className="underline">role page</Link>.
          </p>
        </div>
        <button onClick={refreshEmbeddings} disabled={busy}
          className="shrink-0 rounded-full border-2 border-blush bg-white text-cocoa/80 px-3 py-1.5 text-sm disabled:opacity-50">
          {busy ? 'Embedding…' : `Embed backlog${backlog?.pending ? ` (${backlog.pending})` : ''}`}
        </button>
      </div>

      {notice && <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">{notice}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="space-y-3">
        {sessions.map((s) => {
          const expired = new Date(s.expires_at) < new Date()
          const live = s.status === 'issued' || s.status === 'in_progress'
          return (
            <Link key={s.id} to={`/ai-interviews/${s.id}`}
              className="card p-5 flex items-center justify-between gap-4 hover:shadow-[0_18px_50px_-18px_rgba(92,80,73,0.35)] transition-shadow">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-cocoa">{s.candidates?.full_name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${statusStyles[s.status] || ''}`}>
                    {statusLabel[s.status] || s.status}
                  </span>
                  {expired && live && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blush/50 text-cocoa/60">expired</span>
                  )}
                  {s.roles?.title && <span className="text-sm text-cocoa/45 truncate">· {s.roles.title}</span>}
                </div>
                <p className="text-xs text-cocoa/45 mt-1">
                  Issued {new Date(s.issued_at).toLocaleString()} ·{' '}
                  {expired ? 'expired' : 'expires'} {new Date(s.expires_at).toLocaleString()}
                  {s.consumed_at && ` · started ${new Date(s.consumed_at).toLocaleString()}`}
                </p>
              </div>
              <span className="text-cocoa/30 text-lg shrink-0">→</span>
            </Link>
          )
        })}
        {sessions.length === 0 && (
          <p className="text-sm text-cocoa/45">
            No AI interviews yet — open a role, then use "AI interview" on an approved candidate.
          </p>
        )}
      </div>

      <ManualSection section="ai-interviews" />
    </div>
  )
}
