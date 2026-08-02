/**
 * Central configuration for Monlam AI Cloud API integration.
 *
 * The API key is intentionally NOT embedded in the client bundle at build
 * time (it would ship to every end user).  It is resolved at runtime from,
 * in order:
 *
 *   1. `config.json` next to the task pane bundle — a deployment-time file
 *      that is gitignored (see `config.example.json` for the shape);
 *   2. `process.env.REACT_APP_MONLAM_API_KEY` — dev-server convenience only;
 *      production webpack builds never inject it.
 *
 * All API key and base URL access for Monlam endpoints must use these
 * helpers.
 */

export const MONLAM_BASE_URL = 'https://api-v1.monlamai.studio';

let cachedKey: string | null = null;

/** Resolve the Monlam API key at runtime (never statically bundled). */
export async function getMonlamApiKey(): Promise<string> {
  if (cachedKey) {
    return cachedKey;
  }
  try {
    const response = await fetch('config.json', { cache: 'no-store' });
    if (response.ok) {
      const config: { monlamApiKey?: unknown } = await response.json();
      if (typeof config.monlamApiKey === 'string' && config.monlamApiKey) {
        cachedKey = config.monlamApiKey;
        return cachedKey;
      }
    }
  } catch {
    // config.json missing (e.g. dev server) — fall through to the env.
  }
  const fromEnv = process.env.REACT_APP_MONLAM_API_KEY;
  if (fromEnv && fromEnv !== 'REPLACE_WITH_YOUR_MONLAM_API_KEY') {
    cachedKey = fromEnv;
    return cachedKey;
  }
  return '';
}
