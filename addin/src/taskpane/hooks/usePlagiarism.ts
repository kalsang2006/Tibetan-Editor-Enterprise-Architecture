/**
 * React hook for triggering plagiarism check requests and managing results.
 */

import { useCallback, useState } from 'react';
import { fetchPlagiarismCheck } from '../services/PlagiarismBridge';
import {
  DEFAULT_ANALYSIS_DAEMON_PORT,
  type PlagiarismCheckResult,
} from '../types/ipc';

export type PlagiarismStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface UsePlagiarismResult {
  result: PlagiarismCheckResult | null;
  status: PlagiarismStatus;
  error: string | null;
  check: () => Promise<void>;
  reset: () => void;
}

export function usePlagiarism(options: {
  getText: () => Promise<string>;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}): UsePlagiarismResult {
  const { getText } = options;
  const baseUrl = options.baseUrl ?? `http://127.0.0.1:${DEFAULT_ANALYSIS_DAEMON_PORT}`;
  const doFetch = options.fetchImpl;

  const [result, setResult] = useState<PlagiarismCheckResult | null>(null);
  const [status, setStatus] = useState<PlagiarismStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  const check = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const text = (await getText()).replace(/^\uFEFF/, '');
      if (!text.trim()) {
        setResult({
          originality_score: 100,
          matches: [],
          query_fingerprint_count: 0,
          total_corpus_documents: 0,
          elapsed_ms: 0,
        });
        setStatus('ready');
        return;
      }

      const res = await fetchPlagiarismCheck({
        baseUrl,
        text,
        ...(doFetch !== undefined ? { fetchImpl: doFetch } : {}),
      });

      setResult(res);
      setStatus('ready');
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [getText, baseUrl, doFetch]);

  const reset = useCallback(() => {
    setResult(null);
    setStatus('idle');
    setError(null);
  }, []);

  return { result, status, error, check, reset };
}
