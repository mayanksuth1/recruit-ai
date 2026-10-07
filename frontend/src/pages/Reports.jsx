import { useEffect, useState } from 'react'
import { api, downloadFile } from '../lib/api'
import { DotBar, Label, PageFrame, PageHeader, fmtDate } from '../components/Page'

export default function Reports() {
  const [view, setView] = useState('recruiter')
  const [data, setData] = useState(null)
  const [reports, setReports] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async (v = view) => {
    try {
      setData(await api(v === 'recruiter' ? '/api/reports/funnel' : '/api/reports/client-summary'))
      setReports(await api('/api/reports'))
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load(view) }, [view])

  const generate = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const res = await api('/api/reports/generate', { method: 'POST' })
      setNotice(res.created ? 'Weekly summary generated.' : 'This week already has a summary — see the list below.')
      await load()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <PageFrame wide>
      <PageHeader title="Reports" section="reports"
        subtitle={view === 'recruiter'
          ? 'Pipeline health for you — full detail including upcoming interviews.'
          : 'A cleaner summary to share with clients — aggregate numbers only, no candidate details.'}
        actions={<>
          <div role="radiogroup" aria-label="Report view" className="flex gap-1 rounded-[12px] border border-line bg-surface p-1">
            {['recruiter', 'client'].map((v) => (
              <button key={v} role="radio" aria-checked={view === v} onClick={() => setView(v)}
                className={`h-[34px] rounded-lg px-3.5 text-sm ${view === v ? 'bg-line font-semibold text-ink' : 'font-medium text-ink-2'}`}>
                {v === 'recruiter' ? 'Recruiter view' : 'Client view'}
              </button>
            ))}
          </div>
          <button onClick={generate} disabled={busy} className="btn-primary">{busy ? 'Generating…' : 'Generate this week'}</button>
        </>} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      {notice && <p className="rounded-[10px] border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{notice}</p>}

      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              ['01', 'Candidates', data.totals.candidates, null],
              ['02', 'Avg score', data.totals.avg_score ?? '—', null],
              view === 'recruiter'
                ? ['03', 'Pending drafts', data.pending_drafts, data.pending_drafts ? 'Review' : null]
                : ['03', 'Roles', data.per_role?.length ?? 0, null],
            ].map(([n, label, value, tag]) => (
              <div key={n} className="card flex items-end justify-between gap-3 px-[22px] py-5">
                <div className="flex flex-col gap-3.5">
                  <div className="panel-label"><b>{n}</b>{label}</div>
                  <div className="dot-num text-[48px] text-ink">{value}</div>
                </div>
                {tag && <a href="/outbox" className="chip font-mono text-accent-soft no-underline">{tag}</a>}
              </div>
            ))}
          </div>

          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <section className="card flex flex-col gap-[18px] px-6 py-[22px]">
              <Label n={4} right="All time">Hiring funnel</Label>
              {(() => {
                const max = Math.max(...data.funnel.map((f) => f.count), 1)
                return data.funnel.map((f) => (
                  <div key={f.stage} className="grid grid-cols-[110px_minmax(0,1fr)_56px_52px] items-center gap-4">
                    <span className="text-[15px] font-medium capitalize text-ink-2">{f.stage}</span>
                    <DotBar pct={(f.count / max) * 100} height={22} />
                    <span className="dot-num text-right text-2xl text-ink">{f.count}</span>
                    <span className="text-right font-mono text-[13px] font-medium text-ink-muted">
                      {f.drop_off_pct !== null && f.drop_off_pct !== undefined ? `${Math.max(0, 100 - f.drop_off_pct)}%` : ''}
                    </span>
                  </div>
                ))
              })()}
            </section>

            <section className="card flex flex-col gap-3.5 px-6 py-[22px]">
              <Label n={5}>Weekly summaries</Label>
              <p className="m-0 text-[15px] leading-relaxed text-ink-muted">
                A written summary of the week's pipeline, stored (never auto-emailed) and ready to share as a PDF.
              </p>
              {reports.map((r) => (
                <div key={r.id} className="row-inset flex items-center justify-between gap-3 px-3.5 py-3">
                  <div className="flex flex-col gap-[3px]">
                    <span className="text-[15px] font-semibold text-ink">
                      {fmtDate(r.period_start, { year: false })} – {fmtDate(r.period_end)}
                    </span>
                    <span className="font-mono text-[13px] text-ink-muted">Generated {fmtDate(r.created_at, { year: false })}</span>
                  </div>
                  <button className="btn-ghost h-[34px]"
                    onClick={() => downloadFile(`/api/reports/${r.id}/pdf`, `weekly-summary-${r.period_start}.pdf`).catch((e) => setError(e.message))}>
                    Download PDF
                  </button>
                </div>
              ))}
              {reports.length === 0 && (
                <div className="row-inset px-3.5 py-3 text-sm text-ink-muted">No summaries yet. Use "Generate this week" above.</div>
              )}
            </section>
          </div>

          {data.per_role?.length > 0 && (
            <section className="card overflow-hidden">
              <div className="border-b border-line px-6 py-[18px]"><Label n={6}>By role</Label></div>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-[15px] text-ink-2">
                  <thead><tr>
                    {['Role', 'Sourced', 'Screened', 'Outreached', 'Interviewed', 'Offered', 'Closed'].map((h, i) => (
                      <th key={h} className={`py-3.5 text-left font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-ink-subtle ${i ? 'px-4' : 'pl-6 pr-4'}`}>{h}</th>
                    ))}
                  </tr></thead>
                  <tbody>
                    {data.per_role.map((r) => (
                      <tr key={r.role_title} className="border-t border-line">
                        <td className="py-3.5 pl-6 pr-4 font-semibold text-ink">{r.role_title}</td>
                        {['sourced', 'screened', 'outreached', 'interviewed', 'offered', 'closed'].map((c) => (
                          <td key={c} className="dot-num px-4 py-3.5 text-xl text-ink">{r[c]}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {view === 'recruiter' && data.upcoming_interviews?.length > 0 && (
            <section className="card flex flex-col gap-3 px-6 py-[22px]">
              <Label n={7}>Upcoming interviews</Label>
              {data.upcoming_interviews.map((iv, i) => (
                <div key={i} className="row-inset flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                  <span className="font-semibold text-ink">{iv.candidate}</span>
                  {iv.role && <span className="text-ink-muted">· {iv.role}</span>}
                  <span className="ml-auto font-mono text-ink-2">{fmtDate(iv.start, { year: false })} · {iv.duration_minutes} min</span>
                </div>
              ))}
            </section>
          )}
        </>
      )}

    </PageFrame>
  )
}
