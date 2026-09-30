import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { EmptyState, PageFrame, PageHeader } from '../components/Page'

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
    <PageFrame>
      <PageHeader title="Search" section="search"
        subtitle="Describe who you're looking for in plain language. Results are ranked by meaning, not keywords." />

      {backlog?.pending > 0 && (
        <p className="text-sm text-amber-900 bg-butter/50 border border-butter rounded-md px-3 py-2">
          {backlog.pending} item(s) have changed since they were last embedded and will not
          match until you run <Link to="/ai-interviews" className="underline">Embed backlog</Link>.
        </p>
      )}

      <form role="search" onSubmit={run} className="card flex flex-col gap-3.5 px-6 py-[22px]">
        <div className="flex flex-col gap-2.5 sm:flex-row">
          <label className="flex flex-1 flex-col gap-2 text-sm font-medium text-ink-2">
            Search query
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. led a payments migration to an event-driven architecture"
              className="h-[52px] rounded-[10px] border px-4 text-[17px] text-ink" />
          </label>
          <button type="submit" disabled={busy || query.trim().length < 2 || kinds.length === 0}
            className="btn-primary h-[52px] self-end px-6 text-base">
            {busy ? 'Searching…' : 'Search'}
          </button>
        </div>
        <fieldset className="m-0 flex flex-wrap items-center gap-2.5 border-0 p-0">
          <legend className="float-left mr-1.5 font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-ink-muted">Scope</legend>
          {KINDS.map((k) => {
            const on = kinds.includes(k.key)
            return (
              <label key={k.key}
                className={`inline-flex h-[34px] cursor-pointer items-center gap-2 rounded-full border px-3 text-sm font-medium ${on ? 'border-accent bg-[#2A1414] text-ink' : 'border-line-strong text-ink-2'}`}>
                <input type="checkbox" checked={on} onChange={() => toggleKind(k.key)} className="m-0" />
                {k.label}
              </label>
            )
          })}
        </fieldset>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {results && (
        <section className="flex flex-col gap-3">
          <div className="flex justify-between font-mono text-[13px] font-medium text-ink-muted">
            <span>{results.length} result{results.length === 1 ? '' : 's'}</span><span>Sorted by relevance</span>
          </div>
          {results.map((r) => (
            <article key={r.embedding_id} className="card grid grid-cols-[88px_minmax(0,1fr)] items-start gap-5 px-[22px] py-[18px] md:grid-cols-[88px_minmax(0,1fr)_auto]">
              <div className="flex flex-col gap-1" title={`cosine distance ${r.distance.toFixed(4)}`}>
                <span className="dot-num text-[30px] text-accent">.{Math.round(r.similarity * 100).toString().padStart(2, '0')}</span>
                <span className="font-mono text-[12px] font-medium tracking-[0.08em] text-ink-muted">MATCH</span>
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <div className="text-[17px] font-semibold text-ink">{r.candidate_name || 'Unnamed'}</div>
                {/* The matched chunk itself, not a summary of it: the text the
                    ranking was actually computed from. */}
                <p className="m-0 line-clamp-6 whitespace-pre-wrap text-[15px] leading-relaxed text-ink-2">{r.snippet}</p>
                {r.session_id && (
                  <Link to={`/ai-interviews/${r.session_id}`} className="text-sm font-medium no-underline">Open the full interview →</Link>
                )}
              </div>
              <span className="hidden whitespace-nowrap rounded-md border border-line-strong px-[9px] py-1 font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-ink-2 md:inline">
                {r.source_kind === 'transcript' ? 'Interview answer' : 'Profile'}
              </span>
            </article>
          ))}
          {results.length === 0 && (
            <EmptyState className="bg-surface" title="Nothing matched">
              If you have just added candidates, run "Embed backlog" on AI Interviews first, then search again.
            </EmptyState>
          )}
        </section>
      )}

      <ManualSection section="search" />
    </PageFrame>
  )
}
