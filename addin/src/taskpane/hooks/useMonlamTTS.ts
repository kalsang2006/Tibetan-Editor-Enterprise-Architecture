/**
 * Custom React Hook for Monlam Tibetan Text-to-Speech API integration.
 * Supports both JSON audio_url response format and binary blob fallback.
 */

import * as React from 'react';

import { getMonlamApiKey, MONLAM_BASE_URL } from '../config';

const MONLAM_TTS_ENDPOINT = `${MONLAM_BASE_URL}/api/v1/text-to-speech/`;

export interface UseMonlamTTSOptions {
  apiKey?: string;
  baseUrl?: string;
}

export interface UseMonlamTTSResult {
  audioUrl: string | null;
  isLoading: boolean;
  error: string | null;
  generate: (text: string, voice: string) => Promise<void>;
  clear: () => void;
}

export function useMonlamTTS(options?: UseMonlamTTSOptions): UseMonlamTTSResult {
  const [audioUrl, setAudioUrl] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState<boolean>(false);
  const [error, setError] = React.useState<string | null>(null);

  const endpoint = options?.baseUrl || MONLAM_TTS_ENDPOINT;
  const configuredApiKey = options?.apiKey;

  const clear = React.useCallback(() => {
    if (audioUrl && audioUrl.startsWith('blob:')) {
      URL.revokeObjectURL(audioUrl);
    }
    setAudioUrl(null);
    setError(null);
  }, [audioUrl]);

  const generate = React.useCallback(
    async (text: string, voice: string) => {
      if (!text.trim()) {
        setError('Please enter Tibetan text to generate speech.');
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        const apiKey = configuredApiKey || (await getMonlamApiKey());
        if (!apiKey) {
          setTimeout(() => {
            setIsLoading(false);
          }, 800);
          return;
        }
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': apiKey,
          },
          body: JSON.stringify({
            text,
            voice_name: voice,
            model_name: 'monlamai-tts',
          }),
        });

        if (!response.ok) {
          throw new Error(`Monlam TTS API returned status ${response.status}`);
        }

        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const data = await response.json();
          const url = data?.audio_url || data?.url || data?.audioUrl;
          if (!url) {
            throw new Error(data?.message || 'Monlam TTS API returned no audio URL');
          }
          setAudioUrl((prev) => {
            if (prev && prev.startsWith('blob:')) {
              URL.revokeObjectURL(prev);
            }
            return url;
          });
        } else {
          // Binary audio blob fallback
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          setAudioUrl((prev) => {
            if (prev && prev.startsWith('blob:')) {
              URL.revokeObjectURL(prev);
            }
            return url;
          });
        }
      } catch (err) {
        console.warn('[Monlam TTS Hook] Endpoint error:', err);
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setIsLoading(false);
      }
    },
    [endpoint, configuredApiKey],
  );

  return {
    audioUrl,
    isLoading,
    error,
    generate,
    clear,
  };
}
