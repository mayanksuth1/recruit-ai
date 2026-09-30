import { Link } from 'react-router-dom'
import { Logo } from './Shell'
import { DotBars, Elbow, Pulse } from './fx'

function Step({ n, title, children, className = '', i }) {
  return (
    <div className={`card p-5 animate-rise ${className}`} style={{ animationDelay: `${i * 160}ms` }}>
      <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-[#FF6B6B]">Step {n}</div>
      <div className="mt-2 text-xl font-medium tracking-tight text-cocoa">{title}</div>
      {children}
    </div>
  )
}

/* Sign-in / sign-up frame: the product story on the left, the form on the right. */
export default function AuthLayout({ children }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden overflow-hidden border-r border-line p-10 lg:flex lg:flex-col">
        <Logo />
        <div className="mt-10">
          <h1 className="dot-num text-5xl leading-tight text-cocoa">HIRE WITH<br />INTELLIGENCE</h1>
          <p className="mt-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-cocoa/55">
            <Pulse color="#7FD9A0" /> AI does the grunt work. You make the call.
          </p>
        </div>

        <div className="mt-10 w-full max-w-lg">
          <Step n={1} title="Drop in resumes" i={0} className="w-[78%]">
            <div className="mt-4 flex items-center gap-3 rounded-[10px] border border-line bg-white/[0.02] px-3 py-2 text-sm text-cocoa/60">
              <span className="font-mono text-[11px] text-[#FF6B6B]">PDF</span> 40 resumes · Data Analyst
            </div>
          </Step>
          <div className="w-[70%] pl-[6%]"><Elbow /></div>
          <Step n={2} title="AI scores every one against the JD" i={1} className="ml-[18%] w-[82%]">
            <div className="mt-4 space-y-2">
              {[['Priya S.', 92, true], ['Arjun M.', 81], ['Divya N.', 64]].map(([name, s, top]) => (
                <div key={name} className={`flex items-center justify-between rounded-[10px] border px-3 py-2 text-sm ${top ? 'border-[#FF4040]/70 text-cocoa glow' : 'border-line text-cocoa/60'}`}>
                  <span className="flex items-center gap-2">
                    <span className={`h-3 w-3 rounded-full border ${top ? 'border-[#FF4040] bg-[#FF4040] shadow-[0_0_8px_#FF4040]' : 'border-cocoa/30'}`} />{name}
                  </span>
                  <span className="dot-num text-base">{s}</span>
                </div>
              ))}
            </div>
          </Step>
          <div className="ml-[30%] w-[70%]"><Elbow flip /></div>
          <Step n={3} title="You approve. Then it sends." i={2} className="w-[86%]">
            <div className="mt-4 flex items-end justify-between gap-4">
              <p className="max-w-[14rem] text-sm text-cocoa/55">Nothing reaches a candidate without your click — two approval gates, every time.</p>
              <div className="w-28"><DotBars values={[2, 3, 2, 4, 5, 4, 7, 8, 9]} rows={7} height={58} /></div>
            </div>
          </Step>
        </div>

        <div className="mt-auto pt-10 font-mono text-[11px] uppercase tracking-[0.2em] text-cocoa/35">
          Build your shortlist<span className="animate-blink text-[#FF4040]"> _</span>
        </div>
      </section>

      <section className="flex min-h-screen flex-col items-center justify-center p-6">
        <div className="mb-8 lg:hidden"><Logo /></div>
        <div className="w-full max-w-sm animate-rise">{children}</div>
        <p className="mt-8 font-mono text-[10px] uppercase tracking-[0.16em] text-cocoa/35">
          <Link to="/privacy" className="hover:text-cocoa/70">Privacy</Link> · Public beta
        </p>
      </section>
    </div>
  )
}
