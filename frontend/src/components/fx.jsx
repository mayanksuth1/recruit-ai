// Visual building blocks for the dark "instrument panel" UI: dot-matrix
// numbers, dotted gauges, dot bar charts, a dotted sparkline, a waveform and
// glowing connectors. All SVG/CSS — no chart library — and every animation
// is switched off by the prefers-reduced-motion rule in index.css.
import { useEffect, useRef, useState } from 'react'

const EMBER = '#FF4040'
const DIM = 'rgba(242,238,233,0.16)'
const LIGHT = 'rgba(242,238,233,0.85)'

/* Count up to `value` once, the first time it is shown. */
export function useCountUp(value, ms = 900) {
  const [shown, setShown] = useState(0)
  const target = Number(value) || 0
  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) { setShown(target); return }
    let raf
    const start = performance.now()
    const tick = (t) => {
      const p = Math.min(1, (t - start) / ms)
      setShown(Math.round(target * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return shown
}

export function compact(n) {
  const v = Number(n) || 0
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 10_000) return `${(v / 1000).toFixed(1)}K`
  return v.toLocaleString()
}

export function DotNumber({ value, className = '', suffix = '' }) {
  const n = useCountUp(value)
  return <span className={`dot-num ${className}`}>{compact(n)}{suffix}</span>
}

/* A numbered, labelled panel: "01  OPEN ROLES". */
export function Panel({ n, label, right, children, className = '', i = 0, as: As = 'div', ...rest }) {
  return (
    <As className={`card p-5 animate-rise ${className}`} style={{ animationDelay: `${i * 70}ms` }} {...rest}>
      {(label || right) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="panel-label">{n != null && <b>{String(n).padStart(2, '0')}</b>}{label}</div>
          {right}
        </div>
      )}
      {children}
    </As>
  )
}

/* Pulsing status dot. */
export function Pulse({ color = EMBER, className = '' }) {
  return (
    <span className={`relative inline-flex h-2 w-2 ${className}`}>
      <span className="absolute inset-0 rounded-full" style={{ background: color, animation: 'ping-soft 1.8s cubic-bezier(0,0,.2,1) infinite' }} />
      <span className="relative h-2 w-2 rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
    </span>
  )
}

/* Circular gauge made of dots; `pct` of them light up, in sequence. */
export function DotRing({ pct = 0, size = 150, dots = 60, label, sub, warn = 0.8 }) {
  const r = size / 2 - 8
  const lit = Math.round(Math.max(0, Math.min(1, pct)) * dots)
  const hot = pct >= warn
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="absolute inset-0">
        {Array.from({ length: dots }, (_, k) => {
          const a = (k / dots) * Math.PI * 2 - Math.PI / 2
          const on = k < lit
          return (
            <circle key={k} cx={size / 2 + r * Math.cos(a)} cy={size / 2 + r * Math.sin(a)}
              r={on ? 2.3 : 1.6} fill={on ? (hot && k > lit - 8 ? EMBER : LIGHT) : DIM}
              style={on ? { animation: `dot-on .4s ${k * 18}ms both` } : undefined} />
          )
        })}
      </svg>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="absolute inset-0"
        style={{ animation: 'spin-slow 24s linear infinite' }}>
        <circle cx={size / 2} cy={size / 2} r={r - 14} fill="none" stroke="rgba(255,255,255,0.06)"
          strokeDasharray="1 5" strokeLinecap="round" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="dot-num text-3xl text-cocoa">{label}</div>
        {sub && <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cocoa/50">{sub}</div>}
      </div>
    </div>
  )
}

/* Dot-matrix bar chart: each bar is a column of dots. Last bar is ember. */
export function DotBars({ values = [], rows = 9, height = 96, accentLast = 3 }) {
  const max = Math.max(1, ...values)
  return (
    <div className="flex items-end gap-[5px]" style={{ height }}>
      {values.map((v, i) => {
        const filled = Math.max(v > 0 ? 1 : 0, Math.round((v / max) * rows))
        const hot = i >= values.length - accentLast
        return (
          <div key={i} className="flex flex-1 flex-col-reverse gap-[3px] origin-bottom"
            style={{ animation: `bar-up .7s ${i * 35}ms cubic-bezier(.2,.7,.2,1) both` }} title={`${v}`}>
            {Array.from({ length: rows }, (_, k) => (
              <span key={k} className="mx-auto h-[5px] w-[5px] rounded-full"
                style={{ background: k < filled ? (hot ? EMBER : LIGHT) : 'rgba(255,255,255,0.05)',
                         boxShadow: k < filled && hot ? `0 0 6px ${EMBER}` : 'none' }} />
            ))}
          </div>
        )
      })}
    </div>
  )
}

/* Dotted sparkline with the peak ringed in ember. */
export function DotSpark({ values = [], width = 320, height = 90 }) {
  if (!values.length) return null
  const max = Math.max(1, ...values)
  const step = values.length > 1 ? width / (values.length - 1) : width
  const pts = values.map((v, i) => [i * step, height - 8 - (v / max) * (height - 20)])
  const peak = values.indexOf(Math.max(...values))
  const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }} preserveAspectRatio="none">
      <path d={d} fill="none" stroke={LIGHT} strokeWidth="2" strokeDasharray="0.1 7" strokeLinecap="round"
        style={{ animation: 'flow 1.6s linear infinite' }} />
      {max > 0 && pts[peak] && (
        <g>
          <circle cx={pts[peak][0]} cy={pts[peak][1]} r="7" fill="none" stroke={EMBER} strokeWidth="1.5" />
          <circle cx={pts[peak][0]} cy={pts[peak][1]} r="3" fill={EMBER} style={{ filter: `drop-shadow(0 0 4px ${EMBER})` }} />
        </g>
      )}
    </svg>
  )
}

/* The "thinking" waveform: dotted line with an animated burst in the middle. */
export function Waveform({ bars = 34, active = true }) {
  return (
    <div className="flex h-10 items-center gap-[3px]">
      {Array.from({ length: bars }, (_, i) => {
        const mid = Math.abs(i - bars / 2) < bars / 6
        return (
          <span key={i} className="w-[3px] origin-center rounded-full"
            style={{
              height: mid ? 28 : 6 + ((i * 7) % 11),
              background: mid ? EMBER : 'rgba(237,231,225,0.35)',
              boxShadow: mid ? `0 0 6px ${EMBER}` : 'none',
              animation: active ? `wave ${0.9 + (i % 5) * 0.13}s ${i * 40}ms ease-in-out infinite` : 'none',
            }} />
        )
      })}
    </div>
  )
}

/* Horizontal pipeline: stage nodes joined by a glowing ember line.
   stages = [{ key, label, count }]. Nodes with count > 0 glow. */
export function Pipeline({ stages = [] }) {
  const ref = useRef(null)
  return (
    <div ref={ref} className="relative">
      <div className="absolute left-[8%] right-[8%] top-[22px] h-[2px] rounded-full"
        style={{ background: `linear-gradient(90deg, ${EMBER}, rgba(255,107,107,0.35))`, boxShadow: `0 0 12px ${EMBER}` }} />
      <svg className="absolute left-[8%] right-[8%] top-[17px] h-3 w-[84%]" preserveAspectRatio="none" viewBox="0 0 100 10">
        <line x1="0" y1="5" x2="100" y2="5" stroke="#ffb3b3" strokeWidth="1.2" strokeDasharray="1 11"
          style={{ animation: 'flow 1.2s linear infinite' }} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="relative grid" style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}>
        {stages.map((s, i) => {
          const on = s.count > 0
          return (
            <div key={s.key} className="flex flex-col items-center gap-2 animate-rise" style={{ animationDelay: `${i * 90}ms` }}>
              <span className="flex h-11 w-11 items-center justify-center rounded-full border-2 bg-ink"
                style={{ borderColor: on ? EMBER : 'rgba(255,255,255,0.14)', boxShadow: on ? `0 0 16px rgba(255,64,64,.55)` : 'none' }}>
                <span className="dot-num text-lg" style={{ color: on ? '#ffb3b3' : 'rgba(237,231,225,.4)' }}>{s.count}</span>
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-cocoa/60">{s.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* Vertical elbow connector used between stacked steps (auth screens). */
export function Elbow({ flip = false, height = 56 }) {
  const path = flip ? 'M 90 0 V 20 Q 90 28 82 28 H 18 Q 10 28 10 36 V 56' : 'M 10 0 V 20 Q 10 28 18 28 H 82 Q 90 28 90 36 V 56'
  return (
    <svg viewBox="0 0 100 56" preserveAspectRatio="none" className="w-full" style={{ height }}>
      <path d={path} fill="none" stroke={EMBER} strokeWidth="2" vectorEffect="non-scaling-stroke"
        style={{ filter: `drop-shadow(0 0 5px ${EMBER})` }} />
      <path d={path} fill="none" stroke="#ffb3b3" strokeWidth="1.2" strokeDasharray="1 10" vectorEffect="non-scaling-stroke"
        style={{ animation: 'flow 1.1s linear infinite' }} />
      <circle cx={flip ? 90 : 10} cy="2" r="3.5" fill={EMBER} />
      <circle cx={flip ? 10 : 90} cy="54" r="3.5" fill={EMBER} />
    </svg>
  )
}

/* A dot-matrix face for the "agent" panel. */
export function DotFace({ size = 88 }) {
  const r = size / 2 - 4
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {Array.from({ length: 28 }, (_, k) => {
        const a = (k / 28) * Math.PI * 2
        return <circle key={k} cx={size / 2 + r * Math.cos(a)} cy={size / 2 + r * Math.sin(a)} r="1.6" fill={LIGHT} />
      })}
      <circle cx={size / 2 - 11} cy={size / 2 - 4} r="3" fill={EMBER} style={{ animation: 'blink 3.4s steps(1) infinite' }} />
      <circle cx={size / 2 + 11} cy={size / 2 - 4} r="3" fill={EMBER} style={{ animation: 'blink 3.4s steps(1) infinite' }} />
      {[-8, -4, 0, 4, 8].map((dx) => <circle key={dx} cx={size / 2 + dx} cy={size / 2 + 12 + Math.abs(dx) * -0.2} r="1.3" fill={DIM} />)}
    </svg>
  )
}
