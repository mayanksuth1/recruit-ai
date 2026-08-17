import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import ManualHelp, { ManualSection } from '../components/ManualHelp'

const KINDS = [
  { key: 'profile', label: 'Profiles' },
  { key: 'transcript', label: 'Interview answers' },
]

export default function Search() {
  const [query, setQuery] = useState('')
  const [kinds, setKinds] = useState(['profile', 'transcript'])
  const [results, setResults] = useState(null)
  const [backlog, setBacklog] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/api/embeddings/backlog').then(setBacklog).catch(() => {})
  }, [])

  const run = async (e) => {
    e?.preventDefault()
    if (query.trim().length < 2) return
    setBusy(true)
    setError('')
    try {
      setResults(await api('/api/search/semantic', { method: 'POST', body: { query, kinds, limit: 25 } }))
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const toggleKind = (k) => {
    setKinds((cur) => (cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]))
  }

  return (
    <div className="max-w-3xl mx-auto p-8 space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-extrabold text-cocoa">Semantic search</h1>
          <ManualHelp section="search" />
        </div>
        <p className="text-sm text-cocoa/60">
          Searches meaning, not keywords — describe the person you want in your own
          words. Covers talent-pool profiles and what candidates actually said in
          their AI interviews.
        </p>
      </div>

      {backlog?.pending > 0 && (
        <p className="text-sm text-amber-900 bg-butter/50 border border-butter rounded-md px-3 py-2">
          {backlog.pending} item(s) have changed since they were last embedded and will not
          match until you run <Link to="/ai-interviews" className="underline">Embed backlog</Link>.
        </p>
      )}

      <form onSubmit={run} className="card p-5 space-y-3">
        <textarea
          rows={2}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) run(e) }}
          placeholder="e.g. shipped an idempotency layer that survived duplicate webhooks"
          className="w-full rounded-2xl border border-blush px-4 py-3 text-sm focus:outline-none focus:border-rosy"
        />
        <div className="flex items-center justify-between gap-3">
          <div className="flex gap-2">
            {KINDS.map((k) => (
              <button key={k.key} type="button" onClick={() => toggleKind(k.key)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium border-2 transition-colors ${
                  kinds.includes(k.key)
                    ? 'bg-lavender border-lavender text-indigo-900'
                    : 'bg-white border-blush text-cocoa/50'
                }`}>
                {k.label}
              </button>
            ))}
          </div>
          <button type="submit" disabled={busy || query.trim().length < 2 || kinds.length === 0}
            className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-5 py-2 text-sm font-semibold disabled:opacity-40 disabled:hover:scale-100">
            {busy ? 'Searching…' : 'Search'}
          </button>
        </div>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {results && (
        <div className="space-y-3">
          <p className="text-xs text-cocoa/45">
            {results.length} result{results.length === 1 ? '' : 's'}, most similar first.
          </p>
          {results.map((r) => (
            <div key={r.embedding_id} className="card p-5 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-medium text-cocoa truncate">{r.candidate_name || 'Unnamed'}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${
                    r.source_kind === 'transcript' ? 'bg-lavender/60 text-indigo-900' : 'bg-mint/60 text-teal-900'
                  }`}>
                    {r.source_kind === 'transcript' ? `interview answer ${r.chunk_ordinal + 1}` : 'profile'}
                  </span>
                </div>
                <span className="text-xs text-cocoa/45 shrink-0" title={`cosine distance ${r.distance.toFixed(4)}`}>
                  {(r.similarity * 100).toFixed(1)}% match
                </span>
              </div>
              {/* The matched chunk itself, not a summary of it — the recruiter
                  should see the text the ranking was actually computed from. */}
              <p className="text-sm text-cocoa/70 whitespace-pre-wrap line-clamp-6">{r.snippet}</p>
              {r.session_id && (
                <Link to={`/ai-interviews/${r.session_id}`} className="text-xs text-cocoa/50 underline">
                  Open the full interview →
                </Link>
              )}
            </div>
          ))}
          {results.length === 0 && (
            <p className="text-sm text-cocoa/45">
              Nothing matched. If you have just added candidates, run "Embed backlog" first.
            </p>
          )}
        </div>
      )}

      <ManualSection section="search" />
    </div>
  )
}
