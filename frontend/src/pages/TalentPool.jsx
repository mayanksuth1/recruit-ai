import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

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

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-cocoa">Talent Pool</h1>
        <p className="text-sm text-cocoa/60">
          Org-wide candidates that persist across roles. Import exported search
          results as CSV, or paste rows directly.
        </p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {result && (
        <div className="rounded-md bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-800">
          Imported {result.inserted} new, updated {result.updated} existing.
          {result.warnings?.length > 0 && (
            <span className="text-amber-700"> {result.warnings.length} row(s) skipped.</span>
          )}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <label className="block bg-white/70 rounded-3xl border-2 border-dashed border-peach p-6 text-center cursor-pointer hover:border-rosy">
          <span className="text-sm text-cocoa/70">
            {busy ? 'Importing…' : 'Upload CSV file (name, email, title, company, skills…)'}
          </span>
          <input ref={fileRef} type="file" accept=".csv,text/csv" hidden disabled={busy}
            onChange={(e) => e.target.files?.[0] && importData({ file: e.target.files[0] })} />
        </label>
        <div className="card p-4 space-y-2">
          <textarea rows={4} value={pasteText} onChange={(e) => setPasteText(e.target.value)}
            placeholder={'Or paste CSV text:\nName,Email,Title,Company,Skills\nJane Doe,jane@x.com,Backend Engineer,Acme,"Python, SQL"'}
            className="w-full rounded-2xl border border-blush px-3 py-2 text-xs font-mono" />
          <button disabled={busy || !pasteText.trim()} onClick={() => importData({ text: pasteText })}
            className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-1.5 text-sm font-medium disabled:opacity-50">
            Import pasted rows
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={async () => {
          setBusy(true); setError('')
          try { setDupes((await api('/api/talent-pool/duplicates')).pairs) } catch (err) { setError(err.message) }
          setBusy(false)
        }} disabled={busy}
          className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-3 py-1.5 text-sm disabled:opacity-50">
          Scan for duplicates
        </button>
        {dupes !== null && (
          <span className="text-sm text-cocoa/60">
            {dupes.length === 0 ? 'No likely duplicates found.' : `${dupes.length} suspected pair(s):`}
          </span>
        )}
      </div>
      {dupes && dupes.length > 0 && (
        <div className="space-y-1">
          {dupes.map((p, i) => (
            <div key={i} className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
              <strong>{p.a.full_name}</strong> ({p.a.email || 'no email'}) ↔{' '}
              <strong>{p.b.full_name}</strong> ({p.b.email || 'no email'}) — name similarity {p.name_similarity}
              {p.email_match && ', same email'}{p.phone_match && ', same phone'}
            </div>
          ))}
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-cream/70 text-left text-cocoa/60">
            <tr>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Title / Company</th>
              <th className="px-4 py-2 font-medium">Contact</th>
              <th className="px-4 py-2 font-medium">Skills</th>
              <th className="px-4 py-2 font-medium">Source</th>
            </tr>
          </thead>
          <tbody>
            {pool.map((p) => (
              <tr key={p.id} className="border-t border-blush/40">
                <td className="px-4 py-2 font-medium text-cocoa">{p.full_name}</td>
                <td className="px-4 py-2 text-cocoa/70">
                  {[p.current_title, p.current_company].filter(Boolean).join(' · ')}
                </td>
                <td className="px-4 py-2 text-cocoa/60">{p.email || p.phone || '–'}</td>
                <td className="px-4 py-2 text-cocoa/60 max-w-56 truncate">{p.skills || '–'}</td>
                <td className="px-4 py-2 text-cocoa/45 text-xs">{p.source}</td>
              </tr>
            ))}
            {pool.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-cocoa/45">
                Pool is empty — import a CSV above.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-cocoa/45">
        LinkedIn note: live profile search/scraping isn't supported (no public API;
        violates LinkedIn ToS). Export search results to CSV and import here. A
        partner-API integration point exists at
        <code> backend/app/sourcing/connectors/linkedin.py</code>.
      </p>
    </div>
  )
}
