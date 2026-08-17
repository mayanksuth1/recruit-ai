// Regenerate setup-database.sql from supabase/migrations/.
//
// setup-database.sql is the single file a new owner pastes into the Supabase
// SQL Editor. It was previously maintained by hand and had silently fallen
// three migrations behind — 0007-0009 existed on disk but were in nobody's
// setup path, so Level 2 was never applied to any database. Generating it
// removes the chance of that happening again.
//
//   node scripts/build_setup_sql.mjs
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(ROOT, 'supabase', 'migrations');
const OUT = join(ROOT, 'setup-database.sql');

// 0000 is deliberately excluded: it grants the service key full DDL power over
// the database, it is documented as optional, and nothing in the app needs it.
const files = readdirSync(SRC)
  .filter((f) => f.endsWith('.sql') && !f.startsWith('0000'))
  .sort();

const header = `-- ============================================================
-- RECRUIT AI - DATABASE SETUP (run ONCE in the Supabase SQL Editor)
-- Paste this entire file and click RUN.
--
-- Covers phases 1-9, including the Level 2 async AI interviews, rubric
-- evidence checking and pgvector semantic search.
--
-- GENERATED FILE - do not edit by hand.
-- Source: supabase/migrations/*.sql
-- Rebuild: node scripts/build_setup_sql.mjs
-- ============================================================
`;

const body = files
  .map((f) => `\n-- ------------------ ${f} ------------------\n${readFileSync(join(SRC, f), 'utf8').trim()}\n`)
  .join('');

writeFileSync(OUT, header + body, 'utf8');

console.log(`setup-database.sql rebuilt from ${files.length} migrations:`);
for (const f of files) console.log(`  ${f}`);
console.log(`\n${(header + body).length} bytes written to ${OUT}`);
