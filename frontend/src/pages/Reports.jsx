import { useEffect, useState } from 'react'
import { api, downloadFile } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { EmptyState, PageFrame, PageHeader } from '../components/Page'

const barColors = ['bg-peach', 'bg-butter', 'bg-mint', 'bg-babyblue', 'bg-lavender', 'bg-rosy']

function Funnel({ funnel }) {
  const max = Math.max(...funnel.map((f) => f.count), 1)
  return (
    <div className="space-y-3">
      {funnel.map((f, i) => (
        <div key={f.stage} className="flex items-center gap-3">
          <span className="w-28 text-sm font-semibold text-cocoa/80 capitalize">{f.stage}</span>
          <div className="flex-1 h-8 bg-cream/70 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${barColors[i % barColors.length]} transition-all duration-700 flex items-center justify-end pr-3`}
              style={{ width: `${Math.max((f.count / max) * 100, f.count > 0 ? 8 : 0)}%` }}
            >
              {f.count > 0 && <span className="text-xs font-extrabold text-cocoa">{f.count}</span>}
            </div>
          </div>
          <span className="w-32 text-xs text-cocoa/45">
            {f.drop_off_pct !== null && f.drop_off_pct !== undefined ? `−${f.drop_off_pct}% drop-off` : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

function RoleTable({ rows }) {
  if (!rows?.length) return null
  const cols = ['sourced', 'screened', 'outreached', 'interviewed', 'offered', 'closed']
  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-cream/70 text-left text-cocoa/60">
          <tr>
            <th className="px-4 py-2 font-semibold">Role</th>
            {cols.map((c) => <th key={c} className="px-3 py-2 font-semibold capitalize">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.role_title} className="border-t border-blush/40">
              <td className="px-4 py-2 font-medium text-cocoa">{r.role_title}</td>
              {cols.map((c) => <td key={c} className="px-3 py-2 text-cocoa/70">{r[c]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

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
        actions={
          <div role="radiogroup" aria-label="Report view" className="flex gap-1 rounded-[12px] border border-line bg-surface p-1">
            {['recruiter', 'client'].map((v) => (
              <button key={v} role="radio" aria-checked={view === v} onClick={() => setView(v)}
                className={`h-[34px] rounded-lg px-3.5 text-sm ${view === v ? 'bg-line font-semibold text-ink' : 'font-medium text-ink-2'}`}>
                {v === 'recruiter' ? 'Recruiter view' : 'Client view'}
              </button>
            ))}
          </div>
        } />
      {error && <p className="text-sm text-red-600">{error}</p>}
      {notice && <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-2xl px-3 py-2">{notice}</p>}

      {data && (
        <>
          <div className="card p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-extrabold text-cocoa">Hiring funnel</h2>
              <div className="flex gap-4 text-sm text-cocoa/60">
                <span>Candidates: <strong className="text-cocoa">{data.totals.candidates}</strong></span>
                <span>Avg score: <strong className="text-cocoa">{data.totals.avg_score ?? '–'}</strong></span>
                {view === 'recruiter' && (
                  <span>Pending drafts: <strong className="text-cocoa">{data.pending_drafts}</strong></span>
                )}
              </div>
            </div>
            <Funnel funnel={data.funnel} />
          </div>

          <RoleTable rows={data.per_role} />

          {view === 'recruiter' && data.upcoming_interviews?.length > 0 && (
            <div className="card p-6 space-y-2">
              <h2 className="font-extrabold text-cocoa">Upcoming interviews</h2>
              {data.upcoming_interviews.map((iv, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <span className="w-2 h-2 rounded-full bg-babyblue" />
                  <span className="font-medium text-cocoa">{iv.candidate}</span>
                  {iv.role && <span className="text-cocoa/60">· {iv.role}</span>}
                  <span className="text-cocoa/45 ml-auto">{new Date(iv.start).toLocaleString()} · {iv.duration_minutes} min</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <div className="card p-6 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-extrabold text-cocoa">Weekly summaries</h2>
            <p className="text-xs text-cocoa/60">
              Generated automatically each week (stored, never auto-emailed). Download as PDF to share.
            </p>
          </div>
          <button onClick={generate} disabled={busy}
            className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-medium disabled:opacity-50">
            {busy ? 'Generating…' : 'Generate this week'}
          </button>
        </div>
        <div className="space-y-2">
          {reports.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-2xl border-2 border-blush px-4 py-2.5">
              <span className="text-sm text-cocoa/80 font-medium">
                Week of {r.period_start} → {r.period_end}
              </span>
              <button
                onClick={() => downloadFile(`/api/reports/${r.id}/pdf`, `weekly-summary-${r.period_start}.pdf`).catch((e) => setError(e.message))}
                className="rounded-full bg-lavender text-indigo-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-1.5 text-xs font-bold">
                Download PDF
              </button>
            </div>
          ))}
          {reports.length === 0 && <p className="text-sm text-cocoa/45">No summaries yet — generate one above.</p>}
        </div>
      </div>

      <ManualSection section="reports" />
    </PageFrame>
  )
}
