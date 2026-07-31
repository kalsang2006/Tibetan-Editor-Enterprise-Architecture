/**
 * Calling the plagiarism check HTTP bridge and unwrapping its result.
 *
 * Communicates with `teea.transport.http_server` at `/api/plagiarism/check`.
 */

import { assertLoopback, buildRequest, unwrap, DaemonFaultError } from './IpcBridge';
import {
  PLAGIARISM_METHOD,
  PLAGIARISM_PATH,
  type IpcFault,
  type PlagiarismCheckResult,
} from '../types/ipc';

/**
 * Execute plagiarism detection over `text` and return the result payload.
 *
 * @param options.baseUrl The daemon's origin, e.g. `http://127.0.0.1:50505`.
 * @param options.text The document text to analyze for plagiarism.
 * @param options.threshold Minimum similarity score to report (0.0 to 1.0).
 * @param options.fetchImpl `fetch` to use; overridable for tests.
 * @param options.signal Aborts the request.
 * @returns The structured `PlagiarismCheckResult`.
 * @throws DaemonFaultError If the daemon is unreachable or reports a fault.
 */
export async function fetchPlagiarismCheck(options: {
  baseUrl: string;
  text: string;
  threshold?: number;
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
}): Promise<PlagiarismCheckResult> {
  const base = assertLoopback(options.baseUrl);
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  const url = new URL(PLAGIARISM_PATH, base);

  const request = buildRequest(PLAGIARISM_METHOD, {
    text: options.text,
    min_similarity: options.threshold ?? 0.05,
  });

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
      `The daemon rejected the plagiarism check request (HTTP ${response.status}).`,
    );
  }

  const body = (await response.json()) as {
    ok?: boolean;
    request_id?: string;
    result?: Record<string, unknown> | null;
    error?: IpcFault | null;
  };

  const result = unwrap({
    protocol_version: '1.0',
    request_id: body.request_id ?? 'req',
    ok: body.ok ?? false,
    result: body.result ?? null,
    error: body.error ?? null,
  });

  return {
    originality_score: Number(result.originality_score ?? 100),
    matches: Array.isArray(result.matches) ? (result.matches as PlagiarismCheckResult['matches']) : [],
    query_fingerprint_count: Number(result.query_fingerprint_count ?? 0),
    total_corpus_documents: Number(result.total_corpus_documents ?? 0),
    elapsed_ms: Number(result.elapsed_ms ?? 0),
  };
}
