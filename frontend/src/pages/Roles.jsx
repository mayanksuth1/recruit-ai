import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import ManualHelp, { ManualSection } from '../components/ManualHelp'

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

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-8">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-extrabold text-cocoa">Roles</h1>
          <ManualHelp section="roles" />
        </div>
        {org && <p className="text-sm text-cocoa/60">{org.name}</p>}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <form onSubmit={createRole} className="card p-6 space-y-3">
        <h2 className="font-medium text-cocoa/80">New role</h2>
        <input required placeholder="Role title (e.g. Senior Backend Engineer)" value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm" />
        <textarea required rows={5} placeholder="Paste the job description here — resumes are scored against it"
          value={description} onChange={(e) => setDescription(e.target.value)}
          className="w-full rounded-2xl border border-blush px-3 py-2 text-sm" />
        <button disabled={busy} className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-medium disabled:opacity-50">
          Create role
        </button>
      </form>

      <div className="space-y-2">
        {roles.map((r) => (
          <Link key={r.id} to={`/roles/${r.id}`}
            className="block card px-4 py-3 hover:border-rosy">
            <div className="flex items-center justify-between">
              <span className="font-medium text-cocoa">{r.title}</span>
              <span className="text-xs text-cocoa/45">{new Date(r.created_at).toLocaleDateString()}</span>
            </div>
          </Link>
        ))}
        {roles.length === 0 && <p className="text-sm text-cocoa/45">No roles yet.</p>}
      </div>

      <ManualSection section="roles" />
    </div>
  )
}
