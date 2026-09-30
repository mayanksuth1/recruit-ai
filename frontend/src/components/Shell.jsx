import { NavLink } from 'react-router-dom'

// Sidebar + TopBar from the design file (Sidebar.dc.html, TopBar.dc.html):
// numbered mono nav, the active item on #221F1D with an inset ring and a
// glowing red dot, "Signed in as" footer, and a status/date top bar.

const NAV = [
  ['/dashboard', 'Dashboard'],
  ['/', 'Roles'],
  ['/talent-pool', 'Talent Pool'],
  ['/outbox', 'Outbox'],
  ['/interviews', 'Interviews'],
  ['/ai-interviews', 'AI Interviews'],
  ['/search', 'Search'],
  ['/reports', 'Reports'],
]

export function Logo({ size = 27 }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="dot-num text-ink" style={{ fontSize: size, letterSpacing: '.03em' }}>
        RECRUIT<span className="text-accent">·</span>AI
      </div>
      <div className="font-mono text-[12px] font-medium uppercase leading-none tracking-[0.12em] text-ink-muted">Hiring Console</div>
    </div>
  )
}

function Item({ to, label, n, tone }) {
  return (
    <NavLink to={to} end={to === '/'}
      className={({ isActive }) =>
        `flex h-[42px] items-center gap-3 rounded-[10px] px-3 text-[15px] font-medium no-underline transition-colors ${
          isActive
            ? 'bg-[#221F1D] text-ink shadow-[inset_0_0_0_1px_#3A3734] hover:text-ink'
            : `${tone || 'text-ink-2'} hover:bg-[#1C1A19] hover:text-ink`}`}>
      {({ isActive }) => (
        <>
          <span className={`w-[18px] font-mono text-[12px] font-medium ${isActive ? 'text-accent' : 'text-ink-subtle'}`}>{n}</span>
          <span className="flex-1">{label}</span>
          {isActive && <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_8px_#FF4040]" />}
        </>
      )}
    </NavLink>
  )
}

export function TopBar({ onSignOut }) {
  const d = new Date()
  const today = `${d.toLocaleDateString('en-GB', { weekday: 'short' })} ${d.getDate()} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()]} ${d.getFullYear()}`
  return (
    <div className="flex h-[60px] shrink-0 items-center justify-between gap-4 border-b border-line px-5 md:px-10">
      <div role="status" className="inline-flex h-8 items-center gap-2.5 rounded-full border border-line-strong px-3.5 font-mono text-[13px] font-medium text-ink-2">
        <span className="relative flex h-[7px] w-[7px]">
          <span className="absolute inset-0 rounded-full bg-positive" style={{ animation: 'ping-soft 2.4s cubic-bezier(0,0,.2,1) infinite' }} />
          <span className="relative h-[7px] w-[7px] rounded-full bg-positive shadow-[0_0_8px_#7FD9A0]" />
        </span>
        <span className="hidden sm:inline">All systems operational</span>
      </div>
      <div className="flex items-center gap-2">
        <div className="hidden h-8 items-center gap-2.5 rounded-lg border border-line bg-surface px-3.5 font-mono text-[13px] font-medium uppercase tracking-[0.06em] text-ink-2 sm:inline-flex">
          <span className="text-ink-subtle">Today</span>{today}
        </div>
        <button onClick={onSignOut} className="btn-ghost h-8 md:hidden">Sign out</button>
      </div>
    </div>
  )
}

export default function Shell({ email, isAdmin, onSignOut, children }) {
  return (
    <div className="grid min-h-screen md:grid-cols-[256px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-line bg-sidebar px-4 pb-[22px] pt-[26px] md:flex">
        <div className="px-3 pb-[30px]"><Logo /></div>
        <nav aria-label="Primary" className="flex flex-col gap-0.5">
          {NAV.map(([to, label], i) => <Item key={to} to={to} label={label} n={String(i + 1).padStart(2, '0')} />)}
        </nav>
        <div className="min-h-8 flex-1" />
        <nav aria-label="Secondary" className="flex flex-col gap-0.5 pb-4">
          {isAdmin && <Item to="/admin" label="Admin" n="◆" tone="text-accent-soft" />}
          <Item to="/settings" label="Settings" n="⚙" />
          <Item to="/manual" label="Help centre" n="?" />
        </nav>
        <div className="flex flex-col gap-2.5 border-t border-line px-3 pt-4">
          <div className="font-mono text-[12px] uppercase tracking-[0.08em] text-ink-subtle">Signed in as</div>
          <div className="truncate text-sm font-medium text-ink" title={email}>{email}</div>
          <button type="button" onClick={onSignOut}
            className="h-[34px] self-start rounded-lg border border-line-strong bg-transparent px-3 text-sm font-medium text-ink-2 transition-colors hover:border-accent hover:text-ink">
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col" style={{ background: 'radial-gradient(900px 420px at 100% 0%,rgba(255,64,64,.07),transparent 70%)' }}>
        <TopBar onSignOut={onSignOut} />
        {/* Mobile: the sidebar becomes a scrolling tab strip. */}
        <nav className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 md:hidden">
          {[...NAV, ['/settings', 'Settings'], ['/manual', 'Help'], ...(isAdmin ? [['/admin', 'Admin']] : [])].map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'}
              className={({ isActive }) => `whitespace-nowrap rounded-lg px-3 py-1.5 text-xs no-underline ${isActive ? 'bg-[#221F1D] text-ink shadow-[inset_0_0_0_1px_#3A3734]' : 'text-ink-2'}`}>
              {label}
            </NavLink>
          ))}
        </nav>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  )
}
