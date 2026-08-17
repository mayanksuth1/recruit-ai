import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MANUAL, TONES, getManualSection } from '../lib/manual'

// Minimal inline formatter: **bold** only. A full markdown dependency would be
// four orders of magnitude larger than the one feature the manual copy uses.
export function renderInline(text) {
  return String(text)
    .split(/(\*\*[^*]+\*\*)/g)
    .filter(Boolean)
    .map((chunk, i) =>
      chunk.startsWith('**') && chunk.endsWith('**') ? (
        <b key={i} className="font-bold text-cocoa">{chunk.slice(2, -2)}</b>
      ) : (
        <span key={i}>{chunk}</span>
      ),
    )
}

const pillClass = (tone) =>
  `rounded-full px-3.5 py-1.5 text-xs font-bold ${(TONES[tone] || TONES.outline).pill}`

function Block({ block }) {
  switch (block.k) {
    case 'p':
      return <p className="text-sm text-cocoa/70">{renderInline(block.t)}</p>

    case 'pills':
      return (
        <div className="flex flex-wrap gap-2">
          {block.items.map((p) => (
            <span key={p.label} className={pillClass(p.tone)}>{p.label}</span>
          ))}
        </div>
      )

    case 'pillnote':
      return (
        <p className="flex flex-wrap items-center gap-2 text-sm text-cocoa/70">
          {renderInline(block.t)}
          {block.items.map((p) => (
            <span key={p.label} className={pillClass(p.tone)}>{p.label}</span>
          ))}
        </p>
      )

    case 'scores':
      return (
        <div className="flex flex-wrap gap-2">
          {block.items.map((s) => (
            <span key={s.label} className="rounded-full bg-cream px-3 py-1.5 text-xs font-bold text-cocoa/70">
              {s.label} <b className="text-teal-900">{s.value}</b>
            </span>
          ))}
        </div>
      )

    case 'kv':
      return (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5">
          {block.rows.map(([dt, dd]) => (
            <div key={dt} className="contents">
              <dt className="whitespace-nowrap pt-0.5 text-xs font-bold text-cocoa">{dt}</dt>
              <dd className="text-sm text-cocoa/70">{dd}</dd>
            </div>
          ))}
        </dl>
      )

    case 'steps':
      return (
        <ol className="mt-1">
          {block.items.map((s, i) => (
            <li
              key={s.idx}
              className={`flex items-start gap-3.5 py-3 text-sm text-cocoa/70 ${
                i === 0 ? '' : 'border-t border-cocoa/10'
              }`}
            >
              <span className="flex h-6 min-w-6 flex-none items-center justify-center rounded-full bg-mint px-1.5 text-[11px] font-extrabold text-teal-900">
                {s.idx}
              </span>
              <span>{renderInline(s.t)}</span>
            </li>
          ))}
        </ol>
      )

    case 'table':
      return (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {block.head.map((h) => (
                  <th
                    key={h}
                    className="border-b-2 border-blush px-3 py-2 text-left text-[11px] font-extrabold uppercase tracking-wide text-cocoa/50"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((r) => (
                <tr key={r[0]}>
                  {r.map((cell, i) => (
                    <td key={i} className="border-b border-cocoa/10 px-3 py-2.5 text-cocoa/70">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )

    // Notes appear both as top-level body items and nested inside a card.
    case 'note':
      return <Note note={block} />

    default:
      return null
  }
}

function Note({ note }) {
  const bg = note.tone === 'butter' ? 'bg-butter' : 'bg-blush'
  return (
    <div className={`rounded-2xl px-5 py-4 text-sm text-cocoa ${bg}`}>
      {note.title && <strong className="font-extrabold">{note.title} </strong>}
      {renderInline(note.t)}
    </div>
  )
}

/** Renders one manual section's body. Shared by the drawer and the /manual page. */
export function ManualSectionBody({ section }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-cocoa/70">{section.lede}</p>
      {section.body.map((item, i) =>
        item.k === 'note' ? (
          <Note key={i} note={item} />
        ) : (
          <div key={i} className="card space-y-3 p-5">
            <h3 className="text-sm font-bold text-cocoa">{item.h3}</h3>
            {item.blocks.map((b, j) => <Block key={j} block={b} />)}
          </div>
        ),
      )}
    </div>
  )
}

/**
 * The same section, rendered inline at the foot of the page it documents.
 *
 * Collapsed by default: these pages already scroll, and the manual is reference
 * material rather than something you re-read every visit. The drawer at the top
 * of the page covers the quick-glance case; this covers reading in place.
 * Both render from the same data, so they cannot drift apart.
 */
export function ManualSection({ section }) {
  const [open, setOpen] = useState(false)
  const data = getManualSection(section)
  if (!data) return null

  const tone = TONES[data.tone] || TONES.outline
  const panelId = `manual-panel-${data.id}`

  return (
    <section className="mt-10 border-t border-cocoa/10 pt-6">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center gap-3 rounded-2xl bg-white/60 px-4 py-3 text-left transition-colors hover:bg-white"
      >
        <span className={`flex h-8 w-8 flex-none items-center justify-center rounded-lg text-xs font-extrabold ${tone.badge}`}>
          {data.num}
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-bold text-cocoa">Manual — {data.title}</span>
          <span className="block truncate text-xs text-cocoa/50">{data.tag}</span>
        </span>
        <span className="ml-auto flex flex-none items-center gap-2 text-xs font-bold text-cocoa/50">
          {open ? 'Hide' : 'Read'}
          <svg
            viewBox="0 0 20 20"
            aria-hidden="true"
            className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`}
          >
            <path
              d="M5 8l5 5 5-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </button>

      {open && (
        <div id={panelId} className="pt-5">
          <ManualSectionBody section={data} />
          <Link
            to="/manual"
            className="mt-4 inline-block text-xs font-bold text-cocoa/50 transition-colors hover:text-cocoa"
          >
            Read the full manual — all {MANUAL.length} sections →
          </Link>
        </div>
      )}
    </section>
  )
}

/**
 * Per-page contextual help. Drop `<ManualHelp section="roles" />` beside a page
 * heading; it renders a button that opens that section of the manual in a
 * slide-over, without navigating away from the work in progress.
 */
export default function ManualHelp({ section }) {
  const [open, setOpen] = useState(false)
  const data = getManualSection(section)

  // Escape closes; body scroll is locked while the drawer owns the viewport.
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open])

  if (!data) return null
  const tone = TONES[data.tone] || TONES.outline

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`How ${data.title} works`}
        className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-bold text-cocoa/70 shadow-[0_1px_3px_rgba(92,80,73,0.12)] transition-transform hover:scale-[1.04] hover:text-cocoa active:scale-95"
      >
        <span className={`h-2 w-2 rounded-full ${tone.swatch}`} />
        How this works
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="absolute inset-0 bg-cocoa/25 backdrop-blur-[2px]"
            onClick={() => setOpen(false)}
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label={`${data.title} — manual`}
            className="relative flex h-full w-full max-w-xl flex-col bg-cream shadow-[0_0_60px_-10px_rgba(92,80,73,0.5)]"
          >
            <header className="flex items-center gap-3 border-b border-cocoa/10 bg-white/70 px-6 py-4 backdrop-blur-md">
              <span className={`flex h-9 w-9 items-center justify-center rounded-xl text-sm font-extrabold ${tone.badge}`}>
                {data.num}
              </span>
              <div>
                <h2 className="text-lg font-extrabold text-cocoa">{data.title}</h2>
                <p className="text-xs font-bold text-cocoa/50">{data.tag}</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close manual"
                className="ml-auto rounded-full px-3 py-1.5 text-sm font-semibold text-cocoa/60 transition-colors hover:bg-blush/50 hover:text-cocoa"
              >
                Close
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-6 py-5">
              <ManualSectionBody section={data} />
            </div>

            <footer className="border-t border-cocoa/10 bg-white/70 px-6 py-3 backdrop-blur-md">
              <Link
                to="/manual"
                onClick={() => setOpen(false)}
                className="text-xs font-bold text-cocoa/60 transition-colors hover:text-cocoa"
              >
                Read the full manual — all {MANUAL.length} sections →
              </Link>
            </footer>
          </aside>
        </div>
      )}
    </>
  )
}
