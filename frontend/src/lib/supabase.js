import { createClient } from '@supabase/supabase-js'

/* Where Supabase lives depends on how the app is being served.
 *
 * In local development VITE_SUPABASE_URL points straight at the local stack
 * (127.0.0.1:54421) and the browser talks to it directly.
 *
 * In a self-hosted deployment there is no such luxury: this code runs in the
 * VISITOR's browser, and 127.0.0.1 there means their machine, not the server.
 * So the build leaves VITE_SUPABASE_URL empty and we fall back to the origin
 * the page was served from, where the backend reverse-proxies /supabase to the
 * local stack. Computing it at runtime rather than baking it in at build time
 * means the same bundle works no matter what hostname it ends up behind — which
 * matters when that hostname is a tunnel URL that changes on every restart.
 */
const url =
  import.meta.env.VITE_SUPABASE_URL ||
  (typeof window !== 'undefined' ? `${window.location.origin}/supabase` : '')

const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabaseConfigured = Boolean(url && anonKey)

// Fall back to a placeholder key so the UI still renders before configuration;
// auth calls will fail with a visible error until the real key is set.
export const supabase = createClient(
  url || 'http://localhost:54321',
  anonKey || 'anon-key-not-configured',
)
