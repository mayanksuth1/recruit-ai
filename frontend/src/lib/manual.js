// The user manual, as data rather than prose markup.
//
// One source feeds two surfaces: the per-page help drawer (ManualHelp) and the
// full /manual page. Keeping it structured — rather than a blob of HTML — means
// the renderer applies the app's own Tailwind theme, so the manual can never
// drift visually from the UI it documents.
//
// Inline **bold** is supported in `t` strings; see renderInline in ManualHelp.

// Tailwind scans source for LITERAL class strings, so tones must be a static
// lookup. Building `bg-${tone}` dynamically would get purged at build time.
export const TONES = {
  mint: { badge: 'bg-mint text-teal-900', pill: 'bg-mint text-teal-900', swatch: 'bg-mint' },
  babyblue: { badge: 'bg-babyblue text-sky-900', pill: 'bg-babyblue text-sky-900', swatch: 'bg-babyblue' },
  lavender: { badge: 'bg-lavender text-indigo-900', pill: 'bg-lavender text-indigo-900', swatch: 'bg-lavender' },
  butter: { badge: 'bg-butter text-amber-800', pill: 'bg-butter text-amber-800', swatch: 'bg-butter' },
  rosy: { badge: 'bg-rosy text-rose-900', pill: 'bg-rosy text-rose-900', swatch: 'bg-rosy' },
  peach: { badge: 'bg-peach text-amber-800', pill: 'bg-peach text-amber-800', swatch: 'bg-peach' },
  blush: { badge: 'bg-blush text-cocoa', pill: 'bg-blush text-cocoa', swatch: 'bg-blush' },
  outline: { badge: '', pill: 'bg-white text-cocoa/70 border-2 border-blush', swatch: 'bg-white' },
}

export const MANUAL = [
  {
    id: 'dashboard',
    num: '00',
    title: 'Dashboard',
    tag: 'What needs you',
    tone: 'peach',
    lede:
      'A live read of the pipeline and, more usefully, a list of everything currently ' +
      'blocked on a human decision.',
    body: [
      {
        k: 'card',
        h3: 'The six tiles',
        blocks: [
          {
            k: 'kv',
            rows: [
              ['Open roles', 'Roles with status open. Click through to the role list.'],
              ['Candidates', 'Every candidate attached to a role, across all roles.'],
              ['Talent pool', 'Org-wide pool entries, which persist across roles.'],
              ['Email drafts', 'Written but unsent. Nothing leaves until you send it.'],
              ['Upcoming interviews', 'Scheduled, still in the future.'],
              ['Not embedded', 'Items that will not appear in semantic search until embedded.'],
            ],
          },
        ],
      },
      {
        k: 'card',
        h3: 'Needs you',
        blocks: [
          {
            k: 'p',
            t:
              'The part worth reading first. Each row is something only a person can clear — ' +
              'a pending approve/reject, an unreviewed draft, a past interview with no feedback ' +
              'logged, an AI interview link about to expire, a completed interview not yet ' +
              'scored, or an open role with no LinkedIn post. Every row links straight to the ' +
              'screen where you fix it.',
          },
          {
            k: 'note',
            tone: 'blush',
            t:
              'An empty list is a real result, not a broken page — it means nothing is waiting ' +
              'on you.',
          },
        ],
      },
      {
        k: 'card',
        h3: 'Stages and activity',
        blocks: [
          {
            k: 'p',
            t:
              '**Candidates by stage** shows the spread across screening → outreach → interview ' +
              '→ offer → closed. **Recent activity** is a merged feed of roles opened, candidates ' +
              'added, emails drafted and sent, interviews, and AI interview sessions, newest first. ' +
              '**Refresh** re-reads it without reloading the page.',
          },
          {
            k: 'p',
            t:
              'For conversion rates, drop-off between stages and the client-facing PDF, use ' +
              '**Reports** instead — this page is about what to do next, not how the funnel is ' +
              'performing.',
          },
        ],
      },
    ],
  },
  {
    id: 'roles',
    num: '01',
    title: 'Roles',
    tag: 'Pipeline hub',
    tone: 'mint',
    lede:
      'Every hire starts here. A role holds the job description, the candidates matched or ' +
      'uploaded against it, and the five-stage pipeline each one moves through.',
    body: [
      {
        k: 'card',
        h3: 'Create a role',
        blocks: [
          {
            k: 'p',
            t:
              'Click **New role**, then **Create role** to save it. The job description you write ' +
              'here is what every match score, resume screen, and outreach draft is generated ' +
              'against — the more specific the must-haves and nice-to-haves, the sharper the scoring.',
          },
        ],
      },
      {
        k: 'card',
        h3: 'Getting candidates onto a role',
        blocks: [
          {
            k: 'pills',
            items: [
              { label: 'Upload resume PDF(s)', tone: 'outline' },
              { label: 'Match from talent pool', tone: 'outline' },
              { label: 'Generate Boolean search', tone: 'outline' },
            ],
          },
          {
            k: 'p',
            t:
              'Uploaded resumes are scored directly against the job description. **Match from talent ' +
              'pool** runs the same scoring against everyone already imported into Talent Pool. ' +
              '**Generate Boolean search** writes a search string you can paste into LinkedIn ' +
              'Recruiter or another external sourcing tool — Recruit AI does not scrape LinkedIn ' +
              'itself (see the note in Talent Pool).',
          },
        ],
      },
      {
        k: 'card',
        h3: 'Generate LinkedIn post',
        blocks: [
          {
            k: 'p',
            t:
              '**Generate LinkedIn post** writes job-post copy from two things: your ' +
              '**Company profile** (Settings) and this role’s job description. Fill the ' +
              'company profile in first — without it the button returns an error rather ' +
              'than inventing a company.',
          },
          {
            k: 'p',
            t:
              'The draft appears in an editable box. Edit it freely and click **Save edits** ' +
              'to keep changes, **Regenerate** for a fresh take, or **Copy** to put it on your ' +
              'clipboard. The draft is stored against the role, so it is still there after a refresh.',
          },
          {
            k: 'note',
            tone: 'blush',
            t:
              'There is no publish or send button, by design. Recruit AI never posts to ' +
              'LinkedIn — it has no connection to your account. You copy the text and post it yourself.',
          },
        ],
      },
      {
        k: 'card',
        h3: 'Reading a candidate card',
        blocks: [
          {
            k: 'p',
            t:
              'Each candidate shows a composite match score plus its three inputs, and a short ' +
              'written rationale explaining the number.',
          },
          {
            k: 'scores',
            items: [
              { label: 'overall', value: 92 },
              { label: 'skills', value: 95 },
              { label: 'experience', value: 94 },
              { label: 'education', value: 82 },
            ],
          },
          {
            k: 'p',
            t:
              'The rationale is generated per candidate, not templated — it calls out specific gaps ' +
              '(e.g. "Celery-based, not ASGI" or "Python is secondary to Go") so you know exactly ' +
              'what is driving the score down before you act on it.',
          },
          {
            k: 'pillnote',
            t: 'Status badges use the same colour key throughout the app:',
            items: [
              { label: 'approved', tone: 'mint' },
              { label: 'pending', tone: 'butter' },
              { label: 'rejected', tone: 'rosy' },
            ],
          },
        ],
      },
      {
        k: 'card',
        h3: 'Moving a candidate through the pipeline',
        blocks: [
          {
            k: 'steps',
            items: [
              { idx: '1', t: '**Approve / Reject** — the first decision. Approving unlocks the rest of the action row; rejecting stops it there.' },
              { idx: '2', t: '**Reset** — clears the decision and returns the candidate to pending if you change your mind.' },
              { idx: '3', t: '**Draft outreach** — writes an outreach email and sends it to Outbox as a draft. It does not send anything.' },
              { idx: '4', t: '**Schedule interview** — opens interview scheduling for that candidate; shows up under Interviews once set.' },
              { idx: '5', t: '**AI interview** — issues an async AI-interview link for that candidate (see AI Interviews).' },
              { idx: '6', t: '**Approve for offer** — the final gate before the offer stage.' },
            ],
          },
          {
            k: 'p',
            t:
              'The stage bar underneath each candidate — **screening → outreach → interview → offer ' +
              '→ closed** — always reflects where they actually are; it updates as you use the ' +
              'actions above rather than needing to be set by hand.',
          },
        ],
      },
    ],
  },

  {
    id: 'talent-pool',
    num: '02',
    title: 'Talent Pool',
    tag: 'Org-wide',
    tone: 'babyblue',
    lede:
      'Candidates here are not tied to one role — they persist across every role you run, so ' +
      'sourcing work is never done twice.',
    body: [
      {
        k: 'card',
        h3: 'Getting candidates in',
        blocks: [
          {
            k: 'pills',
            items: [
              { label: 'Upload CSV file', tone: 'outline' },
              { label: 'Import pasted rows', tone: 'outline' },
              { label: 'Scan for duplicates', tone: 'outline' },
            ],
          },
          {
            k: 'p',
            t:
              'Accepts name, email, title, company, and skills columns, either as a file or pasted ' +
              'directly. Run **Scan for duplicates** after a bulk import — it is the safeguard ' +
              'before candidates get matched against multiple live roles.',
          },
        ],
      },
      {
        k: 'card',
        h3: "What's on a profile",
        blocks: [
          {
            k: 'table',
            head: ['Field', 'Example'],
            rows: [
              ['Name / Title / Company', 'Priya Raghavan — Staff Backend Engineer · Flipkart'],
              ['Contact', 'Email captured from import'],
              ['Skills', 'Full tag list from the source data'],
              ['Source', 'How they entered the pool, e.g. csv_import'],
            ],
          },
        ],
      },
      {
        k: 'note',
        tone: 'butter',
        title: 'On LinkedIn:',
        t:
          'live profile search or scraping is not supported — it has no public API for this and ' +
          'would violate LinkedIn’s terms of service. The supported path is exporting your ' +
          'LinkedIn search results to CSV and importing them here (or via the Boolean search ' +
          'string from a role page).',
      },
    ],
  },

  {
    id: 'outbox',
    num: '03',
    title: 'Outbox',
    tag: 'Human in the loop',
    tone: 'lavender',
    lede:
      'Every email Recruit AI writes lands here first. Nothing leaves your domain without you ' +
      'clicking send.',
    body: [
      {
        k: 'card',
        h3: 'The three tabs',
        blocks: [
          {
            k: 'kv',
            rows: [
              ['Drafts', 'Outreach and follow-ups waiting on your review. Read, edit, send, or discard each one individually.'],
              ['Sent', 'A record of what actually went out.'],
              ['Discarded', 'Drafts you chose not to send — kept for reference, not deleted.'],
            ],
          },
        ],
      },
      {
        k: 'card',
        h3: 'Follow-up automation',
        blocks: [
          {
            k: 'p',
            t:
              'Set **Follow up after [n] days** and click **Draft follow-ups** to generate follow-up ' +
              'emails for candidates who have not replied — as drafts, same as everything else. ' +
              'Nothing sends until you approve it from the Drafts tab.',
          },
        ],
      },
      {
        k: 'note',
        tone: 'blush',
        t:
          'A candidate has to be approved on their role page first, then **Draft outreach** clicked ' +
          'there, before anything appears in Outbox. An empty Outbox usually just means step one ' +
          'has not happened yet.',
      },
    ],
  },

  {
    id: 'interviews',
    num: '04',
    title: 'Interviews',
    tag: 'Live scheduling',
    tone: 'butter',
    lede:
      'Human-run interviews scheduled from a candidate’s role page, tracked here with automatic ' +
      'reminders so nothing falls through between scheduling and feedback.',
    body: [
      {
        k: 'card',
        h3: 'What runs automatically',
        blocks: [
          {
            k: 'steps',
            items: [
              { idx: '24h', t: 'before the interview — a reminder is drafted automatically.' },
              { idx: '48h', t: 'after, if feedback is still missing — the interviewer is nudged.' },
              { idx: '15m', t: 'a background check runs on this cadence to catch anything due. Click **Run checks now** to force one immediately rather than waiting.' },
            ],
          },
        ],
      },
      {
        k: 'note',
        tone: 'blush',
        t:
          'To schedule one: open the candidate on their role page and use **Schedule interview**. ' +
          'It will not appear as an option here directly — this page is for tracking and reminders ' +
          'once one exists.',
      },
    ],
  },

  {
    id: 'ai-interviews',
    num: '05',
    title: 'AI Interviews',
    tag: 'Async, adaptive',
    tone: 'mint',
    lede:
      'A five-question async screen a candidate can complete on their own time, where each question ' +
      'is written from their previous answer rather than pulled from a fixed script.',
    body: [
      {
        k: 'card',
        h3: 'Issuing one',
        blocks: [
          {
            k: 'p',
            t:
              'Open the role the candidate is on, and use **AI interview** on an approved ' +
              'candidate’s action row. The link is single-use and expires **72 hours** after it ' +
              'is issued — reissue if it lapses before they complete it.',
          },
        ],
      },
      {
        k: 'card',
        h3: 'Embed backlog',
        blocks: [
          {
            k: 'p',
            t:
              'Answers and profiles get embedded so Semantic Search can find them by meaning. The ' +
              'count next to **Embed backlog** is how many items are written but not yet embedded — ' +
              'they will not surface in search until that backlog is cleared.',
          },
        ],
      },
    ],
  },

  {
    id: 'search',
    num: '06',
    title: 'Search',
    tag: 'Semantic',
    tone: 'rosy',
    lede:
      'Describe the person you want in plain language — this searches meaning, not keyword overlap.',
    body: [
      {
        k: 'card',
        h3: 'Scope',
        blocks: [
          {
            k: 'pills',
            items: [
              { label: 'Profiles', tone: 'outline' },
              { label: 'Interview answers', tone: 'outline' },
            ],
          },
          {
            k: 'p',
            t:
              'Toggle either off to narrow a search to just talent-pool profiles or just what ' +
              'candidates actually said in their AI interviews.',
          },
        ],
      },
      {
        k: 'note',
        tone: 'butter',
        title: 'Stale results:',
        t:
          'if the page flags items changed since they were last embedded, those will not match a ' +
          'query until you clear the backlog from AI Interviews. Worth checking before trusting ' +
          'that a search came back empty.',
      },
    ],
  },

  {
    id: 'reports',
    num: '07',
    title: 'Reports',
    tag: 'Internal + client-facing',
    tone: 'peach',
    lede:
      'Two views of the same pipeline data, scoped for who is reading — plus a weekly summary you ' +
      'control the release of.',
    body: [
      {
        k: 'card',
        h3: 'Recruiter view vs. Client view',
        blocks: [
          {
            k: 'kv',
            rows: [
              ['Recruiter view', 'Internal — full detail, including upcoming interviews.'],
              ['Client view', "The scoped version safe to hand to whoever you're hiring for."],
            ],
          },
        ],
      },
      {
        k: 'card',
        h3: 'Weekly summaries',
        blocks: [
          {
            k: 'p',
            t:
              'Click **Generate this week** to produce one. It is generated and stored, **never ' +
              'auto-emailed** — download it as a PDF when you are ready to share it yourself.',
          },
        ],
      },
    ],
  },

  {
    id: 'settings',
    num: '08',
    title: 'Settings',
    tag: 'Integrations',
    tone: 'blush',
    lede:
      'Your company profile, plus two integration points: your calendar, and whatever ATS ' +
      'you already run hiring through.',
    body: [
      {
        k: 'card',
        h3: 'Company profile',
        blocks: [
          {
            k: 'p',
            t:
              'Fill this in once: company name, what the company does, culture and benefits, ' +
              'location, and anything else worth telling candidates. It is the context the ' +
              '**Generate LinkedIn post** action on a role page writes from.',
          },
          {
            k: 'p',
            t:
              'The generator is told never to invent facts, so anything not written here will ' +
              'not appear in a post. Thin profile, thin post — specifics are what stop the copy ' +
              'reading like boilerplate.',
          },
        ],
      },
      {
        k: 'card',
        h3: 'Google Calendar',
        blocks: [
          {
            k: 'p',
            t:
              'Click **Connect Google Calendar**. Once connected, interview slots get proposed from ' +
              'your real availability and scheduled events land on your calendar automatically ' +
              'instead of you cross-checking by hand.',
          },
        ],
      },
      {
        k: 'card',
        h3: 'ATS sync — generic webhooks',
        blocks: [
          {
            k: 'p',
            t:
              'Works with anything that speaks webhooks — Greenhouse, Lever, and similar. Set an ' +
              '**outbound webhook URL** (where Recruit AI posts stage changes to) and a **shared ' +
              'secret** for HMAC signing in both directions, then **Save**. Your ATS pushes changes ' +
              'back to the inbound URL shown on the page. Use **Send test event** to confirm the ' +
              'connection before relying on it.',
          },
        ],
      },
      {
        k: 'note',
        tone: 'butter',
        title: 'Workday',
        t:
          'is not covered by the generic webhook — it needs its paid enterprise API tier, arranged ' +
          'separately.',
      },
    ],
  },
]

export const getManualSection = (id) => MANUAL.find((m) => m.id === id) || null
