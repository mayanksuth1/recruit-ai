import { useEffect, useState } from 'react'
import { MANUAL } from '../lib/manual'
import { ManualSectionBody } from '../components/ManualHelp'
import { apiUrl } from '../lib/api'
import { PageFrame, PageHeader } from '../components/Page'

/**
 * Help centre — design screen 10: a strip of numbered section chips, then one
 * card per screen with its description and the terms it uses. Each card opens
 * the full manual text for that screen, from the same data the per-page
 * "How this works" drawers read (lib/manual.js).
 */

// Strip **bold** markers for the short definitions on the cards.
const plain = (t) => String(t || '').replace(/\*\*/g, '')
const firstSentence = (t) => {
  const s = plain(t)
  const m = s.match(/^.*?[.!?](\s|$)/)
  return (m ? m[0] : s).trim()
}

/* Up to three term/definition pairs that summarise a section: the first
   key-value table if it has one, otherwise each card's heading and its
   opening sentence. */
function termsOf(section) {
  for (const item of section.body) {
    const kv = item.blocks?.find((b) => b.k === 'kv')
    if (kv) return kv.rows.slice(0, 3).map(([term, def]) => ({ term, def: plain(def) }))
  }
  return section.body
    .filter((item) => item.h3)
    .slice(0, 3)
    .map((item) => {
      // Prefer a sentence; fall back to a list's labels or a table's first row.
      const blocks = item.blocks || []
      const p = blocks.find((b) => b.t)
      const list = blocks.find((b) => Array.isArray(b.items))
      const kv = blocks.find((b) => Array.isArray(b.rows))
      const def = p ? firstSentence(p.t)
        : list ? list.items.map((x) => plain(x.label || x.t || x)).join(', ')
        : kv ? kv.rows.map((r) => plain(r[0])).join(', ') : ''
      return { term: item.h3, def }
    })
}

function HelpCard({ section, n, open, onToggle }) {
  return (
    <section id={section.id} className="card flex scroll-mt-24 flex-col gap-3.5 px-6 py-[22px]">
      <div className="flex items-baseline gap-3">
        <span className="dot-num text-[26px] text-accent">{n}</span>
        <h2 className="m-0 text-[19px] font-semibold text-ink">{section.title}</h2>
        <span className="ml-auto font-mono text-[12px] uppercase tracking-[0.08em] text-ink-subtle">{section.tag}</span>
      </div>
      <p className="m-0 text-[15px] leading-relaxed text-ink-2">{plain(section.lede)}</p>
      <dl className="m-0 grid grid-cols-[150px_minmax(0,1fr)] border-t border-line md:grid-cols-[170px_minmax(0,1fr)]">
        {termsOf(section).map((r) => (
          <div key={r.term} className="contents">
            <dt className="border-b border-line py-2.5 pr-3 font-mono text-[13px] font-medium leading-normal text-ink">{r.term}</dt>
            <dd className="m-0 border-b border-line py-2.5 text-sm leading-normal text-ink-muted">{r.def}</dd>
          </div>
        ))}
      </dl>
      <button onClick={onToggle} className="btn-ghost h-[34px] self-start">
        {open ? 'Hide full guide' : 'Read the full guide'}
      </button>
      {open && <div className="border-t border-line pt-4"><ManualSectionBody section={section} /></div>}
    </section>
  )
}

export default function Manual() {
  const [open, setOpen] = useState(() => new Set())
  const [contact, setContact] = useState(null)
  const [scrollTo, setScrollTo] = useState(null)

  useEffect(() => {
    fetch(apiUrl('/api/public/legal')).then((r) => (r.ok ? r.json() : null))
      .then((f) => f?.contact_email && setContact(f.contact_email)).catch(() => {})
  }, [])

  // Arriving from a "How this works" pill (/manual#roles): open that card.
  useEffect(() => {
    const id = window.location.hash.slice(1)
    if (!id || !MANUAL.some((m) => m.id === id)) return
    setOpen(new Set([id]))
    setScrollTo(id)
  }, [])

  // Runs after the opened card has rendered. Instant, and re-applied once:
  // the page's entrance animation and late font loading both shift layout,
  // and the browser's own scroll restoration can land after the first jump.
  useEffect(() => {
    if (!scrollTo) return
    const go = () => document.getElementById(scrollTo)?.scrollIntoView({ block: 'start' })
    go()
    const t = setTimeout(go, 450)
    return () => clearTimeout(t)
  }, [scrollTo])

  const toggle = (id) => setOpen((prev) => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  return (
    <PageFrame wide>
      <PageHeader title="Help centre" help={false}
        subtitle={'What each screen does, and the terms it uses. Every "How this works" pill links here.'}
        actions={contact
          ? <a href={`mailto:${contact}`} className="btn-primary no-underline">Email support</a>
          : <a href="/privacy" className="btn-ghost h-[42px] no-underline">Privacy &amp; contact</a>} />

      <nav aria-label="Screens" className="flex flex-wrap gap-2">
        {MANUAL.map((m, i) => (
          <a key={m.id} href={`#${m.id}`}
            onClick={(e) => {
              e.preventDefault()
              setOpen((prev) => new Set(prev).add(m.id))
              document.getElementById(m.id)?.scrollIntoView({ behavior: 'smooth' })
            }}
            className="inline-flex h-9 items-center gap-2 rounded-full border border-line-strong bg-surface px-3.5 text-sm font-medium text-ink no-underline transition-colors hover:border-accent hover:text-ink">
            <span className="font-mono text-[12px] font-medium text-accent-soft">{String(i + 1).padStart(2, '0')}</span>
            {m.title}
          </a>
        ))}
      </nav>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        {MANUAL.map((m, i) => (
          <HelpCard key={m.id} section={m} n={String(i + 1).padStart(2, '0')}
            open={open.has(m.id)} onToggle={() => toggle(m.id)} />
        ))}
      </div>

      <div className="flex flex-wrap justify-between gap-3 border-t border-line pt-6 font-mono text-[12px] uppercase tracking-[0.08em] text-ink-subtle">
        <span>Recruit AI — help centre</span>
        <span>Nothing sends without your click</span>
      </div>
    </PageFrame>
  )
}
