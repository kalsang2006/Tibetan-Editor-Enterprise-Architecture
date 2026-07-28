/**
 * Building daemon requests and parsing the token stream that comes back.
 *
 * The request shapes here are the daemon's, not JSON-RPC: see `types/ipc.ts`.
 * Nothing in this module chooses a transport. The daemon composes an `IpcServer`
 * over an injected `Transport` and ships no socket (ADR-020), so the concrete
 * channel is supplied by the host and passed in.
 *
 * The air-gapped boundary is enforced, not assumed
 * ------------------------------------------------
 * {@link assertLoopback} rejects any endpoint that is not the local machine, and
 * it throws rather than warning. A writing assistant that silently posted a
 * user's unpublished manuscript to a remote host would be the single worst
 * failure this product could have, so the check is a hard stop at the one place
 * a URL can enter the system.
 */

import {
  AI_METHOD_PATHS,
  PROTOCOL_VERSION,
  type IpcRequest,
  type IpcResponse,
  type StreamFrame,
} from '../types/ipc';

/** Hostnames that are unambiguously this machine. */
const LOOPBACK_HOSTS = new Set([
  'localhost',
  '127.0.0.1',
  '[::1]',
  '::1',
  '0.0.0.0',
]);

/** The SSE line prefix the daemon emits. */
const DATA_PREFIX = 'data: ';

/** The literal terminator the daemon closes every stream with. */
export const DONE_PAYLOAD = '[DONE]';

/** Raised when an endpoint would leave the machine. */
export class AirGapViolationError extends Error {
  constructor(readonly endpoint: string) {
    super(
      `Refusing to contact ${endpoint}: TEEA runs offline and may only talk to ` +
        'the local daemon.',
    );
    this.name = 'AirGapViolationError';
  }
}

/** Raised when the daemon answers with a fault. */
export class DaemonFaultError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly context: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'DaemonFaultError';
  }
}

/** Anything that can carry one request to the daemon and bring a reply back. */
export interface Channel {
  /** Send a query and await its response. */
  call(request: IpcRequest): Promise<IpcResponse>;
  /** Send a command. Returns once the command has been handed off. */
  notify(request: IpcRequest): Promise<void>;
}

/** Drives one token stream. Resolves when the stream is closed. */
export type StreamTransport = (
  request: IpcRequest,
  onFrame: (frame: StreamFrame) => void,
  signal: AbortSignal,
) => Promise<void>;

let requestCounter = 0;

/** Mint a request id unique within this pane session. */
export function nextRequestId(prefix = 'req'): string {
  requestCounter += 1;
  return `${prefix}-${requestCounter}`;
}

/** Reset the id counter. Test-only; production ids are monotonic for a session. */
export function resetRequestIds(): void {
  requestCounter = 0;
}

/**
 * Build a request in the daemon's own envelope.
 *
 * @param method The routed method name.
 * @param params The call's arguments.
 * @param options Session, id and whether a reply is awaited.
 */
export function buildRequest(
  method: string,
  params: Record<string, unknown>,
  options: {
    sessionId?: string | null;
    requestId?: string;
    expectsResponse?: boolean;
  } = {},
): IpcRequest {
  return {
    protocol_version: PROTOCOL_VERSION,
    request_id: options.requestId ?? nextRequestId(),
    method,
    params,
    session_id: options.sessionId ?? null,
    expects_response: options.expectsResponse ?? true,
  };
}

/**
 * Unwrap a response, raising the daemon's fault as a typed error.
 *
 * @param response What came back.
 * @returns The result mapping.
 * @throws DaemonFaultError When the response reports failure.
 */
export function unwrap(response: IpcResponse): Record<string, unknown> {
  if (response.ok) {
    return response.result ?? {};
  }
  const fault = response.error;
  throw new DaemonFaultError(
    fault?.code ?? 'TEEA-0000',
    fault?.message ?? 'The daemon reported an unspecified failure.',
    fault?.context ?? {},
  );
}

/**
 * Reject any endpoint that is not on this machine.
 *
 * @param endpoint The URL a transport was asked to contact.
 * @throws AirGapViolationError When the host is not loopback.
 */
export function assertLoopback(endpoint: string): URL {
  let url: URL;
  try {
    url = new URL(endpoint);
  } catch {
    throw new AirGapViolationError(endpoint);
  }
  if (!LOOPBACK_HOSTS.has(url.hostname)) {
    throw new AirGapViolationError(endpoint);
  }
  return url;
}

/**
 * Parse one SSE `data:` payload into a frame.
 *
 * @param payload The text after `data: `.
 * @returns The frame, or `null` for a payload that carries nothing useful.
 */
export function parseFrame(payload: string): StreamFrame | null {
  const trimmed = payload.trim();
  if (trimmed.length === 0) {
    return null;
  }
  if (trimmed === DONE_PAYLOAD) {
    return { kind: 'done' };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return null;
  }
  if (typeof parsed !== 'object' || parsed === null) {
    return null;
  }
  const record = parsed as Record<string, unknown>;
  if (typeof record.token === 'string') {
    return { kind: 'token', token: record.token };
  }
  if (record.cancelled === true) {
    return { kind: 'cancelled' };
  }
  const error = record.error;
  if (typeof error === 'object' && error !== null) {
    const detail = error as Record<string, unknown>;
    return {
      kind: 'error',
      code: typeof detail.code === 'string' ? detail.code : 'TEEA-0000',
      message:
        typeof detail.message === 'string'
          ? detail.message
          : 'The daemon reported an unspecified failure.',
    };
  }
  return null;
}

/**
 * Incremental SSE reader.
 *
 * A network read boundary falls wherever it likes, including halfway through a
 * multi-byte Tibetan codepoint's escape or between an event's two closing
 * newlines. Buffering until a complete `\n\n` is the only way a token is not
 * silently split into two.
 */
export class SseParser {
  private buffer = '';

  /**
   * Feed a chunk and drain every complete frame it produced.
   *
   * @param chunk Whatever arrived.
   * @returns The frames now complete, in order.
   */
  push(chunk: string): StreamFrame[] {
    this.buffer += chunk;
    const frames: StreamFrame[] = [];
    let boundary = this.buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const event = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      for (const line of event.split('\n')) {
        if (line.startsWith(DATA_PREFIX)) {
          const frame = parseFrame(line.slice(DATA_PREFIX.length));
          if (frame !== null) {
            frames.push(frame);
          }
        }
      }
      boundary = this.buffer.indexOf('\n\n');
    }
    return frames;
  }

  /** Whatever is buffered but not yet a complete event. */
  get pending(): string {
    return this.buffer;
  }

  /** Discard the buffer. Called when a stream is abandoned. */
  reset(): void {
    this.buffer = '';
  }
}

/**
 * A stream transport over `fetch`, talking to `teea.transport.http_server`'s
 * loopback bridge.
 *
 * `baseUrl` is checked before the first byte is sent (`assertLoopback`), and
 * each request's own path is resolved from its `method` via
 * {@link AI_METHOD_PATHS} -- the server routes `/api/ai/rewrite`,
 * `/api/ai/explain`, `/api/ai/summarize` and `/api/ai/cancel` to four different
 * handlers, so one fixed endpoint URL cannot serve every call the way a single
 * generic POST target could for a simpler API. The `AbortSignal` is passed
 * straight through so `stopGeneration` closes the real HTTP connection: the
 * server-side emitter notices the failed write and self-cancels (see
 * `teea.ai.handlers._AiHandler._stream` and `AiHttpServer`'s own docstring) --
 * no separate `ai.cancel` call is needed on this path, unlike
 * {@link createChannelStreamTransport}, which has no connection to close.
 *
 * @param options.baseUrl The daemon's origin, e.g. `http://127.0.0.1:50505`.
 *   Must be loopback.
 * @param options.fetchImpl `fetch` to use; overridable for tests.
 * @returns A transport usable by `useAIAssistant`.
 */
export function createFetchStreamTransport(options: {
  baseUrl: string;
  fetchImpl?: typeof fetch;
}): StreamTransport {
  const base = assertLoopback(options.baseUrl);
  const doFetch = options.fetchImpl ?? globalThis.fetch;

  return async (request, onFrame, signal) => {
    const path = AI_METHOD_PATHS[request.method];
    if (path === undefined) {
      throw new DaemonFaultError(
        'TEEA-4001',
        `No known HTTP endpoint for method "${request.method}".`,
      );
    }
    const url = new URL(path, base);

    let response: Response;
    try {
      response = await doFetch(url.toString(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(request),
        signal,
      });
    } catch (error) {
      // An abort is a deliberate stop, not a connectivity failure; let the
      // caller's own abort handling see it unchanged rather than reporting it
      // as "daemon unreachable".
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
        `The daemon rejected the request (HTTP ${response.status}).`,
      );
    }
    const body = response.body;
    if (body === null) {
      throw new DaemonFaultError('TEEA-4002', 'The daemon returned no stream.');
    }

    const reader = body.getReader();
    const decoder = new TextDecoder('utf-8');
    const parser = new SseParser();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
          onFrame(frame);
          if (frame.kind === 'done') {
            return;
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  };
}

/**
 * A stream transport over an injected {@link Channel}.
 *
 * For an embedding where the pane and daemon share a process (no socket, no
 * HTTP), the SSE frames the handlers emit arrive as command payloads on the
 * existing bus and are parsed with the same {@link SseParser}. See
 * {@link createFetchStreamTransport} for the loopback-HTTP path a real Word
 * add-in uses.
 *
 * Cancellation has no connection to close here, unlike the fetch transport:
 * aborting only tears down this function's own promise, so a caller that wants
 * `stopGeneration` to actually interrupt the daemon-side generation must pass
 * `cancelMethod`, which is fired as a command carrying the same `request_id`
 * before the promise resolves.
 *
 * @param channel Where to send the request.
 * @param subscribe How the host delivers emitted frames back to the pane.
 * @param options.cancelMethod The command to fire on abort, e.g. `ai.cancel`.
 *   Omit only if the channel's handlers ignore cancellation entirely.
 * @returns A transport usable by `useAIAssistant`.
 */
export function createChannelStreamTransport(
  channel: Channel,
  subscribe: (
    requestId: string,
    onChunk: (chunk: string) => void,
  ) => () => void,
  options: { cancelMethod?: string } = {},
): StreamTransport {
  return async (request, onFrame, signal) => {
    const parser = new SseParser();
    await new Promise<void>((resolve, reject) => {
      // `subscribe`'s contract only promises a callback and a teardown
      // function; nothing says the callback cannot fire *before* `subscribe`
      // has returned that teardown function (a channel that replays a
      // buffered last value synchronously would do exactly this). Calling the
      // still-unassigned `unsubscribe` in that window would throw, or -- if
      // hoisted with a placeholder -- silently invoke the wrong function. A
      // pending flag defers the call until the real teardown exists.
      let unsubscribe: (() => void) | null = null;
      let unsubscribePending = false;
      const requestUnsubscribe = (): void => {
        if (unsubscribe !== null) {
          unsubscribe();
        } else {
          unsubscribePending = true;
        }
      };

      unsubscribe = subscribe(request.request_id, (chunk) => {
        for (const frame of parser.push(chunk)) {
          onFrame(frame);
          if (frame.kind === 'done') {
            requestUnsubscribe();
            resolve();
          }
        }
      });
      if (unsubscribePending) {
        unsubscribe();
      }

      const onAbort = (): void => {
        requestUnsubscribe();
        parser.reset();
        if (options.cancelMethod !== undefined) {
          const requestId =
            typeof request.params.request_id === 'string'
              ? request.params.request_id
              : request.request_id;
          void channel.notify(
            buildRequest(
              options.cancelMethod,
              { request_id: requestId },
              { sessionId: request.session_id, expectsResponse: false },
            ),
          );
        }
        resolve();
      };
      signal.addEventListener('abort', onAbort, { once: true });

      channel.notify(request).catch((error: unknown) => {
        requestUnsubscribe();
        reject(error instanceof Error ? error : new Error(String(error)));
      });
    });
  };
}
