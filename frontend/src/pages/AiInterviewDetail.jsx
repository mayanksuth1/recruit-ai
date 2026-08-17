import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { statusLabel, statusStyles } from './AiInterviews'

// The evidence quote was matched by the database against a WHITESPACE-SQUASHED
// copy of the answer, so `evidence_offset` is an offset into that squashed text
// and slicing the raw answer by it would land in the wrong place. Rather than
// re-squash for display (which would flatten the candidate's paragraphs), find
// the quote again with a whitespace-tolerant pattern built from its own tokens.
// Same notion of "verbatim" as ai_squash_ws, applied to formatted text.
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function locate(answer, quote) {
  if (!answer || !quote) return null
  const tokens = quote.trim().split(/\s+/).filter(Boolean).map(escapeRe)
  if (!tokens.length) return null
  const m = new RegExp(tokens.join('\\s+')).exec(answer)
  return m ? { start: m.index, end: m.index + m[0].length } : null
}

function Answer({ text, quote }) {
  const hit = locate(text, quote)
  if (!hit) return <span className="whitespace-pre-wrap">{text}</span>
  return (
    <span className="whitespace-pre-wrap">
      {text.slice(0, hit.start)}
      <mark className="bg-butter rounded px-0.5">{text.slice(hit.start, hit.end)}</mark>
      {text.slice(hit.end)}
    </span>
  )
}

const checkExplain = {
  verbatim: 'quoted verbatim from the transcript',
  not_verbatim: 'this quote does not appear in the candidate’s answers',
  too_short: 'a fragment, not a citation (under 5 words or 25 characters)',
  empty: 'the model returned no quote for this criterion',
  no_transcript: 'there are no answers to quote from',
  unchecked: 'not checked',
}

export default function AiInterviewDetail() {
  const { sessionId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [focus, setFocus] = useState(null)   // the criterion whose quote is lit up
  const [elapsed, setElapsed] = useState(0)
  const turnRefs = useRef({})
  const timer = useRef(null)

  const load = async () => {
    try { setData(await api(`/api/ai-interviews/${sessionId}`)) }
    catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [sessionId])

  // Scoring runs on the quality model and takes around three minutes; without
  // an elapsed count a static "Scoring…" is indistinguishable from a hang.
  const runScoring = async () => {
    setBusy(true)
    setError('')
    setElapsed(0)
    clearInterval(timer.current)
    timer.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    try { setData(await api(`/api/ai-interviews/${sessionId}/score`, { method: 'POST' })) }
    catch (err) { setError(err.message) }
    clearInterval(timer.current)
    setBusy(false)
  }

  useEffect(() => () => clearInterval(timer.current), [])

  const jumpTo = (criterion) => {
    setFocus(criterion)
    const node = turnRefs.current[criterion.evidence_turn_ordinal]
    if (node) node.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  if (error && !data) return <div className="max-w-3xl mx-auto p-8"><p className="text-sm text-red-600">{error}</p></div>
  if (!data) return null

  const { session, state, turns, score_card: card, totals, evidence_audit: audit } = data
  const total = totals?.[0]
  const rejected = session.status === 'scoring_rejected'
  const scorable = session.status === 'completed' || rejected

  return (
    <div className="max-w-3xl mx-auto p-8 space-y-6">
      <Link to="/ai-interviews" className="text-sm text-cocoa/60 hover:text-cocoa">&larr; All AI interviews</Link>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-cocoa">{session.candidates?.full_name}</h1>
          <p className="text-sm text-cocoa/60">
            {session.roles?.title || 'No role'} ·{' '}
            <span className={`text-xs px-2 py-0.5 rounded-full ${statusStyles[session.status] || ''}`}>
              {statusLabel[session.status] || session.status}
            </span>{' '}
            · {state.answered_count}/{state.question_target} answered
          </p>
        </div>
        {scorable && (
          <div className="shrink-0 text-center">
            <button onClick={runScoring} disabled={busy}
              className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-semibold disabled:opacity-50">
              {busy ? `Scoring… ${elapsed}s` : rejected ? 'Re-run scoring' : 'Run scoring'}
            </button>
            {busy && <p className="mt-1 text-xs text-cocoa/45">Usually 2–3 minutes.</p>}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {rejected && (
        <div className="rounded-2xl bg-rosy/25 border border-rosy p-4 space-y-2">
          <p className="text-sm font-semibold text-rose-900">Scoring rejected — no score card is shown.</p>
          <p className="text-sm text-rose-900/80">
            At least one criterion cited evidence that is not in this candidate’s transcript.
            A card where some quotes are real and one is invented is worse than no card,
            because the real ones make the invented one look checked. The rejected run is
            kept below so it can be inspected.
          </p>
          <ul className="text-sm text-rose-900/90 space-y-1 pt-1">
            {audit.filter((a) => a.evidence_check !== 'verbatim').map((a) => (
              <li key={a.criterion_key}>
                <span className="font-mono text-xs">{a.criterion_key}</span> — {checkExplain[a.evidence_check]}
                {a.evidence_quote && <em className="block text-rose-900/60">“{a.evidence_quote}”</em>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {card.length > 0 && (
        <div className="card p-6 space-y-5">
          <div className="flex items-baseline justify-between">
            <h2 className="font-extrabold text-cocoa">Score card</h2>
            {total && (
              <span className="text-sm text-cocoa/70">
                <strong className="text-lg text-cocoa">{total.percent}%</strong>{' '}
                ({total.weighted_score} / {total.weighted_max} weighted)
              </span>
            )}
          </div>
          {card.map((c) => (
            <div key={c.criterion_key} className="space-y-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-semibold text-cocoa">{c.label}</span>
                <span className="text-sm text-cocoa/70 shrink-0">
                  {c.score} / {c.max_score} <span className="text-xs text-cocoa/40">×{c.weight}</span>
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-blush/50 overflow-hidden">
                <div className="h-full bg-mint" style={{ width: `${(c.score / c.max_score) * 100}%` }} />
              </div>
              {c.rationale && <p className="text-sm text-cocoa/70">{c.rationale}</p>}
              {c.evidence_quote && (
                <button onClick={() => jumpTo(c)}
                  className={`block w-full text-left text-sm italic rounded-xl px-3 py-2 border transition-colors ${
                    focus?.criterion_key === c.criterion_key
                      ? 'bg-butter/60 border-butter'
                      : 'bg-cream/60 border-blush/60 hover:border-rosy'
                  }`}>
                  “{c.evidence_quote}”
                  <span className="not-italic text-xs text-cocoa/45 block mt-0.5">
                    → answer {c.evidence_turn_ordinal}, character {c.evidence_offset}
                  </span>
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card p-6 space-y-5">
        <h2 className="font-extrabold text-cocoa">Transcript</h2>
        {turns.map((t) => (
          <div key={t.ordinal} ref={(el) => { turnRefs.current[t.ordinal] = el }}
            className={`space-y-1 rounded-2xl px-3 py-2 -mx-3 transition-colors ${
              focus?.evidence_turn_ordinal === t.ordinal ? 'bg-butter/20' : ''
            }`}>
            <p className="text-sm font-semibold text-cocoa">
              Q{t.ordinal}. {t.question_text}
              {t.source_turn_ordinal && (
                <span className="ml-2 font-normal text-xs text-cocoa/40">
                  written from answer {t.source_turn_ordinal}
                </span>
              )}
            </p>
            <p className="text-sm text-cocoa/70">
              {t.answer_text
                ? <Answer text={t.answer_text}
                    quote={focus?.evidence_turn_ordinal === t.ordinal ? focus.evidence_quote : null} />
                : <em className="text-cocoa/40">unanswered</em>}
            </p>
          </div>
        ))}
        {turns.length === 0 && <p className="text-sm text-cocoa/45">The candidate has not opened the link yet.</p>}
      </div>
    </div>
  )
}
