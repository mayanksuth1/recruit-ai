import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { ManualSection } from '../components/ManualHelp'
import { Label, PageFrame, PageHeader } from '../components/Page'

export default function TalentPool() {
  const [pool, setPool] = useState([])
  const [pasteText, setPasteText] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dupes, setDupes] = useState(null)
  const fileRef = useRef(null)

  const load = async () => {
    try {
      setPool(await api('/api/talent-pool'))
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [])

  const importData = async ({ file, text }) => {
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const formData = new FormData()
      if (file) formData.append('file', file)
      if (text) formData.append('csv_text', text)
      const res = await api('/api/talent-pool/import', { method: 'POST', formData })
      setResult(res)
      setPasteText('')
      if (fileRef.current) fileRef.current.value = ''
      await load()
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const scan = async () => {
    setBusy(true); setError('')
    try { setDupes((await api('/api/talent-pool/duplicates')).pairs) } catch (err) { setError(err.message) }
    setBusy(false)
  }
  const empty = pool.length === 0
  const skillsOf = (p) => String(p.skills || '').split(/[,;|]/).map((k) => k.trim()).filter(Boolean).slice(0, 4)
  const th = 'px-4 py-3.5 text-left font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-ink-subtle'

  return (
    <PageFrame wide>
      <PageHeader title="Talent Pool" section="talent-pool"
        subtitle="Every candidate you've imported, across all roles."
        actions={
          <button onClick={scan} disabled={busy || empty}
            className={empty ? 'h-[42px] cursor-not-allowed rounded-[10px] border border-line-strong bg-surface px-[18px] text-[15px] font-semibold text-ink-subtle' : 'btn-primary'}>
            Scan for duplicates
          </button>
        } />
      {error && <p className="text-sm text-red-600">{error}</p>}
      {result && (
        <div className="rounded-[10px] border border-green-200 bg-green-50 px-4 py-2 text-sm text-green-800">
          Imported {result.inserted} new, updated {result.updated} existing.
          {result.warnings?.length > 0 && <span className="text-amber-700"> {result.warnings.length} row(s) skipped.</span>}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {empty ? (
          <label className="dot-grid flex min-h-[240px] cursor-pointer flex-col items-center justify-center gap-3 rounded-[14px] border-[1.5px] border-dashed border-accent bg-surface p-7 text-center">
            <span className="dot-num text-[40px] text-accent">CSV</span>
            <span className="text-lg font-semibold text-ink">{busy ? 'Importing…' : 'Drop a CSV file to import candidates'}</span>
            <span className="text-sm leading-normal text-ink-muted">Columns: name, title, company, email, phone, skills, source</span>
            <span className="btn-primary pointer-events-none h-10">Browse files</span>
            <input ref={fileRef} type="file" accept=".csv,text/csv" hidden disabled={busy}
              onChange={(e) => e.target.files?.[0] && importData({ file: e.target.files[0] })} />
          </label>
        ) : (
          <label className="flex cursor-pointer items-center gap-5 rounded-[14px] border-[1.5px] border-dashed border-line-strong bg-surface px-6 py-5">
            <span className="dot-num text-[32px] text-accent">CSV</span>
            <span className="flex flex-1 flex-col gap-1">
              <span className="text-base font-semibold text-ink">{busy ? 'Importing…' : 'Drop a CSV file to import'}</span>
              <span className="text-sm text-ink-muted">{pool.length.toLocaleString()} candidates in the pool</span>
            </span>
            <span className="btn-ghost pointer-events-none">Browse files</span>
            <input ref={fileRef} type="file" accept=".csv,text/csv" hidden disabled={busy}
              onChange={(e) => e.target.files?.[0] && importData({ file: e.target.files[0] })} />
          </label>
        )}
        <div className={`card flex gap-3 ${empty ? 'flex-col px-6 py-[22px]' : 'items-end px-5 py-4'}`}>
          <label className="flex flex-1 flex-col gap-2 text-sm font-medium text-ink-2">
            {empty ? 'Or paste CSV rows' : 'Paste CSV rows'}
            <textarea rows={empty ? 6 : 2} value={pasteText} onChange={(e) => setPasteText(e.target.value)}
              placeholder="name,title,company,email,phone,skills,source"
              className="resize-y rounded-[10px] border px-3 py-2.5 font-mono text-sm leading-relaxed text-ink" />
          </label>
          <button disabled={busy || !pasteText.trim()} onClick={() => importData({ text: pasteText })}
            className={`btn-ghost h-10 disabled:opacity-50 ${empty ? 'self-start' : 'self-end'}`}>
            Import pasted rows
          </button>
        </div>
      </div>

      {dupes !== null && (
        <section className="card flex flex-col gap-3 px-6 py-5">
          <Label right={dupes.length ? `${dupes.length} suspected pair(s)` : null}>Duplicate scan</Label>
          {dupes.length === 0 ? (
            <div className="text-sm text-ink-muted">No likely duplicates found.</div>
          ) : dupes.map((p, i) => (
            <div key={i} className="row-inset flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm text-ink-2">
              <strong className="text-ink">{p.a.full_name}</strong><span className="text-ink-muted">{p.a.email || 'no email'}</span>
              <span className="text-accent">↔</span>
              <strong className="text-ink">{p.b.full_name}</strong><span className="text-ink-muted">{p.b.email || 'no email'}</span>
              <span className="ml-auto font-mono text-[13px] text-ink-muted">
                similarity {p.name_similarity}{p.email_match && ' · same email'}{p.phone_match && ' · same phone'}
              </span>
            </div>
          ))}
        </section>
      )}

      {empty ? (
        <section className="card flex flex-col items-start gap-3 p-10">
          <Label n={3}>Candidates · 0</Label>
          <div className="text-xl font-semibold text-ink">Your talent pool is empty</div>
          <div className="max-w-[60ch] text-[15px] leading-relaxed text-ink-muted">
            Import a CSV above. After import, run a duplicate scan to merge people who appear in more than one source.
          </div>
        </section>
      ) : (
        <section className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-6 py-[18px]">
            <Label n={3}>Candidates · {pool.length.toLocaleString()}</Label>
            <div className="font-mono text-[13px] font-medium text-ink-muted">Showing {Math.min(pool.length, 500)}</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[15px] text-ink-2">
              <thead><tr>
                <th className={`${th} pl-6`}>Name</th><th className={th}>Title / Company</th><th className={th}>Contact</th>
                <th className={th}>Skills</th><th className={`${th} pr-6`}>Source</th>
              </tr></thead>
              <tbody>
                {pool.map((p) => (
                  <tr key={p.id} className="border-t border-line">
                    <td className="px-4 py-3.5 pl-6 font-semibold text-ink">{p.full_name}</td>
                    <td className="px-4 py-3.5">
                      <div className="text-ink">{p.current_title || '—'}</div>
                      <div className="text-sm text-ink-muted">{p.current_company}</div>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-sm leading-normal">
                      <div>{p.email || '—'}</div><div className="text-ink-muted">{p.phone}</div>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex flex-wrap gap-1.5">
                        {skillsOf(p).map((k) => (
                          <span key={k} className="rounded-md border border-line-strong bg-[#242120] px-2 py-[3px] text-[13px] font-medium text-ink-2">{k}</span>
                        ))}
                        {!skillsOf(p).length && <span className="text-ink-subtle">—</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 pr-6 font-mono text-[13px] font-medium uppercase tracking-[0.04em] text-ink-2">{(p.source || '').replace('_', ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <p className="text-[13px] text-ink-subtle">
        LinkedIn note: live profile search/scraping isn't supported (no public API; violates LinkedIn ToS).
        Export search results to CSV and import here.
      </p>

      <ManualSection section="talent-pool" />
    </PageFrame>
  )
}
