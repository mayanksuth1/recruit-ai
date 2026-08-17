import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { apiUrl } from '../lib/api'

// Public page — the candidate opens this from their single-use interview link.
// No login; the token in the URL is the whole authentication.
//
// THIS COMPONENT DELIBERATELY HOLDS NO INTERVIEW STATE. The question, the
// ordinal and every prior turn come from the server on every load, and the only
// thing living in the browser is the answer currently being typed. That is what
// makes a closed tab survivable: there is nothing here to lose. Do not "improve"
// this by caching the question or the progress in localStorage — the server's
// copy is the one the transcript is built from, and a cached question that
// disagrees with it would be a question the candidate was never actually asked.
export default function AiInterview() {
  const { token } = useParams()
  const [view, setView] = useState(null)
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')
  const [dead, setDead] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const res = await fetch(apiUrl(`/api/public/ai-interview/${token}`))
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        // 404 (unknown token) and 410 (expired or finished) are both terminal —
        // there is no retry that helps, so say so plainly instead of showing a
        // form the candidate cannot submit.
        if (res.status === 404 || res.status === 410) return setDead(data.detail || 'This link is no longer active.')
        throw new Error(data.detail || res.statusText)
      }
      setView(data)
      setAnswer('')
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [token])

  const submit = async () => {
    if (!answer.trim()) return
    setBusy(true)
    setError('')
    try {
      const res = await fetch(apiUrl(`/api/public/ai-interview/${token}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ordinal: view.ordinal, answer }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        if (res.status === 410) return setDead(data.detail || 'This link is no longer active.')
        throw new Error(data.detail || res.statusText)
      }
      setView(data)
      setAnswer('')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  if (dead) {
    return (
      <Shell>
        <p className="text-sm text-cocoa/70">{dead}</p>
      </Shell>
    )
  }
  if (error && !view) return <Shell><p className="text-sm text-red-600">{error}</p></Shell>
  if (!view) return null

  if (view.state === 'completed') {
    return (
      <Shell title={`Interview — ${view.role_title || 'your application'}`} subtitle={view.org_name}>
        <div className="rounded-2xl bg-green-50 border border-green-200 p-4 space-y-1">
          <p className="text-sm font-semibold text-green-800">
            All done — thank you{view.candidate_name ? `, ${view.candidate_name.split(' ')[0]}` : ''}.
          </p>
          <p className="text-sm text-green-700">
            You answered all {view.answered} questions. The hiring team will review your
            responses and be in touch. You can close this tab.
          </p>
        </div>
      </Shell>
    )
  }

  const pct = Math.round((view.answered / view.question_target) * 100)

  return (
    <Shell title={`Interview — ${view.role_title || 'your application'}`} subtitle={view.org_name}>
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-cocoa/55">
          <span>Question {view.ordinal} of {view.question_target}</span>
          <span>{view.answered} answered</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-blush/50 overflow-hidden">
          <div className="h-full bg-mint transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {view.history.length > 0 && (
        <details className="rounded-2xl border border-blush/70 bg-cream/50 px-4 py-3">
          <summary className="cursor-pointer text-xs font-semibold text-cocoa/60">
            Your earlier answers ({view.history.length})
          </summary>
          <div className="mt-3 space-y-3">
            {view.history.map((t) => (
              <div key={t.ordinal} className="text-sm">
                <p className="font-semibold text-cocoa/80">Q{t.ordinal}. {t.question}</p>
                <p className="text-cocoa/60 whitespace-pre-wrap mt-0.5">{t.answer}</p>
              </div>
            ))}
          </div>
        </details>
      )}

      <div className="space-y-3">
        <p className="text-base font-semibold text-cocoa leading-relaxed">{view.question}</p>
        <textarea
          rows={9}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Take your time — specifics beat polish."
          className="w-full rounded-2xl border border-blush px-4 py-3 text-sm leading-relaxed focus:outline-none focus:border-rosy"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex items-center justify-between">
          <p className="text-xs text-cocoa/45">
            Your progress is saved as you go — you can close this tab and return to this
            same link.
          </p>
          <button
            onClick={submit}
            disabled={busy || !answer.trim()}
            className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-5 py-2 text-sm font-semibold disabled:opacity-40 disabled:hover:scale-100"
          >
            {busy ? 'Saving…' : view.ordinal === view.question_target ? 'Submit final answer' : 'Submit and continue'}
          </button>
        </div>
      </div>
    </Shell>
  )
}

function Shell({ title, subtitle, children }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-2xl card p-8 space-y-6">
        {title && (
          <div>
            <h1 className="text-xl font-extrabold text-cocoa">{title}</h1>
            {subtitle && <p className="text-sm text-cocoa/60">{subtitle}</p>}
          </div>
        )}
        {children}
      </div>
    </div>
  )
}
