import { useEffect, useState } from 'react'
import { MANUAL, TONES } from '../lib/manual'
import { ManualSectionBody } from '../components/ManualHelp'

/**
 * The whole manual on one page, with a sticky section index.
 *
 * The per-page drawers (ManualHelp) cover "what does this screen do" in place;
 * this is for reading end to end. Both render from the same data in lib/manual.js.
 */
export default function Manual() {
  const [active, setActive] = useState(MANUAL[0].id)

  // Highlight the index chip for whichever section is currently in view.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
        if (visible) setActive(visible.target.id)
      },
      { rootMargin: '-96px 0px -60% 0px', threshold: 0 },
    )
    MANUAL.forEach((m) => {
      const el = document.getElementById(m.id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [])

  return (
    <div className="mx-auto max-w-3xl px-8 pb-20">
      <header className="pt-10 pb-6">
        <span className="mb-5 inline-flex items-center gap-2 rounded-full bg-white px-3.5 py-1.5 text-[11px] font-bold uppercase tracking-wider text-cocoa/70 shadow-[0_1px_2px_rgba(92,80,73,0.08)]">
          <span className="h-2 w-2 rounded-full border-2 border-teal-900 bg-mint" />
          Recruit AI · User manual
        </span>
        <h1 className="text-3xl font-extrabold tracking-tight text-cocoa">
          What each screen does
        </h1>
        <p className="mt-4 max-w-[56ch] text-[15px] text-cocoa/70">
          A hiring pipeline that sources, scores, drafts outreach, schedules interviews, and
          reports — with every email, event, and send held for your click before it goes anywhere.
        </p>
        <div className="mt-6 inline-flex rounded-2xl bg-white px-4 py-3 shadow-[0_1px_3px_rgba(92,80,73,0.08)]">
          <div>
            <span className="block text-[10px] font-bold uppercase tracking-wider text-cocoa/50">
              Core principle
            </span>
            <b className="text-[13px] font-bold text-cocoa">nothing auto-sends</b>
          </div>
        </div>
      </header>

      <nav className="sticky top-0 z-10 -mx-8 mb-2 border-b border-cocoa/10 bg-cream/90 px-8 py-3 backdrop-blur-md">
        <div className="flex gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {MANUAL.map((m) => {
            const tone = TONES[m.tone] || TONES.outline
            return (
              <a
                key={m.id}
                href={`#${m.id}`}
                className={`flex flex-none items-center gap-1.5 rounded-full px-3.5 py-2 text-xs font-bold shadow-[0_1px_2px_rgba(92,80,73,0.06)] transition-colors ${
                  active === m.id ? 'bg-white text-cocoa' : 'bg-white/60 text-cocoa/60 hover:text-cocoa'
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${tone.swatch}`} />
                {m.title}
              </a>
            )
          })}
        </div>
      </nav>

      <main>
        {MANUAL.map((m) => {
          const tone = TONES[m.tone] || TONES.outline
          return (
            <section key={m.id} id={m.id} className="scroll-mt-24 pt-10 pb-4">
              <div className="mb-4 flex flex-wrap items-center gap-3.5">
                <span className={`flex h-9 w-9 items-center justify-center rounded-xl text-sm font-extrabold ${tone.badge}`}>
                  {m.num}
                </span>
                <h2 className="text-xl font-extrabold tracking-tight text-cocoa">{m.title}</h2>
                <span className="ml-auto rounded-full bg-white px-3 py-1.5 text-[11px] font-bold text-cocoa/70">
                  {m.tag}
                </span>
              </div>
              <ManualSectionBody section={m} />
            </section>
          )
        })}
      </main>

      <footer className="mt-10 flex flex-wrap justify-between gap-3 border-t border-cocoa/10 pt-8 text-[11px] font-bold text-cocoa/50">
        <span>Recruit AI — user manual</span>
        <span>Nothing sends without your click</span>
      </footer>
    </div>
  )
}
