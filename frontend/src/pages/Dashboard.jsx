import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import ManualHelp, { ManualSection } from '../components/ManualHelp'

// Static class strings, not built from a variable — Tailwind only emits classes
// it can see literally in the source.
const TILES = [
  { key: 'open_roles', label: 'Open roles', tone: 'bg-mint text-teal-900', href: '/' },
  { key: 'candidates', label: 'Candidates', tone: 'bg-babyblue text-sky-900', href: '/' },
  { key: 'talent_pool', label: 'Talent pool', tone: 'bg-lavender text-indigo-900', href: '/talent-pool' },
  { key: 'draft_emails', label: 'Email drafts', tone: 'bg-butter text-amber-800', href: '/outbox' },
  { key: 'upcoming_interviews', label: 'Upcoming interviews', tone: 'bg-peach text-amber-800', href: '/interviews' },
  { key: 'embed_backlog', label: 'Not embedded', tone: 'bg-rosy text-rose-900', href: '/ai-interviews' },
]

const KIND_DOT = {
  role: 'bg-mint',
  candidate: 'bg-babyblue',
  sent: 'bg-lavender',
  draft: 'bg-butter',
  interview: 'bg-peach',
  ai_interview: 'bg-rosy',
}

const STAGE_LABEL = {
  screening: 'Screening', outreach: 'Outreach', interview: 'Interview',
  offer: 'Offer', closed: 'Closed',
}

function timeAgo(iso) {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    try { setData(await api('/api/dashboard')) }
    catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [])

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <p className="text-sm text-red-600">{error}</p>
      </div>
    )
  }
  if (!data) {
    return <div className="max-w-4xl mx-auto p-8 text-sm text-cocoa/45">Loading…</div>
  }

  const maxStage = Math.max(1, ...data.by_stage.map((s) => s.count))

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-extrabold text-cocoa">Dashboard</h1>
          <ManualHelp section="dashboard" />
        </div>
        <p className="text-sm text-cocoa/60">
          What is happening across your pipeline, and what is waiting on you.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {TILES.map((t) => (
          <Link key={t.key} to={t.href} className="card p-4 hover:border-rosy">
            <span className={`inline-flex items-center justify-center min-w-9 h-9 px-2 rounded-xl text-base font-extrabold ${t.tone}`}>
              {data.tiles[t.key]}
            </span>
            <p className="mt-2 text-xs font-bold text-cocoa/60">{t.label}</p>
          </Link>
        ))}
      </div>

      <div className="card p-5 space-y-3">
        <h2 className="font-medium text-cocoa/80">Needs you</h2>
        {data.attention.length === 0 ? (
          <p className="text-sm text-cocoa/45">
            Nothing waiting — no pending decisions, unreviewed drafts or missing feedback.
          </p>
        ) : (
          <ul className="space-y-2">
            {data.attention.map((a) => (
              <li key={a.kind}>
                <Link to={a.href}
                  className="flex items-center gap-3 rounded-2xl bg-cream/70 px-4 py-2.5 text-sm text-cocoa/75 hover:bg-cream">
                  <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-white px-1.5 text-xs font-extrabold text-cocoa">
                    {a.count}
                  </span>
                  <span className="flex-1">{a.label}</span>
                  <span className="text-xs text-cocoa/40">→</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card p-5 space-y-3">
        <h2 className="font-medium text-cocoa/80">Candidates by stage</h2>
        <div className="space-y-2">
          {data.by_stage.map((s) => (
            <div key={s.stage} className="flex items-center gap-3">
              <span className="w-20 shrink-0 text-xs font-bold text-cocoa/60">
                {STAGE_LABEL[s.stage] || s.stage}
              </span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-cream">
                <div className="h-full rounded-full bg-mint"
                  style={{ width: `${(s.count / maxStage) * 100}%` }} />
              </div>
              <span className="w-6 shrink-0 text-right text-xs font-bold text-cocoa">{s.count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-medium text-cocoa/80">Recent activity</h2>
          <button onClick={load} className="text-xs font-bold text-cocoa/50 hover:text-cocoa">
            Refresh
          </button>
        </div>
        {data.activity.length === 0 ? (
          <p className="text-sm text-cocoa/45">Nothing has happened yet.</p>
        ) : (
          <ul className="space-y-1">
            {data.activity.map((e, i) => (
              <li key={i} className="flex items-center gap-3 py-1.5 text-sm text-cocoa/70">
                <span className={`h-2 w-2 shrink-0 rounded-full ${KIND_DOT[e.kind] || 'bg-blush'}`} />
                <span className="flex-1">{e.text}</span>
                <span className="shrink-0 text-xs text-cocoa/40">{timeAgo(e.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ManualSection section="dashboard" />
    </div>
  )
}
