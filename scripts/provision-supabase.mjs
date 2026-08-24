#!/usr/bin/env node
/* Provision a hosted Supabase project for Recruit AI, end to end.
 *
 * Creates the project, waits for it to come up, applies migrations 0001-0011,
 * verifies the schema, reads the API keys and smoke-tests the live REST API
 * including an anon-lockout check — all through the Management API, which needs
 * only an access token. No database password is required for any of it.
 *
 *   npx supabase login            # once, in your terminal — browser approval
 *   node scripts/provision-supabase.mjs
 *
 * or, with a Personal Access Token instead:
 *
 *   SUPABASE_ACCESS_TOKEN=<pat> node scripts/provision-supabase.mjs
 *
 * Secrets are never printed. The generated database password and the project's
 * API keys are written to .env.supabase.local (gitignored) and referenced by
 * path only — copy them from there into Render and Netlify.
 *
 * This script is idempotent: re-running it reuses an existing project of the
 * same name and skips migrations that have already been applied.
 *
 * Options (env):
 *   PROJECT_NAME   default "recruit-ai"
 *   REGION         default "ap-south-1" (Mumbai)
 *   ORG_ID         default: your only org, or set it if you have several
 *   PLAN           default "free"
 *   PROJECT_REF    reuse a specific existing project instead of creating one
 *
 * Deliberately NOT applied: 0000_optional_admin_exec.sql. It grants the service
 * key full DDL power over the database, nothing in the app needs it, and this
 * script gets its DDL from the Management API instead. That matches what
 * setup-database.sql ships.
 */

import { readFileSync, writeFileSync, existsSync, readdirSync, appendFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';
import crypto from 'node:crypto';

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, '..');
const API = 'https://api.supabase.com';

const PROJECT_NAME = process.env.PROJECT_NAME || 'recruit-ai';
const REGION = process.env.REGION || 'ap-south-1';
const PLAN = process.env.PLAN || 'free';
const ENV_OUT = join(repo, '.env.supabase.local');

/* Exiting mid-flight trips `Assertion failed: !(handle->flags &
   UV_HANDLE_CLOSING)` on Windows: process.exit() races undici's keep-alive
   socket pool, and the script looks like it crashed right after printing a
   perfectly good error. Instead: set the exit code, ask the pool to close, and
   let Node shut down on its own. */
class ExitSignal extends Error {}
process.on('uncaughtException', (e) => {
  if (e instanceof ExitSignal) return; // message already printed by die()
  console.error(e);
  process.exitCode = 1;
});

const die = (m) => {
  console.error('\n  x ' + m + '\n');
  process.exitCode = 1;
  const pool = globalThis[Symbol.for('undici.globalDispatcher.1')];
  if (pool && typeof pool.close === 'function') pool.close().catch(() => {});
  throw new ExitSignal(m);
};
const ok = (m) => console.log('  + ' + m);
const step = (m) => console.log('\n' + m);
const info = (m) => console.log('    ' + m);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------ the token -- */
function findToken() {
  if (process.env.SUPABASE_ACCESS_TOKEN) {
    return { token: process.env.SUPABASE_ACCESS_TOKEN, from: 'SUPABASE_ACCESS_TOKEN' };
  }
  const candidates = [
    join(homedir(), '.supabase', 'access-token'),
    join(process.env.APPDATA || '', 'supabase', 'access-token'),
    join(process.env.XDG_CONFIG_HOME || join(homedir(), '.config'), 'supabase', 'access-token')
  ];
  for (const p of candidates) {
    try {
      if (existsSync(p)) {
        const t = readFileSync(p, 'utf8').trim();
        if (t) return { token: t, from: p };
      }
    } catch { /* unreadable, keep looking */ }
  }
  return null;
}

const found = findToken();
if (!found) {
  die('No Supabase access token.\n' +
      '    Run this once in your terminal, approve in the browser, then re-run me:\n' +
      '        npx supabase login\n' +
      '    Or create a Personal Access Token at supabase.com/dashboard/account/tokens and:\n' +
      '        SUPABASE_ACCESS_TOKEN=<pat> node scripts/provision-supabase.mjs');
}
// Never print the token itself — only where it came from.
ok('authenticated (token from ' + (found.from === 'SUPABASE_ACCESS_TOKEN' ? 'environment' : found.from) + ')');
const TOKEN = found.token;

const api = async (path, opts = {}) => {
  let res;
  try {
    res = await fetch(API + path, {
      ...opts,
      headers: { Authorization: 'Bearer ' + TOKEN, 'Content-Type': 'application/json', ...(opts.headers || {}) }
    });
  } catch (e) {
    die('Could not reach the Supabase Management API: ' + (e.message || e));
  }
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  return { status: res.status, ok: res.ok, body };
};

/* --------------------------------------------------------------- 1. org -- */
step('Organisation');
let orgId = process.env.ORG_ID;
{
  const r = await api('/v1/organizations');
  if (r.status === 401) die('That token was rejected. Re-run `npx supabase login`, or check the PAT.');
  if (!r.ok) die('Could not list organisations: ' + r.status + ' ' + JSON.stringify(r.body).slice(0, 200));
  const orgs = r.body || [];
  if (!orgs.length) die('No organisations on this account. Create one in the dashboard first.');
  if (!orgId) {
    if (orgs.length > 1) {
      console.log('    Several organisations found — set ORG_ID to pick one:');
      orgs.forEach((o) => console.log('      ' + o.id + '  ' + o.name));
      die('ORG_ID not set.');
    }
    orgId = orgs[0].id;
  }
  ok('using organisation ' + (orgs.find((o) => o.id === orgId)?.name || orgId));
}

/* ----------------------------------------------------------- 2. project -- */
step('Project');
let ref = process.env.PROJECT_REF || null;
{
  const existing = await api('/v1/projects');
  if (!existing.ok) die('Could not list projects: ' + existing.status);
  const match = (existing.body || []).find((p) => p.name === PROJECT_NAME);

  if (match) {
    ref = match.id;
    ok('project "' + PROJECT_NAME + '" already exists (' + ref + ') — reusing it');
  } else if (ref) {
    ok('using the project ref you supplied: ' + ref);
  } else {
    /* Generated here so a production password never passes through a chat log
       or shell history. It is written to .env.supabase.local and nowhere else. */
    const dbPass = crypto.randomBytes(24).toString('base64url');
    const r = await api('/v1/projects', {
      method: 'POST',
      body: JSON.stringify({
        name: PROJECT_NAME, organization_id: orgId, region: REGION,
        plan: PLAN, db_pass: dbPass
      })
    });
    if (!r.ok) die('Could not create the project: ' + r.status + ' ' + JSON.stringify(r.body).slice(0, 300));
    ref = r.body.id || r.body.ref;
    writeFileSync(ENV_OUT,
      '# Generated by scripts/provision-supabase.mjs - keep this file private.\n' +
      '# This is the ONLY copy of the database password.\n' +
      'SUPABASE_PROJECT_REF=' + ref + '\n' +
      'SUPABASE_DB_PASSWORD=' + dbPass + '\n', { mode: 0o600 });
    ok('created project "' + PROJECT_NAME + '" (' + ref + ') in ' + REGION);
    info('database password written to .env.supabase.local — it is not printed anywhere else');
  }
}

/* ------------------------------------------------------------ 3. health -- */
step('Waiting for the database to come up');
{
  const deadline = Date.now() + 6 * 60 * 1000;
  let healthy = false;
  while (Date.now() < deadline) {
    const r = await api('/v1/projects/' + ref + '/health?services=db,rest');
    if (r.ok && Array.isArray(r.body)) {
      const db = r.body.find((s) => s.name === 'db');
      if (db && (db.healthy === true || db.status === 'ACTIVE_HEALTHY')) { healthy = true; break; }
    }
    await sleep(10000);
    process.stdout.write('.');
  }
  process.stdout.write('\n');
  if (!healthy) die('The project did not become healthy within 6 minutes. Check the dashboard, then re-run — this script is idempotent.');
  ok('database is up');
}

/* -------------------------------------------------------- 4. migrations -- */
step('Migrations');
const runSql = async (sql) =>
  api('/v1/projects/' + ref + '/database/query', { method: 'POST', body: JSON.stringify({ query: sql }) });
{
  const already = await runSql("select to_regclass('public.organizations') is not null as present;");
  const hasSchema = already.ok && Array.isArray(already.body) && already.body[0]?.present;

  if (hasSchema) {
    ok('public.organizations already present — skipping migrations');
    info('re-applying 0011 would truncate ai_embeddings, so this skip is deliberate');
  } else {
    const dir = join(repo, 'supabase', 'migrations');
    // 0000 is excluded on purpose — see the header comment.
    const files = readdirSync(dir).filter((f) => f.endsWith('.sql') && !f.startsWith('0000')).sort();
    for (const f of files) {
      const sql = readFileSync(join(dir, f), 'utf8');
      const r = await runSql(sql);
      if (!r.ok) die('Migration ' + f + ' failed: ' + r.status + ' ' + JSON.stringify(r.body).slice(0, 400));
      ok('applied ' + f);
    }
  }
}

/* ------------------------------------------------------------- 5. verify -- */
step('Verifying the schema');
{
  const check = await runSql(`
    select
      (select count(*) from pg_tables where schemaname = 'public')::int              as tables,
      (select count(*) from pg_policies where schemaname = 'public')::int            as policies,
      (select count(*) from public.ai_interview_rubric_criteria)::int                as criteria,
      (select a.atttypmod from pg_attribute a
        where a.attrelid = 'public.ai_embeddings'::regclass and a.attname = 'embedding')::int as dims,
      (select count(*) from pg_extension where extname = 'vector')::int              as vector_ext;`);
  if (!check.ok) die('Could not verify the schema: ' + JSON.stringify(check.body).slice(0, 300));
  const v = check.body[0];
  if (v.tables < 19) die('Expected at least 19 tables, found ' + v.tables + '.');
  if (!v.vector_ext) die('The `vector` extension is not installed — 0009 did not take.');
  if (v.dims !== 1024) die('ai_embeddings.embedding is ' + v.dims + '-dimensional, expected 1024 (migration 0011).');
  if (v.criteria !== 5) die('Expected 5 seeded rubric criteria, found ' + v.criteria + '.');
  ok(v.tables + ' tables, ' + v.policies + ' RLS policies, vector(' + v.dims + '), ' + v.criteria + ' rubric criteria');
}

/* --------------------------------------------------------------- 6. keys -- */
step('API keys');
let secretKey = null;
let publishableKey = null;
const projectUrl = 'https://' + ref + '.supabase.co';
{
  const r = await api('/v1/projects/' + ref + '/api-keys?reveal=true');
  if (!r.ok) die('Could not read the API keys: ' + r.status + ' ' + JSON.stringify(r.body).slice(0, 200));
  /* Newer projects issue sb_secret_ / sb_publishable_ keys; older ones issue
     the legacy service_role/anon JWTs. The app accepts either, so take
     whichever this project has, preferring the newer pair. */
  for (const k of r.body || []) {
    if (k.type === 'secret' || k.name === 'secret') secretKey = k.api_key;
    if (k.type === 'publishable' || k.name === 'publishable') publishableKey = k.api_key;
  }
  for (const k of r.body || []) {
    if (!secretKey && k.name === 'service_role') secretKey = k.api_key;
    if (!publishableKey && k.name === 'anon') publishableKey = k.api_key;
  }
  if (!secretKey) die('No secret / service_role key returned.');
  if (!publishableKey) die('No publishable / anon key returned.');

  // Written to disk, never printed.
  appendFileSync(ENV_OUT,
    'SUPABASE_URL=' + projectUrl + '\n' +
    'SUPABASE_SECRET_KEY=' + secretKey + '\n' +
    'VITE_SUPABASE_URL=' + projectUrl + '\n' +
    'VITE_SUPABASE_ANON_KEY=' + publishableKey + '\n');
  ok('keys written to .env.supabase.local (not printed)');
}

/* --------------------------------------------------------- 7. smoke test -- */
step('Smoke test through the live API');
{
  const rest = async (path, opts = {}, key = secretKey) => {
    const res = await fetch(projectUrl + '/rest/v1' + path, {
      ...opts,
      headers: {
        apikey: key, Authorization: 'Bearer ' + key,
        'Content-Type': 'application/json', Prefer: 'return=representation',
        ...(opts.headers || {})
      }
    });
    const text = await res.text();
    let body = null; try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    return { status: res.status, ok: res.ok, body };
  };

  // PostgREST can 503 briefly while it picks up a fresh schema.
  let probe = null;
  for (let i = 0; i < 12; i++) {
    probe = await rest('/organizations?select=id&limit=1');
    if (probe.ok) break;
    await sleep(5000);
  }
  if (!probe.ok) die('PostgREST is not serving public.organizations (' + probe.status + '): ' + JSON.stringify(probe.body).slice(0, 200));
  ok('PostgREST is serving the schema');

  const tag = 'provision_' + Date.now().toString(36);
  const org = await rest('/organizations', { method: 'POST', body: JSON.stringify({ name: tag }) });
  if (!org.ok || !org.body?.[0]?.id) die('Could not insert an organisation: ' + org.status + ' ' + JSON.stringify(org.body).slice(0, 200));
  const orgRow = org.body[0].id;

  const cand = await rest('/candidates', {
    method: 'POST',
    body: JSON.stringify({ organization_id: orgRow, full_name: 'Provision Check', email: tag + '@example.com' })
  });
  if (!cand.ok) die('Could not insert a candidate: ' + cand.status + ' ' + JSON.stringify(cand.body).slice(0, 200));
  ok('service key can read and write (org + candidate round-tripped)');

  // anon must see nothing: RLS is the only thing standing between tenants.
  const anonRead = await rest('/candidates?select=id&limit=1', {}, publishableKey);
  if (anonRead.ok && Array.isArray(anonRead.body) && anonRead.body.length > 0) {
    die('SECURITY: anon can read public.candidates. Stop and investigate before deploying.');
  }
  const anonWrite = await rest('/organizations', { method: 'POST', body: JSON.stringify({ name: 'anon-probe' }) }, publishableKey);
  if (anonWrite.ok) die('SECURITY: anon can insert into public.organizations. Stop and investigate before deploying.');
  ok('anon is locked out (read ' + anonRead.status + ' empty, write ' + anonWrite.status + ')');

  await runSql(`delete from public.candidates where organization_id = '${orgRow}';
                delete from public.organizations where id = '${orgRow}';`);
  ok('cleaned up after itself');
}

/* ------------------------------------------------------------- summary -- */
console.log('\n  Project ref:  ' + ref);
console.log('  URL:          ' + projectUrl);
console.log('  Credentials:  .env.supabase.local  (gitignored, never printed)');
console.log('\n  Your local .env files were left pointing at the local stack — that is deliberate.');
console.log('\n  Next:\n' +
  '    1. Render (backend): set SUPABASE_URL and SUPABASE_SECRET_KEY from\n' +
  '       .env.supabase.local, plus NVIDIA_API_KEY, RESEND_API_KEY, EMAIL_FROM,\n' +
  '       GOOGLE_*, FRONTEND_URL and CORS_ORIGINS. See render.yaml.\n' +
  '    2. Netlify (frontend): set VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY and\n' +
  '       VITE_API_URL to the Render backend URL.\n' +
  '    3. Point GOOGLE_REDIRECT_URI at the deployed backend and add it to the\n' +
  '       Google Cloud console, or calendar OAuth will fail.\n');
