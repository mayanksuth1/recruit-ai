import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { EmptyState, Label, PageFrame, PageHeader, fmtDate } from '../components/Page'

export const statusStyles = {
  issued: 'bg-butter/80 text-amber-800',
  in_progress: 'bg-babyblue/70 text-sky-800',
  completed: 'bg-lavender/70 text-indigo-900',
  scored: 'bg-green-50 text-green-700',
  scoring_rejected: 'bg-rosy/70 text-rose-900',
}

export const statusLabel = {
  issued: 'link sent',
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
  const navigate = useNavigate()

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
    <PageFrame wide>
      <PageHeader title="AI Interviews" section="ai-interviews"
        subtitle="Async first-round interviews. Answers are scored and made searchable."
        actions={<>
          {backlog?.pending > 0 && <span className="font-mono text-[13px] text-ink-muted">{backlog.pending} not embedded</span>}
          <button onClick={refreshEmbeddings} disabled={busy} className="btn-primary">{busy ? 'Embedding…' : 'Embed backlog'}</button>
        </>} />
      <div className="grid gap-4 md:grid-cols-3">
        {[['01', 'Questions', '5', 'Adaptive questions per interview. Each follows up on the previous answer.'],
          ['02', 'Links', '1\u00d7', 'Single-use links. A link stops working once the interview is submitted.'],
          ['03', 'Expiry', '72H', 'Unused links expire after 72 hours. Issue a new one from the candidate\u2019s role page.']].map(([n, l, v, d]) => (
          <div key={n} className="card flex flex-col gap-3.5 px-[22px] py-5">
            <div className="panel-label"><b>{n}</b>{l}</div>
            <div className="dot-num text-[44px] text-ink">{v}</div>
            <div className="text-sm leading-normal text-ink-muted">{d}</div>
          </div>
        ))}
      </div>

      {notice && <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">{notice}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {sessions.length > 0 && (
        <section className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-6 py-[18px]">
            <Label n={4}>Interviews · {sessions.length}</Label>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[15px] text-ink-2">
              <thead><tr>
                {['Candidate', 'Role', 'Status', 'Answered', 'Score', 'Link'].map((h, i) => (
                  <th key={h} className={`py-3.5 text-left font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-ink-subtle ${i === 0 ? 'pl-6 pr-4' : i === 5 ? 'pl-4 pr-6' : 'px-4'}`}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {sessions.map((s) => {
                  const expiresAt = new Date(s.expires_at)
                  const live = s.status === 'issued' || s.status === 'in_progress'
                  const expired = live && expiresAt < new Date()
                  const hoursLeft = Math.max(0, Math.round((expiresAt - new Date()) / 3600000))
                  const dot = expired ? 'bg-ink-subtle' : s.status === 'scored' ? 'bg-positive' : s.status === 'scoring_rejected' ? 'bg-ink-subtle' : 'bg-accent'
                  const link = expired ? `Expired ${fmtDate(s.expires_at, { year: false })}`
                    : live ? `Expires in ${hoursLeft}h`
                    : s.completed_at ? `Used ${fmtDate(s.completed_at, { year: false })}` : '—'
                  return (
                    <tr key={s.id} onClick={() => navigate(`/ai-interviews/${s.id}`)}
                      className="cursor-pointer border-t border-line transition-colors hover:bg-[#161514]">
                      <td className="py-3.5 pl-6 pr-4 font-semibold text-ink">{s.candidates?.full_name}</td>
                      <td className="px-4 py-3.5">{s.roles?.title || '—'}</td>
                      <td className="px-4 py-3.5">
                        <span className="chip text-ink"><span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
                          {expired ? 'Expired' : (statusLabel[s.status] || s.status).replace(/^./, (c) => c.toUpperCase())}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 font-mono text-sm font-medium">{s.answered ?? 0}/{s.question_target}</td>
                      <td className="dot-num px-4 py-3.5 text-[22px] text-ink">{s.overall_score ?? '—'}</td>
                      <td className="py-3.5 pl-4 pr-6 font-mono text-sm text-ink-muted">{link}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <div>
        {sessions.length === 0 && (
          <EmptyState className="bg-surface" title="No AI interviews yet"
            actions={<Link to="/" className="btn-ghost h-10 no-underline">Go to Roles</Link>}>
            Open a role, then use "AI interview" on an approved candidate. Their answers are scored here
            and become searchable once embedded.
          </EmptyState>
        )}
      </div>

      <ManualSection section="ai-interviews" />
    </PageFrame>
  )
}
