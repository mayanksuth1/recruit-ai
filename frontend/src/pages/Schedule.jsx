import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { apiUrl } from '../lib/api'

// Public page — the candidate opens this from the scheduling-link email.
// No login required; the unguessable token in the URL scopes everything.
export default function Schedule() {
  const { token } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmed, setConfirmed] = useState(null)

  const load = async () => {
    try {
      const res = await fetch(apiUrl(`/api/public/schedule/${token}`))
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText)
      setData(await res.json())
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [token])

  const pick = async (slot) => {
    if (!window.confirm(`Confirm interview on ${new Date(slot.start).toLocaleString()}?`)) return
    setBusy(true)
    setError('')
    try {
      const res = await fetch(apiUrl(`/api/public/schedule/${token}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start: slot.start }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText)
      setConfirmed(await res.json())
    } catch (err) { setError(err.message) }
    setBusy(false)
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <p className="text-sm text-red-600">{error}</p>
      </div>
    )
  }
  if (!data) return null

  const done = confirmed || data.status === 'scheduled'
  const when = confirmed?.scheduled_start || data.scheduled_start
  const meet = confirmed?.meet_link || data.meet_link

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-lg card p-8 space-y-5">
        <div>
          <h1 className="text-xl font-extrabold text-cocoa">
            Interview — {data.role_title || 'your application'}
          </h1>
          <p className="text-sm text-cocoa/60">
            {data.org_name} · {data.duration_minutes} minutes · Google Meet
          </p>
        </div>

        {done ? (
          <div className="rounded-md bg-green-50 border border-green-200 p-4 space-y-2">
            <p className="text-sm font-medium text-green-800">
              You're booked for {new Date(when).toLocaleString()}.
            </p>
            <p className="text-sm text-green-700">
              A calendar invite is on its way to your inbox.
              {meet && <> Join link: <a href={meet} className="underline">{meet}</a></>}
            </p>
          </div>
        ) : data.status !== 'proposed' ? (
          <p className="text-sm text-cocoa/60">This scheduling link is no longer active.</p>
        ) : data.slots.length === 0 ? (
          <p className="text-sm text-cocoa/60">
            All proposed times have passed — please reply to the email to get new times.
          </p>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-cocoa/70">Pick a time that works for you:</p>
            {data.slots.map((s) => (
              <button key={s.start} onClick={() => pick(s)} disabled={busy}
                className="w-full text-left rounded-2xl border-2 border-blush px-4 py-3 text-sm hover:border-rosy hover:bg-blush/30 disabled:opacity-50">
                {new Date(s.start).toLocaleString(undefined, {
                  weekday: 'long', day: 'numeric', month: 'short',
                  hour: 'numeric', minute: '2-digit',
                })}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
