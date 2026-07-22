# Recruit AI — Start Here

Welcome! Getting your own Recruit AI running takes three steps.
Everything runs on **your own accounts** — your database, your AI key,
your email — nothing is shared with anyone else.

## What you need installed
- **Python 3.10+** — https://python.org (tick "Add to PATH" during install)
- **Node.js 18+** — https://nodejs.org

## Step 1 — Enter your keys
Open **`config.env`** in Notepad. It lists every key you need and exactly
where to get each one (all have free tiers). Fill in the blanks, save.

## Step 2 — Run setup once
Double-click **`setup.bat`**. It checks your keys, installs everything,
and then asks you to do one manual action: copy the contents of
**`setup-database.sql`** into your Supabase project's SQL Editor and click
Run (this creates your database tables — once only).

## Step 3 — Start the app
Double-click **`start.bat`** — or from cmd:

```
cd /d <this folder>
start.bat
```

Two windows open (the app's engine and its interface) and your browser
opens at http://localhost:5173. Sign up with your email, name your
organization, and you're in. Closing the two windows stops the app.

## Learn the product
- **`docs/recruit-ai-book.pdf`** — the full owner's manual (what it does,
  how to operate it, troubleshooting).
- **`docs/USER_GUIDE.md`** — quick step-by-step reference.

## If something doesn't work
The book's "Limits & troubleshooting" chapter covers every common issue
(wrong redirect URI, unverified email domain, AI quota, etc.).
