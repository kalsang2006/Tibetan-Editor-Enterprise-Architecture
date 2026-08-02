/**
 * Monlam AI Studio Cloud Integration Hook with SSE Token Streaming & Melong Model (LLM Chat & Translation).
 */

import * as React from 'react';

import { MONLAM_API_KEY, MONLAM_BASE_URL } from '../config';

/**
 * Monlam AI Studio Chat endpoints.
 *
 * The sync endpoint returns the whole response in one JSON body; the stream
 * endpoint returns the same response as an SSE token stream. The hook tries
 * the stream endpoint first and falls back to the sync one when the daemon
 * does not expose streaming.
 */
export const MONLAM_CHAT_ENDPOINT = `${MONLAM_BASE_URL}/api/v1/ai/chat`;
export const MONLAM_CHAT_STREAM_ENDPOINT = `${MONLAM_BASE_URL}/api/v1/ai/chat/stream`;

/** The model Monlam AI Studio expects in the chat payload. */
export const MONLAM_CHAT_MODEL = 'melong';

export interface CloudAIMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface UseCloudAIResult {
  output: string;
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  generate: (prompt: string, systemPrompt?: string) => Promise<void>;
  stopGeneration: () => void;
  clear: () => void;
}

export function useCloudAI(): UseCloudAIResult {
  const [output, setOutput] = React.useState<string>('');
  const [isLoading, setIsLoading] = React.useState<boolean>(false);
  const [isStreaming, setIsStreaming] = React.useState<boolean>(false);
  const [error, setError] = React.useState<string | null>(null);

  const controllerRef = React.useRef<AbortController | null>(null);

  const stopGeneration = React.useCallback(() => {
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
    setIsStreaming(false);
    setIsLoading(false);
  }, []);

  const clear = React.useCallback(() => {
    stopGeneration();
    setOutput('');
    setError(null);
  }, [stopGeneration]);

  const generate = React.useCallback(
    async (promptText: string, systemPrompt?: string) => {
      if (!promptText.trim()) return;

      stopGeneration();
      const controller = new AbortController();
      controllerRef.current = controller;

      setIsLoading(true);
      setIsStreaming(true);
      setError(null);
      setOutput('');

      const messages: CloudAIMessage[] = [
        {
          role: 'system',
          content: systemPrompt || 'You are an expert Tibetan language writing and editing assistant.',
        },
        { role: 'user', content: promptText },
      ];

      if (!MONLAM_API_KEY) {
        setError(
          'Monlam Cloud AI is not configured. Add REACT_APP_MONLAM_API_KEY to ' +
            'addin/.env and restart the dev server.',
        );
        setIsLoading(false);
        setIsStreaming(false);
        return;
      }

      const requestPayload = {
        model_name: MONLAM_CHAT_MODEL,
        messages,
      };

      try {
        // Attempt SSE Streaming Endpoint first
        const response = await fetch(MONLAM_CHAT_STREAM_ENDPOINT, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': MONLAM_API_KEY,
          },
          body: JSON.stringify(requestPayload),
          signal: controller.signal,
        });

        if (!response.ok) {
          // If stream endpoint is unavailable, fallback to sync endpoint
          if (response.status === 404 || response.status === 405 || response.status === 403) {
            const syncResponse = await fetch(MONLAM_CHAT_ENDPOINT, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': MONLAM_API_KEY,
              },
              body: JSON.stringify(requestPayload),
              signal: controller.signal,
            });

            if (!syncResponse.ok) {
              throw new Error(
                `Monlam Cloud AI returned error status ${syncResponse.status}`,
              );
            }

            const data = await syncResponse.json();
            const resultText =
              data?.response ||
              data?.choices?.[0]?.message?.content ||
              data?.output ||
              data?.message?.content ||
              data?.text ||
              (typeof data === 'string' ? data : JSON.stringify(data));

            setOutput(resultText);
            return;
          }

          if (response.status === 401 || response.status === 402) {
            throw new Error(
              'Monlam Cloud AI rejected the API key (HTTP ' +
                `${response.status}). Check REACT_APP_MONLAM_API_KEY in addin/.env.`,
            );
          }

          throw new Error(
            `Monlam Cloud AI could not process the request (HTTP ${response.status}). ` +
              'Please try again.',
          );
        }

        if (!response.body) {
          throw new Error('Response body unavailable for streaming');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith(':')) continue;
            if (trimmed === 'data: [DONE]') break;

            if (trimmed.startsWith('data: ')) {
              const jsonStr = trimmed.slice(6);
              try {
                const parsed = JSON.parse(jsonStr);
                const token =
                  parsed?.response ||
                  parsed?.choices?.[0]?.delta?.content ||
                  parsed?.choices?.[0]?.text ||
                  parsed?.delta ||
                  parsed?.token ||
                  parsed?.text ||
                  '';
                if (token) {
                  setOutput((prev) => prev + token);
                }
              } catch {
                const token = jsonStr;
                if (token && token !== '[DONE]') {
                  setOutput((prev) => prev + token);
                }
              }
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          console.log('[Monlam Cloud AI] Generation aborted by user.');
          return;
        }
        console.warn('[Monlam Cloud AI] Streaming request error:', err);
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
        }
        setIsLoading(false);
        setIsStreaming(false);
      }
    },
    [stopGeneration],
  );

  return {
    output,
    isLoading,
    isStreaming,
    error,
    generate,
    stopGeneration,
    clear,
  };
}
