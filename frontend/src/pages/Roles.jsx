import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { EmptyState, Label, PageFrame, PageHeader, fmtDate } from '../components/Page'

export default function Roles() {
  const [org, setOrg] = useState(null)
  const [needsOrg, setNeedsOrg] = useState(false)
  const [orgName, setOrgName] = useState('')
  const [roles, setRoles] = useState([])
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const me = await api('/api/organizations/me')
      setOrg(me)
      setNeedsOrg(false)
      setRoles(await api('/api/roles'))
    } catch (err) {
      if (String(err.message).includes('no organization')) setNeedsOrg(true)
      else setError(err.message)
    }
  }

  useEffect(() => { load() }, [])

  const createOrg = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api('/api/organizations/bootstrap', { method: 'POST', body: { organization_name: orgName } })
      await load()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const createRole = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api('/api/roles', { method: 'POST', body: { title, description } })
      setTitle(''); setDescription('')
      setRoles(await api('/api/roles'))
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  if (needsOrg) {
    return (
      <div className="max-w-md mx-auto p-8">
        <form onSubmit={createOrg} className="card p-8 space-y-4">
          <h1 className="text-lg font-semibold text-cocoa">Finish setup</h1>
          <p className="text-sm text-cocoa/60">Your account needs an organization.</p>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <input required placeholder="Organization name" value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            className="w-full rounded-2xl border border-blush px-3 py-2 text-sm" />
          <button disabled={busy} className="w-full rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform py-2 text-sm font-medium disabled:opacity-50">
            Create organization
          </button>
        </form>
      </div>
    )
  }

  const fmt = (iso) => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
  const field = 'rounded-[10px] border px-3 text-[15px] text-ink'

  return (
    <PageFrame wide>
      <PageHeader title="Roles" section="roles"
        subtitle={`Open a role from a job description. Candidates are screened against it.${org ? ` · ${org.name}` : ''}`}
        actions={<button className="btn-primary" onClick={() => document.getElementById('role-title')?.focus()}>+ New role</button>} />
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid items-start gap-4 lg:grid-cols-[460px_minmax(0,1fr)]">
        <form onSubmit={createRole} className="card flex flex-col gap-[18px] px-6 py-[22px]">
          <Label n={1}>New role</Label>
          <label className="flex flex-col gap-2 text-sm font-medium text-ink-2">
            Role title
            <input id="role-title" required placeholder="e.g. Senior Backend Engineer" value={title}
              onChange={(e) => setTitle(e.target.value)} className={`h-[42px] ${field}`} />
          </label>
          <label className="flex flex-col gap-2 text-sm font-medium text-ink-2">
            Job description
            <textarea required rows={12} placeholder="Paste the full job description, including must-have skills and location."
              value={description} onChange={(e) => setDescription(e.target.value)}
              className={`resize-y py-3 leading-relaxed ${field}`} />
          </label>
          <button disabled={busy} className="btn-primary w-full">{busy ? 'Creating…' : 'Create role'}</button>
        </form>

        <section className={`card flex flex-col gap-3.5 px-6 py-[22px] ${roles.length ? '' : 'min-h-[560px]'}`}>
          <Label n={2} right={roles.length ? 'Sorted by newest' : null}>All roles · {roles.length}</Label>
          {roles.length === 0 ? (
            <EmptyState title="No roles yet" className="flex-1">
              Fill in the form on the left to open your first role. Each role gets its own screening
              criteria and a live candidate count here.
              <div className="mt-3.5 font-mono text-[13px] font-medium text-ink-2">← Start with a title and job description</div>
            </EmptyState>
          ) : (
            <>
              <div className="hidden grid-cols-[minmax(0,1fr)_140px_110px_120px] gap-4 px-4 pb-1 font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-ink-subtle md:grid">
                <span>Role</span><span>Opened</span><span>In interview</span><span className="text-right">Candidates</span>
              </div>
              {roles.map((r) => (
                <Link key={r.id} to={`/roles/${r.id}`}
                  className="row-inset grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3.5 no-underline transition-colors hover:border-line-strong hover:bg-[#161514] md:grid-cols-[minmax(0,1fr)_140px_110px_120px]">
                  <div className="flex min-w-0 flex-col gap-[3px]">
                    <span className="text-base font-semibold text-ink">{r.title}</span>
                    <span className="text-sm text-ink-muted">{r.status === 'open' ? 'Open' : r.status || 'Open'}</span>
                  </div>
                  <span className="hidden font-mono text-sm text-ink-2 md:inline">{fmt(r.created_at)}</span>
                  <span className="hidden font-mono text-sm text-ink-2 md:inline">{r.interview_count ?? 0}</span>
                  <span className="dot-num text-right text-[28px] text-ink">{r.candidate_count ?? 0}</span>
                </Link>
              ))}
            </>
          )}
        </section>
      </div>

    </PageFrame>
  )
}
