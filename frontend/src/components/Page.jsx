import { Link } from 'react-router-dom'

// Shared page furniture from the design file: the page frame, the header
// (Doto title, "How this works" pill, subtitle, action) and the "[ 0 ]"
// empty state on a dot grid.

export function PageFrame({ children, wide = false }) {
  return (
    <div className={`mx-auto flex w-full flex-col gap-7 px-5 pb-14 pt-9 md:px-10 ${wide ? 'max-w-[1400px]' : 'max-w-[1184px]'}`}>
      {children}
    </div>
  )
}

export function HowItWorks({ section }) {
  return (
    <Link to={section ? `/manual#${section}` : '/manual'}
      className="inline-flex h-[30px] items-center gap-2 rounded-full border border-line-strong py-0 pl-[5px] pr-3 text-[13px] font-medium text-ink-2 no-underline transition-colors hover:border-accent hover:text-ink">
      <span className="grid h-5 w-5 place-items-center rounded-full bg-line font-mono text-[12px] font-semibold text-ink">?</span>
      How this works
    </Link>
  )
}

export function PageHeader({ title, subtitle, section, actions, help = true }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-6 border-b border-line pb-6">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-4">
          <h1>{title}</h1>
          {help && <HowItWorks section={section} />}
        </div>
        {subtitle && <p className="m-0 text-base leading-normal text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  )
}

export function Label({ n, children, right }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="panel-label">{n != null && <b>{String(n).padStart(2, '0')}</b>}{children}</div>
      {right && <div className="font-mono text-[13px] font-medium text-ink-muted">{right}</div>}
    </div>
  )
}

export function Section({ n, label, right, children, className = '' }) {
  return (
    <section className={`card flex flex-col gap-5 px-6 py-[22px] ${className}`}>
      {label && <Label n={n} right={right}>{label}</Label>}
      {children}
    </section>
  )
}

export function EmptyState({ title, children, actions, count = '0', className = '' }) {
  return (
    <div className={`dot-grid flex flex-col items-start justify-center gap-3.5 rounded-[12px] border border-dashed border-line-strong p-10 ${className}`}>
      <div className="dot-num text-[48px] text-accent">[ {count} ]</div>
      <div className="text-xl font-semibold text-ink">{title}</div>
      {children && <div className="max-w-[56ch] text-[15px] leading-relaxed text-ink-muted">{children}</div>}
      {actions && <div className="flex flex-wrap gap-2.5">{actions}</div>}
    </div>
  )
}

/* Dotted bar: grey dotted track, red dotted fill that grows in. */
export function DotBar({ pct, height = 14 }) {
  return (
    <div className="dot-track" style={{ height }}>
      <div className="dot-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  )
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/* "30 Sep 2026" — the design's date format (en-GB would give "Sept"). */
export function fmtDate(iso, { year = true } = {}) {
  const d = new Date(iso)
  return `${String(d.getDate()).padStart(2, '0')} ${MONTHS[d.getMonth()]}${year ? ` ${d.getFullYear()}` : ''}`
}
