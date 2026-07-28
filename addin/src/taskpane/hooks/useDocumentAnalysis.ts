/**
 * Running the document-analysis pipeline and keeping the pane's suggestion
 * list in step with it.
 *
 * `status` distinguishes three ways this can fail to show suggestions, because
 * the pane must tell them apart in the UI: `'unavailable'` is "start the
 * daemon", `'error'` is "the daemon ran and rejected the request", and neither
 * is "there is nothing wrong with your document" -- which is what an empty
 * `suggestions` array under `status: 'ready'` means.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { fetchAnalysis } from '../services/AnalysisBridge';
import { toSuggestions } from '../services/suggestionAdapter';
import { DEFAULT_ANALYSIS_DAEMON_PORT, type Suggestion } from '../types/ipc';

/** Where the current analysis stands. */
export type AnalysisStatus = 'loading' | 'ready' | 'unavailable' | 'error';

export interface DocumentAnalysis {
  suggestions: readonly Suggestion[];
  status: AnalysisStatus;
  /** Set only when `status` is `'error'` or `'unavailable'`. */
  error: string | null;
  /** Re-read the document and re-run the pipeline over it. */
  refresh: () => void;
}

/**
 * Analyze `getText()`'s document on mount, and again whenever asked.
 *
 * @param options.getText Reads the text to analyze. Called fresh on every
 *   run, never cached here, so a refresh always sees the document as it is
 *   now.
 * @param options.baseUrl The daemon's origin. Defaults to the documented
 *   convention port on loopback.
 * @param options.fetchImpl `fetch` to use; overridable for tests.
 */
export function useDocumentAnalysis(options: {
  getText: () => Promise<string>;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}): DocumentAnalysis {
  const { getText } = options;
  const baseUrl = options.baseUrl ?? `http://127.0.0.1:${DEFAULT_ANALYSIS_DAEMON_PORT}`;
  const doFetch = options.fetchImpl ?? globalThis.fetch;

  const [suggestions, setSuggestions] = useState<readonly Suggestion[]>([]);
  const [status, setStatus] = useState<AnalysisStatus>('loading');
  const [error, setError] = useState<string | null>(null);

  // Guards against a slow, stale run overwriting a newer one's result, the
  // same pattern `useDaemonTransport` uses for its health check.
  const generation = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);

  const run = useCallback(() => {
    const attempt = (generation.current += 1);
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setStatus('loading');

    void (async () => {
      let text: string;
      try {
        text = await getText();
      } catch (caught) {
        if (attempt !== generation.current) {
          return;
        }
        setStatus('error');
        setError(caught instanceof Error ? caught.message : String(caught));
        return;
      }

      try {
        const raw = await fetchAnalysis({
          baseUrl,
          text,
          fetchImpl: doFetch,
          signal: controller.signal,
        });
        if (attempt !== generation.current) {
          return;
        }
        setSuggestions(toSuggestions(raw, text));
        setStatus('ready');
        setError(null);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === 'AbortError') {
          // Superseded by a newer run; that run owns reporting the outcome.
          return;
        }
        if (attempt !== generation.current) {
          return;
        }
        const message = caught instanceof Error ? caught.message : String(caught);
        const unreachable =
          typeof message === 'string' && message.includes('Could not reach');
        setStatus(unreachable ? 'unavailable' : 'error');
        setError(message);
      }
    })();
  }, [getText, baseUrl, doFetch]);

  useEffect(() => {
    run();
    return () => controllerRef.current?.abort();
    // `run` closes over the current `getText`/`baseUrl`/`doFetch`; re-running
    // on mount and whenever those actually change (via `run`'s own identity)
    // is the only automatic trigger. Everything after that is the user's own
    // "Refresh" action.
  }, [run]);

  return useMemo(
    () => ({ suggestions, status, error, refresh: run }),
    [suggestions, status, error, run],
  );
}
