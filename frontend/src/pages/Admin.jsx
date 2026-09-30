import { useEffect, useState } from 'react'
import { api } from '../lib/api'

// Plain-English names for logged actions. Anything unlisted shows its route.
const ACTION_LABEL = {
  'POST /api/auth/signup': 'Signed up',
  'POST /api/organizations/bootstrap': 'Created workspace',
  'PUT /api/company-profile': 'Updated company profile',
  'POST /api/roles': 'Created a role',
  'PATCH /api/roles/{role_id}': 'Edited a role',
  'POST /api/roles/{role_id}/boolean-search': 'Generated Boolean search',
  'POST /api/roles/{role_id}/linkedin-post': 'Generated LinkedIn post',
  'PUT /api/roles/{role_id}/linkedin-post': 'Edited LinkedIn post',
  'POST /api/roles/{role_id}/candidates/upload': 'Uploaded & scored a resume',
  'POST /api/roles/{role_id}/match-pool': 'Matched talent pool to a role',
  'PATCH /api/candidates/bulk-shortlist': 'Bulk-shortlisted candidates',
  'PATCH /api/candidates/{candidate_id}/shortlist': 'Shortlisted a candidate',
  'POST /api/talent-pool/import': 'Imported candidates (CSV)',
  'POST /api/candidates/{candidate_id}/draft-outreach': 'Drafted outreach email',
  'POST /api/candidates/{candidate_id}/approve-offer': 'Approved an offer',
  'POST /api/candidates/{candidate_id}/revoke-offer-approval': 'Revoked offer approval',
  'PATCH /api/candidates/{candidate_id}/stage': 'Moved a candidate stage',
  'POST /api/engagement/follow-ups': 'Generated follow-ups',
  'PATCH /api/messages/{message_id}': 'Edited an email draft',
  'POST /api/messages/{message_id}/send': 'Sent an email',
  'POST /api/messages/{message_id}/discard': 'Discarded an email draft',
  'POST /api/messages/{message_id}/mark-responded': 'Marked a reply',
  'DELETE /api/calendar/connection': 'Disconnected Google Calendar',
  'POST /api/candidates/{candidate_id}/interviews/propose': 'Proposed interview times',
  'PATCH /api/interviews/{interview_id}/feedback': 'Logged interview feedback',
  'POST /api/interviews/{interview_id}/cancel': 'Cancelled an interview',
  'POST /api/scheduler/run-checks': 'Ran reminder checks',
  'POST /api/public/schedule/{token}': 'Candidate booked an interview',
  'POST /api/public/ai-interview/{token}': 'Candidate answered AI interview',
  'POST /api/candidates/{candidate_id}/ai-interview': 'Issued an AI interview',
  'POST /api/ai-interviews/{session_id}/score': 'Scored an AI interview',
  'POST /api/search/semantic': 'Ran semantic search',
  'POST /api/embeddings/refresh': 'Refreshed search index',
  'POST /api/ai-provider/models': 'Listed AI models',
  'PUT /api/ai-provider': 'Connected own AI provider',
  'POST /api/ai-provider/test': 'Tested AI provider',
  'DELETE /api/ai-provider': 'Disconnected AI provider',
  'PUT /api/ats/connection': 'Configured ATS sync',
  'POST /api/ats/test-outbound': 'Sent ATS test event',
  'POST /api/webhooks/ats/{inbound_token}': 'ATS pushed an update',
  'POST /api/reports/generate': 'Generated weekly report',
  'auth.failed_login': 'Failed sign-in',
  'security.rate_limited': 'Rate limit hit',
  'admin.viewed_workspace': 'Admin opened workspace',
}

const label = (a) => ACTION_LABEL[a] || a
const fmt = (iso) => (iso ? new Date(iso).toLocaleString() : '—')
const day = (iso) => (iso ? new Date(iso).toLocaleDateString() : '—')

const TABS = ['Overview', 'Workspaces', 'Activity', 'Users', 'Sign-ins', 'Alerts']

function Tile({ title, value, hint }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-cocoa/60">{title}</div>
      <div className="text-2xl font-extrabold text-cocoa">{value}</div>
      {hint && <div className="text-xs text-cocoa/50">{hint}</div>}
    </div>
  )
}

function Overview() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/admin/overview').then(setD).catch((e) => setErr(e.message)) }, [])
  if (err) return <p className="text-sm text-red-600">{err}</p>
  if (!d) return <p className="text-sm text-cocoa/60">Loading…</p>
  const max = Math.max(1, ...d.series.map((s) => s.actions))
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Tile title="Users" value={d.users} hint={`${d.signups_7d} new this week`} />
        <Tile title="Workspaces" value={d.workspaces} hint={`${d.active_workspaces_7d} active this week`} />
        <Tile title="Actions today" value={d.actions_today} />
        <Tile title="Own-key workspaces" value={d.own_key_workspaces} />
        <Tile title="Free AI calls this month" value={d.ai_calls_this_month} hint={`limit ${d.free_limit} per workspace`} />
        <Tile title="Candidates (all workspaces)" value={d.candidates_total} />
        <Tile title="Resumes scored" value={d.resumes_scored_total} />
        <Tile title="Emails sent" value={d.emails_sent_total} />
      </div>
      <div className="card p-4">
        <div className="text-sm font-medium text-cocoa/80 mb-3">Last 30 days — actions (bars) and signups (numbers)</div>
        <div className="flex items-end gap-1 h-40">
          {d.series.map((s) => (
            <div key={s.day} className="flex-1 flex flex-col items-center justify-end h-full"
              title={`${s.day}: ${s.actions} actions, ${s.signups} signups`}>
              {s.signups > 0 && <span className="text-[10px] text-emerald-700 font-semibold">+{s.signups}</span>}
              <div className="w-full rounded-t bg-cocoa/70" style={{ height: `${(s.actions / max) * 100}%`, minHeight: s.actions ? 2 : 0 }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Workspaces({ open }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/admin/workspaces').then(setRows).catch((e) => setErr(e.message)) }, [])
  if (err) return <p className="text-sm text-red-600">{err}</p>
  if (!rows) return <p className="text-sm text-cocoa/60">Loading…</p>
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-cocoa/60">
          <tr>{['Workspace', 'Owner', 'Signed up', 'Last active', 'Team', 'Roles', 'Candidates', 'Scored', 'Emails sent', 'AI calls (mo)', 'AI'].map((h) =>
            <th key={h} className="px-3 py-2 whitespace-nowrap">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((w) => (
            <tr key={w.organization_id} onClick={() => open(w.organization_id)}
              className="border-t border-blush/40 hover:bg-blush/20 cursor-pointer">
              <td className="px-3 py-2 font-medium text-cocoa">{w.name}</td>
              <td className="px-3 py-2">{w.owner_email || '—'}</td>
              <td className="px-3 py-2 whitespace-nowrap">{day(w.created_at)}</td>
              <td className="px-3 py-2 whitespace-nowrap">{fmt(w.last_active)}</td>
              <td className="px-3 py-2">{w.members}</td>
              <td className="px-3 py-2">{w.roles_open}/{w.roles_total}</td>
              <td className="px-3 py-2">{w.candidates}</td>
              <td className="px-3 py-2">{w.resumes_scored}</td>
              <td className="px-3 py-2">{w.messages_sent}</td>
              <td className="px-3 py-2">{w.ai_calls_this_month}</td>
              <td className="px-3 py-2 whitespace-nowrap">{w.own_ai_provider ? `own: ${w.own_ai_provider}` : 'free'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Feed({ rows }) {
  if (!rows.length) return <p className="text-sm text-cocoa/60 p-4">No activity yet.</p>
  return (
    <div className="divide-y divide-blush/40">
      {rows.map((r) => (
        <div key={r.id} className="px-4 py-2 text-sm flex flex-wrap gap-x-3">
          <span className="text-cocoa/50 whitespace-nowrap">{fmt(r.at)}</span>
          <span className="font-medium text-cocoa">{r.workspace || '—'}</span>
          <span className="text-cocoa/70">{r.user || (r.action.startsWith('POST /api/public') ? 'candidate' : '')}</span>
          <span className="text-cocoa">{label(r.action)}</span>
          {r.meta?.email && <span className="text-cocoa/50">({r.meta.email})</span>}
          {r.meta?.bucket && <span className="text-cocoa/50">({r.meta.bucket})</span>}
        </div>
      ))}
    </div>
  )
}

function WorkspaceDetail({ id, back }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api(`/api/admin/workspaces/${id}`).then(setD).catch((e) => setErr(e.message)) }, [id])
  if (err) return <p className="text-sm text-red-600">{err}</p>
  if (!d) return <p className="text-sm text-cocoa/60">Loading…</p>
  const w = d.workspace
  return (
    <div className="space-y-4">
      <button onClick={back} className="text-sm text-cocoa underline">← All workspaces</button>
      <h2 className="text-xl font-extrabold text-cocoa">{w.name}</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Tile title="Roles (open / total)" value={`${w.roles_open} / ${w.roles_total}`} />
        <Tile title="Candidates" value={w.candidates} hint={`talent pool ${w.pool_size}`} />
        <Tile title="Resumes scored" value={w.resumes_scored} hint={w.avg_score != null ? `avg score ${w.avg_score}` : null} />
        <Tile title="Emails" value={`${w.messages_sent} sent`} hint={`${w.messages_drafted} drafts · ${w.messages_replied} replies`} />
        <Tile title="Interviews" value={`${w.interviews_scheduled} scheduled`} hint={`${w.interviews_completed} with feedback`} />
        <Tile title="AI interviews" value={`${w.ai_interviews_done} / ${w.ai_interviews_issued}`} hint="completed / issued" />
        <Tile title="AI" value={w.own_ai_provider ? `Own: ${w.own_ai_provider}` : 'Free allowance'}
          hint={w.own_ai_provider ? w.own_ai_model : `${w.ai_calls_this_month} calls this month`} />
        <Tile title="Integrations" value={[w.calendar_connected && 'Calendar', w.ats_configured && 'ATS'].filter(Boolean).join(' + ') || 'None'} />
      </div>
      <div className="card p-4 text-sm">
        <div className="font-medium text-cocoa/80 mb-2">Candidates by stage</div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(w.candidates_by_stage || {}).map(([s, n]) => (
            <span key={s} className="px-2 py-1 rounded-full bg-blush/40">{s}: {n}</span>
          ))}
          {!Object.keys(w.candidates_by_stage || {}).length && <span className="text-cocoa/50">No candidates yet.</span>}
        </div>
      </div>
      <div className="card overflow-x-auto">
        <div className="px-4 pt-3 text-sm font-medium text-cocoa/80">Team</div>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-cocoa/60"><tr>
            {['Email', 'Role', 'Joined', 'Last sign-in', 'Sign-in method'].map((h) => <th key={h} className="px-4 py-2">{h}</th>)}
          </tr></thead>
          <tbody>{d.members.map((m) => (
            <tr key={m.email} className="border-t border-blush/40">
              <td className="px-4 py-2">{m.email}</td><td className="px-4 py-2">{m.role}</td>
              <td className="px-4 py-2">{day(m.joined)}</td><td className="px-4 py-2">{fmt(m.last_sign_in_at)}</td>
              <td className="px-4 py-2">{m.providers.join(', ')}</td>
            </tr>))}</tbody>
        </table>
      </div>
      <div className="card">
        <div className="px-4 pt-3 text-sm font-medium text-cocoa/80">Recent activity</div>
        <Feed rows={d.activity} />
      </div>
      <p className="text-xs text-cocoa/50">
        Counts and actions only. Candidate details, resumes, emails and transcripts belong to
        this workspace and are not shown here. Opening this page was recorded in the activity log.
      </p>
    </div>
  )
}

function Activity() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/admin/activity?limit=500').then(setRows).catch((e) => setErr(e.message)) }, [])
  if (err) return <p className="text-sm text-red-600">{err}</p>
  if (!rows) return <p className="text-sm text-cocoa/60">Loading…</p>
  return <div className="card"><Feed rows={rows} /></div>
}

function Users() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/admin/users').then(setRows).catch((e) => setErr(e.message)) }, [])
  if (err) return <p className="text-sm text-red-600">{err}</p>
  if (!rows) return <p className="text-sm text-cocoa/60">Loading…</p>
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-cocoa/60"><tr>
          {['Email', 'Workspace', 'Role', 'Signed up', 'Last sign-in', 'Method'].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}
        </tr></thead>
        <tbody>{rows.map((u) => (
          <tr key={u.id} className="border-t border-blush/40">
            <td className="px-3 py-2">{u.email}</td><td className="px-3 py-2">{u.workspace || '— (no workspace yet)'}</td>
            <td className="px-3 py-2">{u.role || '—'}</td><td className="px-3 py-2">{day(u.created_at)}</td>
            <td className="px-3 py-2">{fmt(u.last_sign_in_at)}</td><td className="px-3 py-2">{u.providers.join(', ')}</td>
          </tr>))}</tbody>
      </table>
    </div>
  )
}

function Signins() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/admin/signins?limit=300').then(setRows).catch((e) => setErr(e.message)) }, [])
  if (err) return <p className="text-sm text-red-600">{err}</p>
  if (!rows) return <p className="text-sm text-cocoa/60">Loading…</p>
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-cocoa/60"><tr>
          {['When', 'Event', 'Account', 'IP address'].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}
        </tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i} className="border-t border-blush/40">
            <td className="px-3 py-2 whitespace-nowrap">{fmt(r.created_at)}</td><td className="px-3 py-2">{r.action}</td>
            <td className="px-3 py-2">{r.email || '—'}</td><td className="px-3 py-2">{r.ip_address || '—'}</td>
          </tr>))}</tbody>
      </table>
      <p className="text-xs text-cocoa/50 px-3 py-2">Kept for security: spotting attacks on accounts.</p>
    </div>
  )
}

function Alerts({ open }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/admin/alerts').then(setD).catch((e) => setErr(e.message)) }, [])
  if (err) return <p className="text-sm text-red-600">{err}</p>
  if (!d) return <p className="text-sm text-cocoa/60">Loading…</p>
  const Section = ({ title, hint, items, render }) => (
    <div className="card p-4 space-y-2">
      <div className="text-sm font-medium text-cocoa/80">{title} <span className="text-cocoa/50">({items.length})</span></div>
      <div className="text-xs text-cocoa/50">{hint}</div>
      {items.length ? items.map(render) : <div className="text-sm text-cocoa/50">None.</div>}
    </div>
  )
  const wsRow = (w) => (
    <div key={w.workspace_id} className="text-sm cursor-pointer hover:underline" onClick={() => open(w.workspace_id)}>
      <strong>{w.workspace}</strong> · {w.owner_email} {w.ai_calls_this_month != null && `· ${w.ai_calls_this_month} calls`}
      {w.signed_up && ` · signed up ${day(w.signed_up)}`}
    </div>
  )
  return (
    <div className="grid md:grid-cols-2 gap-3">
      <Section title="Hit the free AI limit" hint="Most likely to value the product — good people to talk to." items={d.hit_free_limit} render={wsRow} />
      <Section title="Near the free limit (80%+)" hint="About to run out this month." items={d.near_free_limit} render={wsRow} />
      <Section title="Signed up, never started" hint="No roles or candidates after 2 days — worth a friendly nudge." items={d.dormant_signups} render={wsRow} />
      <Section title="Repeated failed sign-ins (24h)" hint="3+ wrong passwords for one address: forgotten password, or someone guessing."
        items={d.failed_logins_24h} render={(f) => <div key={f.email} className="text-sm">{f.email} · {f.attempts} attempts</div>} />
      <Section title="Rate limits hit (24h)" hint="Which protections triggered. Spikes can mean abuse."
        items={d.rate_limited_24h} render={(r) => <div key={r.bucket} className="text-sm">{r.bucket} · {r.times}×</div>} />
    </div>
  )
}

export default function Admin() {
  const [tab, setTab] = useState('Overview')
  const [workspace, setWorkspace] = useState(null)
  const open = (id) => { setWorkspace(id); setTab('Workspaces') }

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold text-cocoa">Admin</h1>
        <p className="text-sm text-cocoa/60">Platform activity and usage. Counts and actions only — never candidate data.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button key={t} onClick={() => { setTab(t); setWorkspace(null) }}
            className={`px-3 py-1.5 rounded-full text-sm font-semibold ${tab === t ? 'bg-cocoa text-cream' : 'text-cocoa/70 hover:bg-blush/50'}`}>
            {t}
          </button>
        ))}
      </div>
      {tab === 'Overview' && <Overview />}
      {tab === 'Workspaces' && (workspace ? <WorkspaceDetail id={workspace} back={() => setWorkspace(null)} /> : <Workspaces open={open} />)}
      {tab === 'Activity' && <Activity />}
      {tab === 'Users' && <Users />}
      {tab === 'Sign-ins' && <Signins />}
      {tab === 'Alerts' && <Alerts open={open} />}
    </div>
  )
}
