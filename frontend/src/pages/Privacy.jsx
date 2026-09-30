import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiUrl } from '../lib/api'

// Plain-language privacy notice (India, Digital Personal Data Protection Act
// 2023). Retention period and contact come from the running server so the
// page cannot drift from what the backend actually does.
const UPDATED = '30 September 2026'

function H({ children }) {
  return <h2 className="text-lg font-bold text-cocoa pt-4">{children}</h2>
}

export default function Privacy() {
  const [facts, setFacts] = useState({ activity_retention_days: 365, contact_email: null, free_ai_calls_per_month: 100 })

  useEffect(() => {
    fetch(apiUrl('/api/public/legal')).then((r) => (r.ok ? r.json() : null)).then((f) => f && setFacts(f)).catch(() => {})
  }, [])

  const contact = facts.contact_email
    ? <a className="underline" href={`mailto:${facts.contact_email}`}>{facts.contact_email}</a>
    : <>a direct message to <strong>@tryrecruitai</strong> on X, Instagram or LinkedIn</>

  return (
    <div className="max-w-3xl mx-auto p-8 space-y-3 text-sm text-cocoa/80 leading-relaxed">
      <h1 className="text-2xl font-extrabold text-cocoa">Privacy notice</h1>
      <p className="text-cocoa/60">Last updated {UPDATED}. Recruit AI is in public beta.</p>

      <p>
        This notice explains what personal data Recruit AI collects, why, how long it is kept and
        what you can do about it. It is written for the recruiters and hiring teams who use the
        product, and for the candidates whose details they manage in it.
      </p>

      <H>1. Two kinds of data</H>
      <p>
        <strong>Your account data</strong> — for this, Recruit AI is the data fiduciary (the one
        responsible under the DPDP Act).
      </p>
      <p>
        <strong>Your workspace content</strong> — roles, candidates, resumes, emails, interview
        notes and transcripts you put into Recruit AI. Your organisation decides what goes in and
        why, so your organisation is the data fiduciary for it. Recruit AI stores and processes it
        only to run the service for you. We do not read it, sell it, or use it to train AI models,
        and our internal admin tools show only counts (for example "40 resumes scored"), never the
        content itself.
      </p>

      <H>2. What we collect about users</H>
      <ul className="list-disc pl-5 space-y-1">
        <li>Account details: email address, password (stored only as a secure hash), organisation name, sign-up method (email or Google).</li>
        <li>Sign-in records: when you sign in or out, and the IP address used — to protect accounts from attack.</li>
        <li>
          An activity log of actions taken in the product — for example "created a role", "sent an
          email", "connected an AI provider" — with who did it and when. It never contains what you
          typed, candidate details or file contents.
        </li>
        <li>Failed sign-in attempts, with the email address that was tried, to detect password guessing.</li>
        <li>How many AI requests your workspace makes each month, to apply the free allowance.</li>
        <li>If you connect your own AI provider: the key, stored encrypted and never shown again after saving.</li>
      </ul>

      <H>3. Why we use it</H>
      <ul className="list-disc pl-5 space-y-1">
        <li>To provide the service you signed up for and keep it working.</li>
        <li>To keep accounts and candidate data secure, and to detect abuse.</li>
        <li>To understand, in aggregate, which features are used, so we can improve the product.</li>
        <li>To contact you about your account (for example if your free AI allowance runs out).</li>
      </ul>
      <p>We do not sell personal data and do not show advertising.</p>

      <H>4. How long we keep it</H>
      <ul className="list-disc pl-5 space-y-1">
        <li>Account data and workspace content: for as long as the account exists.</li>
        <li>
          Detailed activity-log entries: <strong>{facts.activity_retention_days} days</strong>. After
          that they are reduced to daily totals per workspace (for example "12 resumes scored on 3
          March") with no link to any individual, which we keep to understand long-term usage.
        </li>
        <li>Database backups: kept for 14 days, then deleted.</li>
      </ul>

      <H>5. Who else processes data</H>
      <p>To run features you use, some data is sent to these service providers:</p>
      <ul className="list-disc pl-5 space-y-1">
        <li>
          <strong>AI model provider.</strong> Text you ask the AI to work on (job descriptions,
          resume text, interview answers) is sent to the model provider to generate the result:
          NVIDIA during the free allowance, or the provider you connect yourself. These providers
          may process data outside India.
        </li>
        <li><strong>Google</strong>, if you connect Google Calendar or sign in with Google.</li>
        <li><strong>Resend</strong>, to deliver emails you choose to send.</li>
      </ul>

      <H>6. Candidates</H>
      <p>
        If a recruiter using Recruit AI holds your details, that recruiter's organisation is
        responsible for them. Please contact them first to access, correct or delete your data.
        If you cannot reach them, contact us (below) and we will pass your request on and help
        where we can.
      </p>

      <H>7. Your rights</H>
      <p>Under the DPDP Act you can ask us to:</p>
      <ul className="list-disc pl-5 space-y-1">
        <li>tell you what personal data we hold about you and how it is used;</li>
        <li>correct or complete it;</li>
        <li>delete your account and its data;</li>
        <li>withdraw consent (this means closing your account, since the service cannot run without it);</li>
        <li>nominate someone to exercise these rights for you;</li>
        <li>and raise a grievance, which we will answer promptly. If you are not satisfied, you may complain to the Data Protection Board of India.</li>
      </ul>

      <H>8. Security</H>
      <p>
        Data is encrypted in transit (HTTPS). Workspaces are isolated from each other, AI provider
        keys are encrypted at rest, and access to the database is restricted to the application
        itself. No system is perfectly secure; if a breach affects your data we will tell you and
        the Data Protection Board as the law requires.
      </p>

      <H>9. Contact</H>
      <p>For any privacy question, request or grievance, contact us at {contact}.</p>

      <H>10. Changes</H>
      <p>If this notice changes in a way that matters, we will tell users inside the product before it takes effect.</p>

      <p className="pt-6"><Link to="/login" className="underline">Back to Recruit AI</Link></p>
    </div>
  )
}
