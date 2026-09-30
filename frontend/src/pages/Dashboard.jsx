import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { DotBar, EmptyState, Label, PageFrame, PageHeader, Section, fmtDate } from '../components/Page'
import { useCountUp } from '../components/fx'

// Screen 01A / 01B of the design: six stat tiles, "Needs you", and
// candidates by stage on dotted bars. Empty workspaces get the three
// get-started steps instead.

const STAGES = [
  ['screening', 'Screening'], ['outreach', 'Outreach'], ['interview', 'Interview'],
  ['offer', 'Offer'], ['closed', 'Closed'],
]

const STATS = [
  ['open_roles', 'Open roles', 'Roles currently open', 'Create a role to begin', '/'],
  ['candidates', 'Candidates', 'Across all roles', 'Added per role', '/'],
  ['talent_pool', 'Talent pool', 'Everyone you have imported', 'Import a CSV', '/talent-pool'],
  ['draft_emails', 'Email drafts', 'Awaiting your review', 'Drafts appear here', '/outbox'],
  ['upcoming_interviews', 'Upcoming interviews', 'Scheduled from here on', 'Connect your calendar', '/interviews'],
  ['embed_backlog', 'Not embedded', 'Run embed backlog', 'Nothing to embed', '/ai-interviews'],
]

const ONBOARDING = [
  ['01', 'Create a role', 'Paste a job description. Candidates are scored against it.', 'New role', '/'],
  ['02', 'Import candidates', 'Drop a CSV into the Talent Pool, or paste rows directly.', 'Open Talent Pool', '/talent-pool'],
  ['03', 'Connect Google Calendar', 'Lets us draft interview reminders and feedback nudges.', 'Open Settings', '/settings'],
]

function Stat({ n, label, value, note, empty, to }) {
  const shown = useCountUp(value)
  return (
    <Link to={to} className="card flex flex-col gap-[18px] px-5 py-[18px] no-underline">
      <div className="panel-label"><b>{n}</b>{label}</div>
      <div className={`dot-num text-[44px] ${empty ? 'text-[#5E5852]' : 'text-ink'}`}>{shown.toLocaleString()}</div>
      <div className={`text-[13px] ${empty ? 'text-ink-subtle' : 'text-ink-muted'}`}>{note}</div>
    </Link>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api('/api/dashboard').then(setData).catch((err) => setError(err.message))
  }, [])

  if (error) return <PageFrame><p className="text-sm text-red-600">{error}</p></PageFrame>
  if (!data) {
    return <PageFrame><div className="font-mono text-[13px] uppercase tracking-[0.08em] text-ink-subtle">Loading dashboard…</div></PageFrame>
  }

  const t = data.tiles
  const empty = !t.open_roles && !t.candidates && !t.talent_pool
  const byStage = Object.fromEntries(data.by_stage.map((s) => [s.stage, s.count]))
  const total = data.by_stage.reduce((a, s) => a + s.count, 0)
  const maxStage = Math.max(1, ...data.by_stage.map((s) => s.count))
  const openItems = data.attention.reduce((a, g) => a + g.count, 0)
  const laterStages = (byStage.interview || 0) + (byStage.offer || 0) + (byStage.closed || 0)

  const action = t.draft_emails
    ? <button className="btn-primary" onClick={() => navigate('/outbox')}>Review {t.draft_emails} draft{t.draft_emails === 1 ? '' : 's'}</button>
    : <button className="btn-primary" onClick={() => navigate('/')}>{t.open_roles ? '+ New role' : 'Create your first role'}</button>

  return (
    <PageFrame wide>
      <PageHeader title="Dashboard" section="dashboard" actions={action}
        subtitle="Your hiring pipeline at a glance, and the decisions waiting on you." />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {STATS.map(([key, label, note, emptyNote, to], i) => (
          <Stat key={key} n={String(i + 1).padStart(2, '0')} label={label} to={to}
            value={t[key]} empty={!t[key]} note={t[key] ? note : emptyNote} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        {empty ? (
          <Section n={7} label="Get started">
            <div className="flex flex-col gap-2.5">
              {ONBOARDING.map(([n, title, desc, cta, to]) => (
                <div key={n} className="row-inset grid grid-cols-[48px_minmax(0,1fr)_auto] items-center gap-4 px-[18px] py-4">
                  <div className="dot-num text-[28px] text-accent">{n}</div>
                  <div className="flex flex-col gap-1">
                    <div className="text-base font-semibold text-ink">{title}</div>
                    <div className="text-sm leading-normal text-ink-muted">{desc}</div>
                  </div>
                  <button className="btn-ghost" onClick={() => navigate(to)}>{cta}</button>
                </div>
              ))}
            </div>
          </Section>
        ) : (
          <section className="card flex flex-col gap-[18px] px-6 py-[22px]">
            <Label n={7} right={openItems ? (
              <span className="flex items-center gap-2 text-accent-soft"><span className="h-1.5 w-1.5 rounded-full bg-accent" />{openItems} open item{openItems === 1 ? '' : 's'}</span>
            ) : 'All clear'}>Needs you</Label>
            {data.attention.length === 0 ? (
              <div className="row-inset px-4 py-3 text-sm text-ink-muted">
                Nothing waiting — no pending decisions, unreviewed drafts or missing feedback.
              </div>
            ) : (
              data.attention.map((g) => (
                <Link key={g.kind} to={g.href}
                  className="row-inset group flex items-center justify-between gap-3 px-4 py-3.5 no-underline transition-colors hover:border-line-strong">
                  <span className="flex items-baseline gap-2.5">
                    <span className="dot-num text-2xl text-accent">{g.count}</span>
                    <span className="text-base font-semibold text-ink">{g.label}</span>
                  </span>
                  <span className="text-sm font-medium text-accent-soft transition-transform group-hover:translate-x-0.5">Open →</span>
                </Link>
              ))
            )}
            {data.activity.length > 0 && (
              <div className="mt-1 flex flex-col gap-2 border-t border-line pt-4">
                <Label>Recent activity</Label>
                {data.activity.slice(0, 6).map((e, i) => (
                  <div key={i} className="flex items-center gap-3 text-sm text-ink-2">
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-line-strong" />
                    <span className="flex-1 truncate">{e.text}</span>
                    <span className="shrink-0 font-mono text-[12px] text-ink-subtle">{fmtDate(e.at, { year: false })}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        <section className="card flex flex-col gap-[22px] px-6 py-[22px]">
          <Label n={8} right={total ? `${total} total` : null}>Candidates by stage</Label>
          {total === 0 ? (
            <EmptyState title="No candidates in the pipeline" className="flex-1 p-7"
              actions={<button className="btn-ghost bg-surface" onClick={() => navigate('/talent-pool')}>Import candidates</button>}>
              Stages fill in once a role has candidates. Import a CSV to the Talent Pool to start screening.
            </EmptyState>
          ) : (
            <>
              <div className="flex flex-col gap-[18px]">
                {STAGES.map(([key, label]) => (
                  <div key={key} className="flex flex-col gap-2">
                    <div className="flex justify-between text-sm font-medium text-ink-2">
                      <span>{label}</span><span className="dot-num text-xl text-ink">{byStage[key] || 0}</span>
                    </div>
                    <DotBar pct={((byStage[key] || 0) / maxStage) * 100} />
                  </div>
                ))}
              </div>
              <div className="mt-auto border-t border-line pt-4 text-sm leading-normal text-ink-muted">
                {laterStages} of {total} candidate{total === 1 ? '' : 's'} have reached interview or beyond.
              </div>
            </>
          )}
        </section>
      </div>
    </PageFrame>
  )
}
