/**
 * Calling the document-analysis HTTP bridge and unwrapping its result.
 *
 * Mirrors `teea.transport.analysis_server`: one composite call that runs the
 * daemon's `analyze` -> `plugins` -> `fuse` pipeline server-side and returns a
 * `teea.fusion.UnifiedSuggestions`, serialized. See that module's docstring
 * for why this is one endpoint rather than three round trips.
 */

import { assertLoopback, buildRequest, unwrap, DaemonFaultError } from './IpcBridge';
import {
  ANALYSIS_METHOD,
  ANALYSIS_PATH,
  type DaemonSuggestion,
  type IpcFault,
} from '../types/ipc';

/** The daemon's `UnifiedSuggestions`, as it crosses the boundary. */
export interface AnalysisResult {
  suggestions: DaemonSuggestion[];
}

/**
 * Run the analysis pipeline over `text` and return the raw suggestions.
 *
 * @param options.baseUrl The daemon's origin, e.g. `http://127.0.0.1:50505`.
 *   Must be loopback; see {@link assertLoopback}.
 * @param options.text The document text to analyze.
 * @param options.fetchImpl `fetch` to use; overridable for tests.
 * @param options.signal Aborts the request. A caller starting a fresh
 *   analysis while an earlier one is in flight is the ordinary case, not an
 *   error -- the pane always wants the latest document, never a queue of
 *   stale ones.
 * @returns The suggestions the fusion engine ranked, in daemon order.
 * @throws DaemonFaultError If the daemon is unreachable or reports a fault.
 */
export async function fetchAnalysis(options: {
  baseUrl: string;
  text: string;
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
}): Promise<DaemonSuggestion[]> {
  const base = assertLoopback(options.baseUrl);
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  const url = new URL(ANALYSIS_PATH, base);

  const request = buildRequest(ANALYSIS_METHOD, { text: options.text });

  const init: RequestInit = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  };
  if (options.signal !== undefined) {
    init.signal = options.signal;
  }

  let response: Response;
  try {
    response = await doFetch(url.toString(), init);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    throw new DaemonFaultError(
      'TEEA-4007',
      `Could not reach the local TEEA daemon at ${base.origin}. Start the ` +
        'daemon and try again.',
    );
  }

  if (!response.ok) {
    throw new DaemonFaultError(
      'TEEA-4003',
      `The daemon rejected the analysis request (HTTP ${response.status}).`,
    );
  }

  const body = (await response.json()) as {
    ok: boolean;
    request_id: string;
    result?: Record<string, unknown> | null;
    error?: IpcFault | null;
  };
  const result = unwrap({
    protocol_version: '1.0',
    request_id: body.request_id,
    ok: body.ok,
    result: body.result ?? null,
    error: body.error ?? null,
  });
  const suggestions = result.suggestions;
  return Array.isArray(suggestions) ? (suggestions as DaemonSuggestion[]) : [];
}
