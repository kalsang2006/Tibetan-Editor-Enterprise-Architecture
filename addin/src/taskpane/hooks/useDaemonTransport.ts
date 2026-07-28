/**
 * Deciding whether the local daemon is reachable, and which transport to hand
 * `useAIAssistant` as a result.
 *
 * No daemon entry point exists yet in this repository -- composing one is a
 * separate decision (host, port and lifecycle conventions nobody has signed
 * off on; see `teea.transport.http_server.DEFAULT_PORT`'s own docstring for
 * why it stops at a documented convention rather than a launcher). So on an
 * ordinary run today, the health check below fails and `status` settles on
 * `'unavailable'` -- that is the *expected*, everyday outcome, not an edge
 * case, and it is exactly what {@link unavailableTransport} exists to degrade
 * into cleanly: one clear error frame instead of a hung request or an
 * unhandled rejection the moment the assistant tab is used.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createFetchStreamTransport, type StreamTransport } from '../services/IpcBridge';
import { DEFAULT_AI_DAEMON_PORT } from '../types/ipc';

/** Where the health check settled, or that it has not settled yet. */
export type DaemonConnectionStatus = 'checking' | 'connected' | 'unavailable';

/** How long to wait for `/health` before giving up on this attempt. */
export const HEALTH_CHECK_TIMEOUT_MS = 1500;

export interface DaemonConnection {
  /** Pass straight to `useAIAssistant({ transport })`. */
  transport: StreamTransport;
  status: DaemonConnectionStatus;
  /** The origin this hook checked, for display. */
  baseUrl: string;
  /** Re-run the health check, e.g. after the user starts the daemon. */
  retry: () => void;
}

/**
 * The transport used whenever the daemon is not confirmed reachable.
 *
 * A fixed, clear error frame rather than a network error surfacing from deep
 * inside `fetch`: a user who has not started the daemon yet should see one
 * sentence telling them so, the same way a missing model produces
 * `ModelNotFoundException`'s fixed message instead of a stack trace.
 */
export const unavailableTransport: StreamTransport = async (_request, onFrame) => {
  onFrame({
    kind: 'error',
    code: 'TEEA-4007',
    message:
      'The local TEEA daemon is not reachable. Start the daemon, then use ' +
      '"Retry connection".',
  });
  onFrame({ kind: 'done' });
};

/**
 * Check whether the daemon at `baseUrl` is reachable, and expose the right
 * transport for whatever the answer was.
 *
 * @param options.baseUrl The daemon's origin. Defaults to the documented
 *   convention port (`DEFAULT_AI_DAEMON_PORT`) on loopback.
 * @param options.fetchImpl `fetch` to use; overridable for tests.
 * @param options.timeoutMs How long one check waits before giving up.
 */
export function useDaemonTransport(
  options: {
    baseUrl?: string;
    fetchImpl?: typeof fetch;
    timeoutMs?: number;
  } = {},
): DaemonConnection {
  const baseUrl = options.baseUrl ?? `http://127.0.0.1:${DEFAULT_AI_DAEMON_PORT}`;
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  const timeoutMs = options.timeoutMs ?? HEALTH_CHECK_TIMEOUT_MS;

  const [status, setStatus] = useState<DaemonConnectionStatus>('checking');
  // Guards against a slow, stale check overwriting a newer one's result: each
  // call to `check` claims the next generation, and only the call still
  // holding the latest one is allowed to `setStatus`.
  const generation = useRef(0);

  const check = useCallback(() => {
    const attempt = (generation.current += 1);
    setStatus('checking');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    doFetch(`${baseUrl}/health`, { signal: controller.signal })
      .then((response) => {
        if (attempt === generation.current) {
          setStatus(response.ok ? 'connected' : 'unavailable');
        }
      })
      .catch(() => {
        if (attempt === generation.current) {
          setStatus('unavailable');
        }
      })
      .finally(() => clearTimeout(timer));
  }, [baseUrl, doFetch, timeoutMs]);

  useEffect(() => {
    check();
    // `check` is intentionally the only dependency: it already closes over
    // the current `baseUrl`/`doFetch`/`timeoutMs`, and re-running on mount
    // (and whenever those actually change, via `check`'s own identity) is the
    // only time an automatic check should fire -- everything after that is
    // the user's own "Retry connection" action, not a background poll.
  }, [check]);

  const transport = useMemo(
    () =>
      status === 'connected'
        ? createFetchStreamTransport({ baseUrl, fetchImpl: doFetch })
        : unavailableTransport,
    [status, baseUrl, doFetch],
  );

  return useMemo(
    () => ({ transport, status, baseUrl, retry: check }),
    [transport, status, baseUrl, check],
  );
}
