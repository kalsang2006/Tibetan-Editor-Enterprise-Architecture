/**
 * Driving one AI generation: start it, stream it, stop it.
 *
 * Streaming state is kept in a ref and flushed on an animation frame, not set
 * per token. A 15-tokens-per-second floor over a minute is nine hundred state
 * updates; re-rendering the pane nine hundred times is how a typewriter effect
 * becomes a stutter. The ref accumulates, the frame publishes, and only the text
 * node re-renders.
 *
 * Stopping is an `AbortController`. `stopGeneration` aborts it and the
 * transport tears down its read; what happens on the daemon side from there is
 * the transport's responsibility, not this hook's. The fetch transport relies
 * on the server noticing the closed connection and raising the cancellation
 * flag itself (`teea.ai.handlers` keys that flag by the same `request_id` sent
 * here, in `params`, not the IPC envelope's own id); the channel transport has
 * no socket to close, so it sends an explicit `ai.cancel` command on abort. An
 * abort is an outcome, not a fault: it updates the UI state and is never
 * surfaced as an error.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { buildRequest, nextRequestId, type StreamTransport } from '../services/IpcBridge';
import type { StreamFrame } from '../types/ipc';

/** Which operation is being asked for. */
export type AssistantAction = 'rewrite' | 'explain' | 'summarize';

/** Method name per action, matching `teea.ai.handlers.AI_ENDPOINT_METHODS`. */
export const ACTION_METHODS: Record<AssistantAction, string> = {
  rewrite: 'ai.rewrite',
  explain: 'ai.explain',
  summarize: 'ai.summarize',
};

/** The cancellation method. */
export const CANCEL_METHOD = 'ai.cancel';

/** Where a generation is in its lifecycle. */
export type AssistantStatus = 'idle' | 'streaming' | 'done' | 'cancelled' | 'error';

/** One generation request. */
export interface AssistantPrompt {
  action: AssistantAction;
  text: string;
  /** Which rewrite template; ignored by the other actions. */
  template?: string;
  posTags?: string;
  depTree?: string;
}

/** What the hook exposes. */
export interface AIAssistant {
  /** Everything generated so far. */
  output: string;
  status: AssistantStatus;
  /** The last failure, or `null`. An abort never sets this. */
  error: { code: string; message: string } | null;
  isStreaming: boolean;
  /** Start a generation, replacing whatever was there. */
  generate: (prompt: AssistantPrompt) => Promise<void>;
  /** Re-run the last prompt from scratch. */
  regenerate: () => Promise<void>;
  /** Stop the current generation. Safe to call when idle. */
  stopGeneration: () => void;
  /** Discard the output and return to idle. */
  clear: () => void;
  /** The prompt that produced the current output, or `null`. */
  lastPrompt: AssistantPrompt | null;
}

/** Schedules the flush. Injected so tests need no animation frames. */
export type FrameScheduler = (callback: () => void) => number;

/**
 * Drive the local assistant.
 *
 * @param options.transport How a request becomes a token stream.
 * @param options.sessionId The IPC session, when one has been established.
 * @param options.schedule Frame scheduler. Defaults to `requestAnimationFrame`.
 */
export function useAIAssistant(options: {
  transport: StreamTransport;
  sessionId?: string | null;
  schedule?: FrameScheduler;
}): AIAssistant {
  const { transport, sessionId = null } = options;
  const schedule = options.schedule ?? defaultScheduler;

  const [output, setOutput] = useState('');
  const [status, setStatus] = useState<AssistantStatus>('idle');
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [lastPrompt, setLastPrompt] = useState<AssistantPrompt | null>(null);

  const bufferRef = useRef('');
  const flushPendingRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(
    () => () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    },
    [],
  );

  const flush = useCallback(() => {
    flushPendingRef.current = false;
    if (mountedRef.current) {
      setOutput(bufferRef.current);
    }
  }, []);

  const enqueue = useCallback(
    (token: string) => {
      bufferRef.current += token;
      if (!flushPendingRef.current) {
        flushPendingRef.current = true;
        schedule(flush);
      }
    },
    [schedule, flush],
  );

  const stopGeneration = useCallback(() => {
    const controller = controllerRef.current;
    if (controller === null) {
      return;
    }
    controllerRef.current = null;
    controller.abort();
    flush();
    if (mountedRef.current) {
      setStatus('cancelled');
    }
  }, [flush]);

  const generate = useCallback(
    async (prompt: AssistantPrompt) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      bufferRef.current = '';
      flushPendingRef.current = false;
      setOutput('');
      setError(null);
      setStatus('streaming');
      setLastPrompt(prompt);

      // Minted once and carried in both the envelope and `params`: the daemon
      // handler reads `params.request_id` (application-level, session-scoped),
      // not the envelope's own id, because `RequestHandler.handle` never sees
      // the envelope. Using one value for both keeps a request and its own
      // cancellation unambiguous even when the pane fires two calls back to
      // back in the same session.
      const requestId = nextRequestId('ai');
      const request = buildRequest(
        ACTION_METHODS[prompt.action],
        { ...paramsFor(prompt), request_id: requestId },
        { sessionId, expectsResponse: prompt.action === 'explain', requestId },
      );

      let terminal: AssistantStatus = 'done';
      let fault: { code: string; message: string } | null = null;

      const onFrame = (frame: StreamFrame): void => {
        switch (frame.kind) {
          case 'token':
            enqueue(frame.token);
            break;
          case 'cancelled':
            terminal = 'cancelled';
            break;
          case 'error':
            terminal = 'error';
            fault = { code: frame.code, message: frame.message };
            break;
          case 'done':
            break;
        }
      };

      try {
        await transport(request, onFrame, controller.signal);
      } catch (caught) {
        if (isAbort(caught)) {
          // The user pressed stop. `stopGeneration` has already set the state,
          // and reporting an abort as a failure would put a red banner on a
          // deliberate action.
          flush();
          return;
        }
        terminal = 'error';
        fault = {
          code: 'TEEA-3005',
          message: caught instanceof Error ? caught.message : String(caught),
        };
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
        }
      }

      flush();
      if (!mountedRef.current) {
        return;
      }
      setError(fault);
      setStatus(terminal);
    },
    [transport, sessionId, enqueue, flush],
  );

  const regenerate = useCallback(async () => {
    if (lastPrompt === null) {
      return;
    }
    await generate(lastPrompt);
  }, [generate, lastPrompt]);

  const clear = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    bufferRef.current = '';
    flushPendingRef.current = false;
    setOutput('');
    setError(null);
    setStatus('idle');
    setLastPrompt(null);
  }, []);

  return useMemo(
    () => ({
      output,
      status,
      error,
      isStreaming: status === 'streaming',
      generate,
      regenerate,
      stopGeneration,
      clear,
      lastPrompt,
    }),
    [output, status, error, generate, regenerate, stopGeneration, clear, lastPrompt],
  );
}

function paramsFor(prompt: AssistantPrompt): Record<string, unknown> {
  const params: Record<string, unknown> = { text: prompt.text };
  if (prompt.action === 'rewrite' && prompt.template !== undefined) {
    params.template = prompt.template;
  }
  if (prompt.posTags !== undefined) {
    params.pos_tags = prompt.posTags;
  }
  if (prompt.depTree !== undefined) {
    params.dep_tree = prompt.depTree;
  }
  return params;
}

function isAbort(error: unknown): boolean {
  if (error instanceof DOMException) {
    return error.name === 'AbortError';
  }
  return error instanceof Error && error.name === 'AbortError';
}

const defaultScheduler: FrameScheduler = (callback) => {
  if (typeof requestAnimationFrame === 'function') {
    return requestAnimationFrame(() => callback());
  }
  return setTimeout(callback, 16) as unknown as number;
};
