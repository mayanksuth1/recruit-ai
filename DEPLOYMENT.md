# Deploying Recruit AI

Frontend → **Vercel**, backend → **Render**, database/auth → **Supabase**
(already hosted). Do the steps in order — the frontend needs the backend URL,
and the backend needs the frontend URL.

---

## 0. Prerequisites
- The GitHub repo is pushed (see main README / the push step).
- Your Supabase project already has the tables (migrations 0001–0006 applied).
- Have your keys from `config.env` handy — you'll paste them into dashboards,
  never into files.

---

## 1. Backend → Render (do this first)

You need the backend live before configuring the frontend, because the
frontend must point at the backend's URL.

**Create the service**
1. Go to https://dashboard.render.com → **New +** → **Web Service**.
2. Connect your GitHub and pick the **recruit-ai** repo.
3. Render may auto-detect `render.yaml` (Blueprint). Either accept it, or
   configure manually with these exact settings:
   - **Root Directory:** `backend`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/api/health`
   - **Instance Type:** Free

**Add environment variables** (Environment tab). Copy the *names* from your
`config.env`; paste the real *values*:

| Variable | Value |
|---|---|
| `SUPABASE_URL` | your Supabase project URL |
| `SUPABASE_SECRET_KEY` | Supabase **secret** key (server-only) |
| `GEMINI_API_KEY` | your Gemini key |
| `GEMINI_MODEL` | `gemini-2.5-flash` |
| `GEMINI_FALLBACK_MODEL` | `gemini-2.5-flash-lite` |
| `RESEND_API_KEY` | your Resend key |
| `EMAIL_FROM` | `Recruit AI <onboarding@resend.dev>` (or your verified domain) |
| `GOOGLE_CLIENT_ID` | your OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | your OAuth client secret |
| `GOOGLE_REDIRECT_URI` | `https://<your-render-url>/api/calendar/oauth/callback` |
| `FRONTEND_URL` | *(fill after step 2 — your Vercel URL)* |
| `CORS_ORIGINS` | *(fill after step 2 — your Vercel URL)* |
| `SCHEDULER_TIMEZONE` | `Asia/Kolkata` |

4. Click **Create Web Service**. Wait for the deploy to go green.
5. Note the URL, e.g. `https://recruit-ai-backend.onrender.com`.
6. **Test it:** open `https://<your-render-url>/api/health` → should return
   `{"status":"ok"}`.

> Free tier note: the service sleeps after ~15 min idle and takes ~30–50s to
> wake on the next request. First load after idle will be slow — that's normal.
> `FRONTEND_URL` and `CORS_ORIGINS` are left blank for now; you'll set them in
> step 3 once Vercel gives you a domain.

---

## 2. Frontend → Vercel

**Create the project**
1. Go to https://vercel.com → **Add New** → **Project** → import **recruit-ai**.
2. Settings (Vite is auto-detected; confirm):
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`

**Add environment variables** (all three):

| Variable | Value |
|---|---|
| `VITE_SUPABASE_URL` | your Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase **publishable/anon** key (public — safe in frontend) |
| `VITE_API_URL` | your Render backend URL from step 1 (no trailing slash) |

3. Click **Deploy**. When it finishes, note the URL, e.g.
   `https://recruit-ai.vercel.app`.

---

## 3. Wire the two together (CORS + links)

Now that you have the Vercel URL, go **back to Render → Environment** and set:

- `FRONTEND_URL` = `https://recruit-ai.vercel.app`
- `CORS_ORIGINS` = `https://recruit-ai.vercel.app`
  (comma-separate if you have several, e.g. a custom domain too)

Save — Render redeploys automatically. The backend already reads CORS from
`CORS_ORIGINS`, so no code change is needed; this just tells it to trust your
Vercel domain.

**Also update Google OAuth** (for interview scheduling to work in prod):
Google Cloud Console → Credentials → your OAuth client → **Authorized redirect
URIs** → add `https://<your-render-url>/api/calendar/oauth/callback`
(matching `GOOGLE_REDIRECT_URI`).

**And Supabase Auth** → URL Configuration → set the **Site URL** to your
Vercel URL (keeps auth redirects correct).

---

## 4. Verification checklist

Work down the list — each step proves one link in the chain.

- [ ] **Backend alive:** `https://<render-url>/api/health` returns `{"status":"ok"}`.
- [ ] **Frontend loads:** open the Vercel URL — you see the sign-in screen,
      no "Configuration needed" banner (means the anon key is set).
- [ ] **Frontend → backend → Supabase (write path):** click **Sign up**,
      create an org. Success means the browser reached the Render backend,
      which reached Supabase. (Open DevTools → Network; the `signup` call
      should hit your Render URL and return 201.)
- [ ] **Frontend → backend (read path):** after signup you land on Roles.
      Create a role → it appears. (A `POST /api/roles` to Render returns 201.)
- [ ] **No CORS errors:** DevTools → Console is clean. A CORS failure looks
      like "blocked by CORS policy" — fix by confirming `CORS_ORIGINS` on
      Render exactly matches the Vercel origin (scheme + host, no trailing slash).
- [ ] **AI path:** upload a resume PDF on a role → it scores. (Confirms the
      Gemini key on Render works.)
- [ ] **Auth persists:** refresh the page — you stay signed in. (Supabase
      session in the browser + backend JWT verification both working.)
- [ ] **Public page:** the candidate scheduling link (`/schedule/<token>`)
      loads without login. (Confirms SPA routing via `vercel.json` and the
      public API path.)

If all boxes check, frontend, backend, and Supabase are fully talking.

---

## Common gotchas
- **CORS blocked:** origin mismatch. `https://app.vercel.app` ≠
  `https://app.vercel.app/` ≠ `http://…`. Match exactly.
- **Frontend calls localhost in prod:** `VITE_API_URL` wasn't set at build
  time. Vite bakes env vars in at build — set it in Vercel and redeploy.
- **First request after idle hangs ~40s:** Render free tier cold start. Normal.
- **Scheduling OAuth fails:** `GOOGLE_REDIRECT_URI` on Render must exactly
  match a URI registered on the Google OAuth client.
