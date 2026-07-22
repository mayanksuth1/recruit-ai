import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabaseConfigured = Boolean(url && anonKey)

// Fall back to a placeholder key so the UI still renders before configuration;
// auth calls will fail with a visible error until the real key is set.
export const supabase = createClient(
  url || 'http://localhost:54321',
  anonKey || 'anon-key-not-configured',
)
