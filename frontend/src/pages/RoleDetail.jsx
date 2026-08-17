import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import ManualHelp, { ManualSection } from '../components/ManualHelp'

const statusStyles = {
  pending: 'bg-butter/70 text-amber-800',
  approved: 'bg-mint text-teal-800',
  rejected: 'bg-rosy text-rose-800',
}

function CopyBlock({ label, text }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-cocoa/60">{label}</span>
        <button onClick={copy} className="text-xs text-cocoa/60 hover:text-cocoa underline">
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre className="bg-cream/70 rounded-md border border-blush/60 p-3 text-xs whitespace-pre-wrap break-words">{text}</pre>
    </div>
  )
}

export default function RoleDetail() {
  const { roleId } = useParams()
  const [role, setRole] = useState(null)
  const [candidates, setCandidates] = useState([])
  const [error, setError] = useState('')
  const [progress, setProgress] = useState('')
  const [matching, setMatching] = useState(false)
  const [boolSearch, setBoolSearch] = useState(null)
  const [boolBusy, setBoolBusy] = useState(false)
  const [post, setPost] = useState('')          // editable draft text
  const [postMeta, setPostMeta] = useState(null) // { model, generated_at }
  const [postBusy, setPostBusy] = useState(false)
  const [postSaved, setPostSaved] = useState(false)
  const [postCopied, setPostCopied] = useState(false)
  const [postElapsed, setPostElapsed] = useState(0)
  const postRef = useRef(null)
  const postTimer = useRef(null)
  const [selected, setSelected] = useState(new Set())
  const [notice, setNotice] = useState('')
  const [draftingIds, setDraftingIds] = useState(new Set())
  const [schedulingId, setSchedulingId] = useState(null) // candidate id with open panel
  const [schedForm, setSchedForm] = useState({ duration_minutes: 45, attendee: '' })
  const [schedBusy, setSchedBusy] = useState(false)
  // { candidateId, link } — the raw token appears exactly once, in this
  // response. It is not stored anywhere, so if it is lost the only remedy is
  // issuing a new link.
  const [aiLink, setAiLink] = useState(null)
  const [aiBusy, setAiBusy] = useState(null)

  const load = async () => {
    try {
      const r = await api(`/api/roles/${roleId}`)
      setRole(r)
      // The draft is a column on the role, so it rehydrates on every load —
      // that is what makes an edited post survive a refresh.
      setPost(r.linkedin_post_draft || '')
      setPostMeta(
        r.linkedin_post_generated_at
          ? { model: r.linkedin_post_model, generated_at: r.linkedin_post_generated_at }
          : null,
      )
      setCandidates(await api(`/api/roles/${roleId}/candidates`))
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [roleId])

  const upload = async (e) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setError('')
    for (let i = 0; i < files.length; i++) {
      setProgress(`Scoring ${i + 1} of ${files.length}…`)
      try {
        const formData = new FormData()
        formData.append('file', files[i])
        await api(`/api/roles/${roleId}/candidates/upload`, { method: 'POST', formData })
      } catch (err) {
        setError(`${files[i].name}: ${err.message}`)
      }
    }
    e.target.value = ''
    setProgress('')
    load()
  }

  const matchPool = async () => {
    setMatching(true)
    setError('')
    try {
      const res = await api(`/api/roles/${roleId}/match-pool`, { method: 'POST', body: {} })
      if (res.matched === 0 && res.skipped_existing > 0) {
        setError('All pool candidates are already attached to this role.')
      } else if (res.matched === 0) {
        setError('Talent pool is empty — import candidates first.')
      }
      await load()
    } catch (err) { setError(err.message) }
    setMatching(false)
  }

  // Generate/regenerate. The endpoint stores the draft, so a reload brings it
  // back via the role record — nothing here is publish-related.
  //
  // This call runs on the quality model and takes around three minutes. A
  // static "Generating…" over that long reads as a hung page, so the elapsed
  // count is the only signal that anything is still happening.
  const generatePost = async () => {
    setPostBusy(true)
    setError('')
    setPostSaved(false)
    setPostElapsed(0)
    clearInterval(postTimer.current)
    postTimer.current = setInterval(() => setPostElapsed((s) => s + 1), 1000)
    try {
      const res = await api(`/api/roles/${roleId}/linkedin-post`, { method: 'POST' })
      setPost(res.linkedin_post_draft)
      setPostMeta({ model: res.linkedin_post_model, generated_at: res.linkedin_post_generated_at })
    } catch (err) { setError(err.message) }
    clearInterval(postTimer.current)
    setPostBusy(false)
  }

  // Navigating away mid-generation would otherwise leave the interval ticking
  // against an unmounted component.
  useEffect(() => () => clearInterval(postTimer.current), [])

  const savePost = async () => {
    setPostBusy(true)
    setError('')
    try {
      await api(`/api/roles/${roleId}/linkedin-post`, {
        method: 'PUT',
        body: { linkedin_post_draft: post },
      })
      setPostSaved(true)
      setTimeout(() => setPostSaved(false), 1500)
    } catch (err) { setError(err.message) }
    setPostBusy(false)
  }

  // The async clipboard API rejects when the document is not focused or the
  // page is not a secure context. Fall back to a selection-based copy, and if
  // even that fails say so — a silent no-op looks identical to a successful
  // copy and the user only finds out when they paste.
  const copyPost = async () => {
    setError('')
    try {
      await navigator.clipboard.writeText(post)
    } catch {
      const el = postRef.current
      if (!el) { setError('Could not copy — select the text and copy manually.'); return }
      el.focus()
      el.select()
      if (!document.execCommand?.('copy')) {
        setError('Could not copy — select the text and copy manually.')
        return
      }
    }
    setPostCopied(true)
    setTimeout(() => setPostCopied(false), 1500)
  }

  const generateBool = async () => {
    setBoolBusy(true)
    setError('')
    try {
      setBoolSearch(await api(`/api/roles/${roleId}/boolean-search`, { method: 'POST' }))
    } catch (err) { setError(err.message) }
    setBoolBusy(false)
  }

  const setStatus = async (candidateId, shortlist_status) => {
    try {
      await api(`/api/candidates/${candidateId}/shortlist`, {
        method: 'PATCH',
        body: { shortlist_status },
      })
      setCandidates((cs) => cs.map((c) => (c.id === candidateId ? { ...c, shortlist_status } : c)))
    } catch (err) { setError(err.message) }
  }

  const bulkSet = async (shortlist_status) => {
    try {
      await api('/api/candidates/bulk-shortlist', {
        method: 'PATCH',
        body: { candidate_ids: [...selected], shortlist_status },
      })
      setCandidates((cs) => cs.map((c) => (selected.has(c.id) ? { ...c, shortlist_status } : c)))
      setSelected(new Set())
    } catch (err) { setError(err.message) }
  }

  const draftOutreach = async (candidateId) => {
    setDraftingIds((s) => new Set(s).add(candidateId))
    setError('')
    setNotice('')
    try {
      await api(`/api/candidates/${candidateId}/draft-outreach`, { method: 'POST' })
      setNotice('Outreach draft created — review and send it from the Outbox.')
    } catch (err) { setError(err.message) }
    setDraftingIds((s) => {
      const next = new Set(s)
      next.delete(candidateId)
      return next
    })
  }

  const setStage = async (candidateId, stage) => {
    setError('')
    setNotice('')
    try {
      const res = await api(`/api/candidates/${candidateId}/stage`, {
        method: 'PATCH',
        body: { stage },
      })
      setCandidates((cs) => cs.map((c) => (c.id === candidateId ? { ...c, stage } : c)))
      if (res.status_update_draft) {
        setNotice('Stage updated. A status-update email was drafted for review in the Outbox (not sent).')
      }
    } catch (err) { setError(err.message) }
  }

  const approveOffer = async (candidateId, revoke = false) => {
    setError('')
    setNotice('')
    try {
      const path = revoke ? 'revoke-offer-approval' : 'approve-offer'
      await api(`/api/candidates/${candidateId}/${path}`, { method: 'POST' })
      setCandidates((cs) => cs.map((c) =>
        c.id === candidateId ? { ...c, offer_approved_at: revoke ? null : new Date().toISOString() } : c))
      setNotice(revoke ? 'Offer approval revoked.' : 'Approved for offer/closure stages (gate 2).')
    } catch (err) { setError(err.message) }
  }

  const proposeInterview = async (candidateId) => {
    setSchedBusy(true)
    setError('')
    setNotice('')
    try {
      const body = {
        duration_minutes: Number(schedForm.duration_minutes) || 45,
        attendee_emails: schedForm.attendee.trim() ? [schedForm.attendee.trim()] : [],
      }
      const res = await api(`/api/candidates/${candidateId}/interviews/propose`, { method: 'POST', body })
      setNotice(`${res.slots.length} slots proposed from your calendar. The scheduling-link email is drafted in the Outbox — review and send it.`)
      setSchedulingId(null)
    } catch (err) { setError(err.message) }
    setSchedBusy(false)
  }

  const issueAiInterview = async (candidateId) => {
    setAiBusy(candidateId)
    setError('')
    setNotice('')
    try {
      const res = await api(`/api/candidates/${candidateId}/ai-interview`, {
        method: 'POST', body: { role_id: roleId, question_target: 5 },
      })
      setAiLink({ candidateId, link: res.link })
      setNotice('Interview link issued — send it to the candidate. It works once and expires in 72 hours.')
    } catch (err) { setError(err.message) }
    setAiBusy(null)
  }

  const toggle = (id) => {
    setSelected((s) => {
      const next = new Set(s)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const ranked = [...candidates].sort(
    (a, b) => (b.scores?.[0]?.overall_score ?? -1) - (a.scores?.[0]?.overall_score ?? -1),
  )
  const allSelected = ranked.length > 0 && selected.size === ranked.length

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-6">
      <Link to="/" className="text-sm text-cocoa/60 hover:text-cocoa">&larr; All roles</Link>
      {role && (
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-extrabold text-cocoa">{role.title}</h1>
            <ManualHelp section="roles" />
          </div>
          <p className="text-sm text-cocoa/60 mt-1 whitespace-pre-wrap line-clamp-4">{role.description}</p>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {notice && (
        <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">{notice}</p>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <label className="block bg-white/70 rounded-3xl border-2 border-dashed border-peach p-6 text-center cursor-pointer hover:border-rosy">
          <span className="text-sm text-cocoa/70">
            {progress || 'Upload resume PDF(s) — scored against the JD'}
          </span>
          <input type="file" accept="application/pdf" multiple hidden onChange={upload} disabled={!!progress} />
        </label>
        <div className="card p-4 flex flex-col gap-2 justify-center">
          <button onClick={matchPool} disabled={matching}
            className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-medium disabled:opacity-50">
            {matching ? 'Scoring pool against JD…' : 'Match from talent pool'}
          </button>
          <button onClick={generateBool} disabled={boolBusy}
            className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-4 py-2 text-sm font-medium disabled:opacity-50">
            {boolBusy ? 'Generating…' : 'Generate Boolean search'}
          </button>
          <button onClick={generatePost} disabled={postBusy}
            className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-4 py-2 text-sm font-medium disabled:opacity-50">
            {postBusy
              ? `Writing the post… ${postElapsed}s`
              : post ? 'Regenerate LinkedIn post' : 'Generate LinkedIn post'}
          </button>
          {postBusy && (
            <p className="text-xs text-cocoa/45 text-center">
              Usually takes 2–3 minutes. You can keep working — leaving this page cancels it.
            </p>
          )}
        </div>
      </div>

      {post && (
        <div className="card p-5 space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h2 className="font-medium text-cocoa/80">LinkedIn post draft</h2>
            <span className="text-xs text-cocoa/45">
              Draft only — copy it and post it yourself.
            </span>
          </div>

          <textarea
            ref={postRef}
            rows={14}
            value={post}
            onChange={(e) => { setPost(e.target.value); setPostSaved(false) }}
            className="w-full rounded-2xl border border-blush px-3 py-2 text-sm whitespace-pre-wrap"
          />

          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={copyPost}
              className="rounded-full bg-cocoa text-cream shadow-md hover:scale-[1.03] active:scale-95 transition-transform px-4 py-2 text-sm font-medium">
              {postCopied ? 'Copied!' : 'Copy'}
            </button>
            <button onClick={savePost} disabled={postBusy}
              className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-4 py-2 text-sm font-medium disabled:opacity-50">
              {postSaved ? 'Saved!' : 'Save edits'}
            </button>
            <button onClick={generatePost} disabled={postBusy}
              className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-4 py-2 text-sm font-medium disabled:opacity-50">
              {postBusy ? `Rewriting… ${postElapsed}s` : 'Regenerate'}
            </button>
            {postMeta?.generated_at && (
              <span className="text-xs text-cocoa/45">
                Generated {new Date(postMeta.generated_at).toLocaleString()}
                {postMeta.model ? ` · ${postMeta.model}` : ''}
              </span>
            )}
          </div>
        </div>
      )}

      {boolSearch && (
        <div className="card p-5 space-y-4">
          <h2 className="font-medium text-cocoa/80">Boolean search strings</h2>
          <CopyBlock label="LinkedIn people search" text={boolSearch.linkedin} />
          <CopyBlock label="Google X-ray" text={boolSearch.google_xray} />
          {boolSearch.tips && <p className="text-xs text-cocoa/60">{boolSearch.tips}</p>}
        </div>
      )}

      {ranked.length > 0 && (
        <div className="flex items-center gap-3 card px-4 py-2">
          <label className="flex items-center gap-2 text-sm text-cocoa/70">
            <input type="checkbox" checked={allSelected}
              onChange={() => setSelected(allSelected ? new Set() : new Set(ranked.map((c) => c.id)))} />
            Select all
          </label>
          {selected.size > 0 && (
            <>
              <span className="text-sm text-cocoa/60">{selected.size} selected</span>
              <button onClick={() => bulkSet('approved')}
                className="rounded-full bg-mint text-teal-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-1 text-xs font-medium">Approve selected</button>
              <button onClick={() => bulkSet('rejected')}
                className="rounded-full bg-rosy text-rose-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-1 text-xs font-medium">Reject selected</button>
            </>
          )}
        </div>
      )}

      <div className="space-y-3">
        {ranked.map((c) => {
          const s = c.scores?.[0]
          return (
            <div key={c.id} className="card p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <input type="checkbox" className="mt-1.5" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-cocoa">{c.full_name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${statusStyles[c.shortlist_status]}`}>
                        {c.shortlist_status}
                      </span>
                      {c.source === 'pool_match' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-babyblue/70 text-sky-800">pool</span>
                      )}
                    </div>
                    <p className="text-xs text-cocoa/45">{[c.email, c.phone].filter(Boolean).join(' · ')}</p>
                  </div>
                </div>
                {s && (
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <div className={`w-14 h-14 rounded-full flex items-center justify-center text-xl font-extrabold text-cocoa shadow-inner ${
                      s.overall_score >= 70 ? 'bg-mint' : s.overall_score >= 40 ? 'bg-butter' : 'bg-rosy/70'
                    }`}>
                      {Math.round(s.overall_score)}
                    </div>
                    <div className="text-xs text-cocoa/45">
                      skills {s.skills_score ?? '–'} · exp {s.experience_score ?? '–'} · edu {s.education_score ?? '–'}
                    </div>
                  </div>
                )}
              </div>
              {s?.rationale && <p className="text-sm text-cocoa/70 mt-3">{s.rationale}</p>}
              <div className="flex items-center gap-2 mt-4 flex-wrap">
                <button onClick={() => setStatus(c.id, 'approved')}
                  className="rounded-full bg-mint text-teal-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-1.5 text-xs font-medium">Approve</button>
                <button onClick={() => setStatus(c.id, 'rejected')}
                  className="rounded-full bg-rosy text-rose-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-1.5 text-xs font-medium">Reject</button>
                {c.shortlist_status !== 'pending' && (
                  <button onClick={() => setStatus(c.id, 'pending')}
                    className="rounded-full border-2 border-blush bg-white text-cocoa/70 px-3 py-1.5 text-xs">Reset</button>
                )}
                {c.shortlist_status === 'approved' && (
                  <>
                    <button onClick={() => draftOutreach(c.id)} disabled={draftingIds.has(c.id)}
                      className="rounded-full bg-babyblue text-sky-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-1.5 text-xs font-medium disabled:opacity-50">
                      {draftingIds.has(c.id) ? 'Drafting…' : 'Draft outreach'}
                    </button>
                    <button onClick={() => setSchedulingId(schedulingId === c.id ? null : c.id)}
                      className="rounded-full bg-lavender text-indigo-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-1.5 text-xs font-medium">
                      Schedule interview
                    </button>
                    <button onClick={() => issueAiInterview(c.id)} disabled={aiBusy === c.id}
                      className="rounded-full bg-mint text-teal-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-1.5 text-xs font-medium disabled:opacity-50"
                      title="Issue a single-use async AI interview link (5 questions, expires in 72h)">
                      {aiBusy === c.id ? 'Issuing…' : 'AI interview'}
                    </button>
                    {c.offer_approved_at ? (
                      <button onClick={() => approveOffer(c.id, true)}
                        className="rounded-md border border-emerald-300 bg-emerald-50 text-emerald-700 px-3 py-1.5 text-xs font-medium"
                        title="Gate 2 passed — click to revoke">
                        ✓ Offer approved
                      </button>
                    ) : (
                      <button onClick={() => approveOffer(c.id)}
                        className="rounded-full border-2 border-blush bg-white text-cocoa/80 px-3 py-1.5 text-xs font-medium"
                        title="Gate 2: required before the offer/closed stages">
                        Approve for offer
                      </button>
                    )}
                  </>
                )}
                <label className="ml-auto flex items-center gap-1.5 text-xs text-cocoa/60">
                  stage
                  <select value={c.stage || 'screening'} onChange={(e) => setStage(c.id, e.target.value)}
                    className="rounded-2xl border border-blush px-2 py-1 text-xs">
                    {['screening', 'outreach', 'interview', 'offer', 'closed'].map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>
              </div>
              {schedulingId === c.id && (
                <div className="mt-3 flex items-end gap-3 rounded-lg bg-cream/70 border border-blush/60 p-3">
                  <label className="text-xs text-cocoa/60">
                    Duration (min)
                    <input type="number" min={15} max={240} step={15} value={schedForm.duration_minutes}
                      onChange={(e) => setSchedForm({ ...schedForm, duration_minutes: e.target.value })}
                      className="mt-1 block w-24 rounded-2xl border border-blush px-2 py-1.5 text-sm" />
                  </label>
                  <label className="text-xs text-cocoa/60 flex-1">
                    Hiring manager email (optional, joins the invite)
                    <input type="email" value={schedForm.attendee} placeholder="manager@company.com"
                      onChange={(e) => setSchedForm({ ...schedForm, attendee: e.target.value })}
                      className="mt-1 block w-full rounded-2xl border border-blush px-2 py-1.5 text-sm" />
                  </label>
                  <button onClick={() => proposeInterview(c.id)} disabled={schedBusy}
                    className="rounded-full bg-lavender text-indigo-900 hover:scale-[1.03] active:scale-95 transition-transform px-3 py-2 text-xs font-medium disabled:opacity-50">
                    {schedBusy ? 'Checking calendar…' : 'Propose slots + draft email'}
                  </button>
                </div>
              )}
              {aiLink?.candidateId === c.id && (
                <div className="mt-3 rounded-lg bg-cream/70 border border-blush/60 p-3 space-y-2">
                  <CopyBlock label="Single-use AI interview link — copy it now" text={aiLink.link} />
                  <p className="text-xs text-cocoa/50">
                    Only the hash of this token is stored, so it cannot be shown again.
                    Lose it and you must issue a new link.
                  </p>
                </div>
              )}
            </div>
          )
        })}
        {candidates.length === 0 && (
          <p className="text-sm text-cocoa/45">No candidates yet — upload resumes or match from the talent pool.</p>
        )}
      </div>

      <ManualSection section="roles" />
    </div>
  )
}
