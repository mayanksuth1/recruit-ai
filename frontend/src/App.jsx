import { useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { supabase, supabaseConfigured } from './lib/supabase'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Roles from './pages/Roles'
import RoleDetail from './pages/RoleDetail'
import TalentPool from './pages/TalentPool'
import Outbox from './pages/Outbox'
import Interviews from './pages/Interviews'
import Settings from './pages/Settings'
import Schedule from './pages/Schedule'
import Reports from './pages/Reports'
import AiInterviews from './pages/AiInterviews'
import AiInterviewDetail from './pages/AiInterviewDetail'
import AiInterview from './pages/AiInterview'
import Search from './pages/Search'
import Manual from './pages/Manual'
import Dashboard from './pages/Dashboard'

function ConfigBanner() {
  return (
    <div className="bg-amber-50 border-b border-amber-300 px-6 py-2 text-sm text-amber-900">
      <strong>Preview mode:</strong> set <code>VITE_SUPABASE_ANON_KEY</code> in{' '}
      <code>frontend/.env</code> (publishable/anon key from the Supabase dashboard) to
      enable sign-in.
    </div>
  )
}

export default function App() {
  const [session, setSession] = useState(undefined) // undefined = loading
  const navigate = useNavigate()

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session)).catch(() => setSession(null))
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  if (session === undefined) return null

  const signOut = async () => {
    await supabase.auth.signOut()
    navigate('/login')
  }

  return (
    <div className="min-h-screen">
      {!supabaseConfigured && <ConfigBanner />}
      {session && (
        <header className="bg-white/70 backdrop-blur-md shadow-[0_10px_30px_-24px_rgba(92,80,73,0.7)] px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <span className="flex items-center gap-2 font-extrabold text-cocoa">
              <span className="flex gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-peach" />
                <span className="w-2.5 h-2.5 rounded-full bg-lavender" />
                <span className="w-2.5 h-2.5 rounded-full bg-mint" />
              </span>
              Recruit AI
            </span>
            <nav className="flex gap-4 text-sm">
              <Link to="/dashboard" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Dashboard</Link>
              <Link to="/" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Roles</Link>
              <Link to="/talent-pool" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Talent Pool</Link>
              <Link to="/outbox" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Outbox</Link>
              <Link to="/interviews" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Interviews</Link>
              <Link to="/ai-interviews" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">AI Interviews</Link>
              <Link to="/search" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Search</Link>
              <Link to="/reports" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Reports</Link>
              <Link to="/settings" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Settings</Link>
            </nav>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <Link to="/manual" className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">Manual</Link>
            <span className="text-cocoa/60">{session.user.email}</span>
            <button onClick={signOut} className="px-3 py-1.5 rounded-full font-semibold text-cocoa/70 hover:text-cocoa hover:bg-blush/50 transition-colors">
              Sign out
            </button>
          </div>
        </header>
      )}
      <Routes>
        <Route path="/login" element={session ? <Navigate to="/" /> : <Login />} />
        <Route path="/signup" element={session ? <Navigate to="/" /> : <Signup />} />
        <Route path="/" element={session ? <Roles /> : <Navigate to="/login" />} />
        <Route path="/roles/:roleId" element={session ? <RoleDetail /> : <Navigate to="/login" />} />
        <Route path="/talent-pool" element={session ? <TalentPool /> : <Navigate to="/login" />} />
        <Route path="/outbox" element={session ? <Outbox /> : <Navigate to="/login" />} />
        <Route path="/interviews" element={session ? <Interviews /> : <Navigate to="/login" />} />
        <Route path="/ai-interviews" element={session ? <AiInterviews /> : <Navigate to="/login" />} />
        <Route path="/ai-interviews/:sessionId" element={session ? <AiInterviewDetail /> : <Navigate to="/login" />} />
        <Route path="/search" element={session ? <Search /> : <Navigate to="/login" />} />
        <Route path="/settings" element={session ? <Settings /> : <Navigate to="/login" />} />
        <Route path="/reports" element={session ? <Reports /> : <Navigate to="/login" />} />
        <Route path="/dashboard" element={session ? <Dashboard /> : <Navigate to="/login" />} />
        <Route path="/manual" element={session ? <Manual /> : <Navigate to="/login" />} />
        {/* Public candidate-facing pages — no login required. The token in the
            URL is the entire authentication, so these must never sit behind the
            session check above. */}
        <Route path="/schedule/:token" element={<Schedule />} />
        <Route path="/ai-interview/:token" element={<AiInterview />} />
      </Routes>
    </div>
  )
}
