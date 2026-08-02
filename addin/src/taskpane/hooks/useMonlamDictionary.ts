/**
 * Custom React Hook for Monlam Tibetan Dictionary Search API integration.
 */

import * as React from 'react';

import { getMonlamApiKey, MONLAM_BASE_URL } from '../config';

const MONLAM_DICT_ENDPOINT = `${MONLAM_BASE_URL}/api/v1/dictionary/search`;

export interface DictionaryEntry {
  id?: string;
  word?: string;
  definition?: string;
  pos?: string;
  explanation?: string;
  examples?: string[];
  pair?: string;
  raw?: unknown;
}

export interface UseMonlamDictionaryResult {
  entries: DictionaryEntry[];
  rawResponse: unknown;
  /** How many definitions the API reported (data.count), falling back to entries.length. */
  count: number;
  isLoading: boolean;
  error: string | null;
  search: (query: string, pair?: string) => Promise<void>;
  clear: () => void;
}

export function useMonlamDictionary(): UseMonlamDictionaryResult {
  const [entries, setEntries] = React.useState<DictionaryEntry[]>([]);
  const [rawResponse, setRawResponse] = React.useState<unknown>(null);
  const [count, setCount] = React.useState<number>(0);
  const [isLoading, setIsLoading] = React.useState<boolean>(false);
  const [error, setError] = React.useState<string | null>(null);

  const clear = React.useCallback(() => {
    setEntries([]);
    setRawResponse(null);
    setCount(0);
    setError(null);
  }, []);

  const search = React.useCallback(async (query: string, pair: string = 'bo-en') => {
    if (!query.trim()) {
      setError('Please enter a Tibetan word or phrase to look up.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const apiKey = await getMonlamApiKey();
      if (!apiKey) {
        setTimeout(() => {
          const mockResult = [
            {
              term: query.trim(),
              definition: `[Demo Mode] Definition for '${query.trim()}': Study; learning; acquisition of knowledge (སློབ་སྦྱོང་བྱེད་པ).`,
              pos: 'noun',
            },
          ];
          setEntries(mockResult as any);
          setCount(1);
          setIsLoading(false);
        }, 500);
        return;
      }
      const url = `${MONLAM_DICT_ENDPOINT}?pair=${encodeURIComponent(pair)}&q=${encodeURIComponent(
        query.trim(),
      )}`;

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'X-API-Key': apiKey,
        },
      });

      if (!response.ok) {
        setEntries([]);
        setCount(0);
        setRawResponse(null);
        setError(
          response.status === 404
            ? 'Word not found in the Monlam Dictionary.'
            : `Monlam Dictionary API returned error status ${response.status}.`,
        );
        return;
      }

      const data = await response.json();
      setRawResponse(data);

      // The API returns either a bare array, a single object, or the
      // documented `{ count, results }` envelope. A `count: 0` (or an empty
      // `results` list) means "no definition found", not an error.
      let items: unknown[] = [];
      let reportedCount: number | undefined;

      if (Array.isArray(data)) {
        items = data;
      } else if (data && typeof data === 'object') {
        const record = data as Record<string, unknown>;
        reportedCount = typeof record.count === 'number' ? record.count : undefined;
        if (Array.isArray(record.results)) {
          items = record.results;
        } else if (reportedCount !== 0) {
          items = [data];
        }
      }

      const parsedEntries: DictionaryEntry[] = [];

      for (const item of items) {
        if (!item || typeof item !== 'object') continue;
        const record = item as Record<string, unknown>;
        parsedEntries.push({
          word: (record.word as string) || (record.term as string) || query,
          definition:
            (record.definition as string) ||
            (record.meaning as string) ||
            (record.explanation as string) ||
            (record.def as string) ||
            (record.text as string) ||
            '',
          pos: (record.pos as string) || (record.part_of_speech as string) || (record.type as string) || '',
          explanation: (record.explanation as string) || (record.notes as string) || '',
          examples: Array.isArray(record.examples)
            ? (record.examples as string[])
            : record.example
            ? [record.example as string]
            : [],
          raw: item,
        });
      }

      setEntries(parsedEntries);
      setCount(reportedCount ?? parsedEntries.length);
    } catch (err) {
      console.warn('[Monlam Dictionary Hook] Search error:', err);
      setEntries([]);
      setCount(0);
      setError(
        'Could not reach the Monlam Dictionary service. Please check your connection and try again.',
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    entries,
    rawResponse,
    count,
    isLoading,
    error,
    search,
    clear,
  };
}
