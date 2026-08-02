import {
  AirGapViolationError,
  DONE_PAYLOAD,
  DaemonFaultError,
  type Channel,
  SseParser,
  assertLoopback,
  buildRequest,
  createChannelStreamTransport,
  createFetchStreamTransport,
  nextRequestId,
  parseFrame,
  resetRequestIds,
  unwrap,
} from '../src/taskpane/services/IpcBridge';
import { PROTOCOL_VERSION, type IpcRequest, type IpcResponse } from '../src/taskpane/types/ipc';

beforeEach(() => {
  resetRequestIds();
});

/**
 * Run `fn` and return what it threw.
 *
 * `expect()` calls lexically inside a `try/catch` in a test body are flagged by
 * `jest/no-conditional-expect`, because forgetting the "did not throw at all"
 * fallback is a common way for such a block to pass vacuously. Capturing the
 * thrown value here and asserting on it back in the test, outside any
 * try/catch, gets the same inspection without that footgun -- and the throw
 * below still fails the test loudly if `fn` did not throw.
 */
function captureThrown(fn: () => void): unknown {
  try {
    fn();
  } catch (error) {
    return error;
  }
  throw new Error('expected fn to throw, but it did not');
}

describe('request envelopes', () => {
  it('matches the daemon wire model and carries no jsonrpc member', () => {
    const request = buildRequest('ai.rewrite', { text: 'x' });

    expect(request).toEqual({
      protocol_version: PROTOCOL_VERSION,
      request_id: 'req-1',
      method: 'ai.rewrite',
      params: { text: 'x' },
      session_id: null,
      expects_response: true,
    });
    expect('jsonrpc' in request).toBe(false);
  });

  it('mints monotonic request ids', () => {
    expect(nextRequestId()).toBe('req-1');
    expect(nextRequestId()).toBe('req-2');
    expect(nextRequestId('cancel')).toBe('cancel-3');
  });

  it('carries the session and the command flag when given', () => {
    const request = buildRequest(
      'ai.summarize',
      {},
      { sessionId: 'sess-2', expectsResponse: false, requestId: 'fixed' },
    );

    expect(request.session_id).toBe('sess-2');
    expect(request.expects_response).toBe(false);
    expect(request.request_id).toBe('fixed');
  });
});

describe('unwrapping responses', () => {
  it('returns the result of a successful response', () => {
    expect(
      unwrap({
        protocol_version: '1.0',
        request_id: 'r',
        ok: true,
        result: { text: 'hello' },
      }),
    ).toEqual({ text: 'hello' });
  });

  it('returns an empty mapping when a success carries no result', () => {
    expect(unwrap({ protocol_version: '1.0', request_id: 'r', ok: true })).toEqual({});
  });

  it('raises the fault with its code', () => {
    expect(() =>
      unwrap({
        protocol_version: '1.0',
        request_id: 'r',
        ok: false,
        error: {
          code: 'TEEA-3005',
          error_type: 'InferenceError',
          message: 'generation failed',
          context: { model: 'qwen' },
        },
      }),
    ).toThrow(DaemonFaultError);
  });

  it('keeps the code and the context on the raised error', () => {
    const error = captureThrown(() =>
      unwrap({
        protocol_version: '1.0',
        request_id: 'r',
        ok: false,
        error: {
          code: 'TEEA-3004',
          error_type: 'ModelLoadError',
          message: 'no model',
          context: { searched: ['a'] },
        },
      }),
    );

    expect(error).toBeInstanceOf(DaemonFaultError);
    expect((error as DaemonFaultError).code).toBe('TEEA-3004');
    expect((error as DaemonFaultError).context).toEqual({ searched: ['a'] });
  });
});

describe('the air-gapped boundary', () => {
  it.each([
    'http://localhost:5000/api',
    'http://127.0.0.1:5000/api',
    'https://127.0.0.1:3000/x',
  ])('accepts the loopback endpoint %s', (endpoint) => {
    expect(() => assertLoopback(endpoint)).not.toThrow();
  });

  it.each([
    'https://huggingface.co/api',
    'http://192.168.1.20:5000/api',
    'https://example.com',
    'not a url',
  ])('refuses %s', (endpoint) => {
    expect(() => assertLoopback(endpoint)).toThrow(AirGapViolationError);
  });

  it('refuses to build a transport for a remote endpoint', () => {
    expect(() =>
      createFetchStreamTransport({ baseUrl: 'https://api.example.com' }),
    ).toThrow(AirGapViolationError);
  });

  it('says why it refused', () => {
    const error = captureThrown(() => assertLoopback('https://example.com'));

    expect((error as Error).message).toMatch(/runs offline/);
  });
});

describe('frame parsing', () => {
  it('parses a token frame', () => {
    expect(parseFrame('{"token": "hello"}')).toEqual({
      kind: 'token',
      token: 'hello',
    });
  });

  it('parses the literal terminator', () => {
    expect(parseFrame(DONE_PAYLOAD)).toEqual({ kind: 'done' });
    expect(DONE_PAYLOAD).toBe('[DONE]');
  });

  it('parses a cancellation frame', () => {
    expect(parseFrame('{"cancelled": true}')).toEqual({ kind: 'cancelled' });
  });

  it('parses an error frame', () => {
    expect(
      parseFrame('{"error": {"code": "TEEA-3005", "message": "boom"}}'),
    ).toEqual({ kind: 'error', code: 'TEEA-3005', message: 'boom' });
  });

  it('keeps a Tibetan token intact', () => {
    expect(parseFrame('{"token": "བཀྲ་ཤིས།"}')).toEqual({
      kind: 'token',
      token: 'བཀྲ་ཤིས།',
    });
  });

  it('keeps a token that is only whitespace', () => {
    expect(parseFrame('{"token": " "}')).toEqual({ kind: 'token', token: ' ' });
  });

  it('ignores an unparseable payload rather than throwing', () => {
    expect(parseFrame('{not json')).toBeNull();
    expect(parseFrame('')).toBeNull();
    expect(parseFrame('null')).toBeNull();
    expect(parseFrame('{"unknown": 1}')).toBeNull();
  });
});

describe('SseParser', () => {
  it('drains complete events', () => {
    const parser = new SseParser();

    const frames = parser.push('data: {"token": "a"}\n\ndata: [DONE]\n\n');

    expect(frames).toEqual([{ kind: 'token', token: 'a' }, { kind: 'done' }]);
  });

  it('buffers a frame split across two chunks', () => {
    const parser = new SseParser();

    expect(parser.push('data: {"tok')).toEqual([]);
    expect(parser.push('en": "split"}\n\n')).toEqual([
      { kind: 'token', token: 'split' },
    ]);
  });

  it('buffers an event whose terminator is split', () => {
    const parser = new SseParser();

    expect(parser.push('data: {"token": "x"}\n')).toEqual([]);
    expect(parser.push('\n')).toEqual([{ kind: 'token', token: 'x' }]);
  });

  it('does not lose a newline inside a token', () => {
    const parser = new SseParser();

    const frames = parser.push('data: {"token": "line1\\nline2"}\n\n');

    expect(frames).toEqual([{ kind: 'token', token: 'line1\nline2' }]);
  });

  it('exposes what is still buffered', () => {
    const parser = new SseParser();
    parser.push('data: partial');

    expect(parser.pending).toBe('data: partial');

    parser.reset();
    expect(parser.pending).toBe('');
  });

  it('ignores non-data lines', () => {
    const parser = new SseParser();

    expect(parser.push(': keep-alive\ndata: {"token": "a"}\n\n')).toEqual([
      { kind: 'token', token: 'a' },
    ]);
  });
});

describe('createFetchStreamTransport', () => {
  function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder();
    let index = 0;
    return new ReadableStream<Uint8Array>({
      pull(controller) {
        if (index >= chunks.length) {
          controller.close();
          return;
        }
        controller.enqueue(encoder.encode(chunks[index]!));
        index += 1;
      },
    });
  }

  it('delivers every frame from the response body', async () => {
    const fetchImpl = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: streamOf(['data: {"token": "a"}\n\n', 'data: [DONE]\n\n']),
    });
    const transport = createFetchStreamTransport({
      baseUrl: 'http://127.0.0.1:5000',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    const frames: unknown[] = [];

    await transport(
      buildRequest('ai.explain', { text: 'x' }),
      (frame) => frames.push(frame),
      new AbortController().signal,
    );

    expect(frames).toEqual([{ kind: 'token', token: 'a' }, { kind: 'done' }]);
  });

  it.each([
    ['ai.explain', '/api/ai/explain'],
    ['ai.summarize', '/api/ai/summarize'],
    ['ai.cancel', '/api/ai/cancel'],
  ])('routes %s to %s under the base URL', async (method, path) => {
    const fetchImpl = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: streamOf(['data: [DONE]\n\n']),
    });
    const transport = createFetchStreamTransport({
      baseUrl: 'http://127.0.0.1:5000',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await transport(buildRequest(method, {}), () => undefined, new AbortController().signal);

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(`http://127.0.0.1:5000${path}`);
  });

  it('refuses a method with no known endpoint', async () => {
    const transport = createFetchStreamTransport({ baseUrl: 'http://127.0.0.1:5000' });

    await expect(
      transport(
        buildRequest('document.analyze', {}),
        () => undefined,
        new AbortController().signal,
      ),
    ).rejects.toThrow(/no known http endpoint/i);
  });

  it('passes the abort signal through to fetch', async () => {
    const controller = new AbortController();
    const fetchImpl = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: streamOf(['data: [DONE]\n\n']),
    });
    const transport = createFetchStreamTransport({
      baseUrl: 'http://127.0.0.1:5000',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await transport(buildRequest('ai.explain', {}), () => undefined, controller.signal);

    expect(fetchImpl.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });

  it('raises a typed fault on a non-OK response', async () => {
    const fetchImpl = jest.fn().mockResolvedValue({ ok: false, status: 500, body: null });
    const transport = createFetchStreamTransport({
      baseUrl: 'http://127.0.0.1:5000',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(
      transport(buildRequest('ai.explain', {}), () => undefined, new AbortController().signal),
    ).rejects.toBeInstanceOf(DaemonFaultError);
  });

  it('reports an unreachable daemon with a clear, actionable message', async () => {
    const fetchImpl = jest.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const transport = createFetchStreamTransport({
      baseUrl: 'http://127.0.0.1:5000',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    const error = await transport(
      buildRequest('ai.explain', {}),
      () => undefined,
      new AbortController().signal,
    ).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(DaemonFaultError);
    expect((error as DaemonFaultError).code).toBe('TEEA-4007');
    expect((error as Error).message).toMatch(/could not reach.*daemon/i);
  });

  it('does not mask an abort as an unreachable daemon', async () => {
    const fetchImpl = jest.fn().mockImplementation(() => {
      const error = new DOMException('The operation was aborted', 'AbortError');
      return Promise.reject(error);
    });
    const transport = createFetchStreamTransport({
      baseUrl: 'http://127.0.0.1:5000',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    const error = await transport(
      buildRequest('ai.explain', {}),
      () => undefined,
      new AbortController().signal,
    ).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(DOMException);
    expect((error as DOMException).name).toBe('AbortError');
  });
});

describe('createChannelStreamTransport', () => {
  function fakeChannel(): { channel: Channel; notified: IpcRequest[] } {
    const notified: IpcRequest[] = [];
    const channel: Channel = {
      call: async (request) =>
        ({
          protocol_version: request.protocol_version,
          request_id: request.request_id,
          ok: true,
          result: {},
        }) satisfies IpcResponse,
      notify: async (request) => {
        notified.push(request);
      },
    };
    return { channel, notified };
  }

  it('delivers frames the host pushes in over the subscribed channel', async () => {
    const { channel } = fakeChannel();
    let deliver: ((chunk: string) => void) | null = null;
    const subscribe = jest.fn((_requestId: string, onChunk: (chunk: string) => void) => {
      deliver = onChunk;
      return jest.fn();
    });
    const transport = createChannelStreamTransport(channel, subscribe);
    const frames: unknown[] = [];

    const done = transport(
      buildRequest('ai.rewrite', { text: 'x' }),
      (frame) => frames.push(frame),
      new AbortController().signal,
    );
    deliver!('data: {"token": "a"}\n\ndata: [DONE]\n\n');
    await done;

    expect(frames).toEqual([{ kind: 'token', token: 'a' }, { kind: 'done' }]);
  });

  it('sends the request as a channel command', async () => {
    const { channel, notified } = fakeChannel();
    const subscribe = jest.fn((_requestId: string, onChunk: (chunk: string) => void) => {
      onChunk('data: [DONE]\n\n');
      return jest.fn();
    });
    const transport = createChannelStreamTransport(channel, subscribe);
    const request = buildRequest('ai.summarize', { text: 'x' });

    await transport(request, () => undefined, new AbortController().signal);

    expect(notified[0]).toBe(request);
  });

  it('unsubscribes once the stream reports done', async () => {
    const { channel } = fakeChannel();
    const unsubscribe = jest.fn();
    const subscribe = jest.fn((_requestId: string, onChunk: (chunk: string) => void) => {
      onChunk('data: [DONE]\n\n');
      return unsubscribe;
    });
    const transport = createChannelStreamTransport(channel, subscribe);

    await transport(buildRequest('ai.rewrite', {}), () => undefined, new AbortController().signal);

    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });

  it('rejects when the channel refuses the command', async () => {
    const channel: Channel = {
      call: async () => {
        throw new Error('should not be called');
      },
      notify: async () => {
        throw new Error('channel closed');
      },
    };
    const subscribe = jest.fn(() => jest.fn());
    const transport = createChannelStreamTransport(channel, subscribe);

    await expect(
      transport(buildRequest('ai.rewrite', {}), () => undefined, new AbortController().signal),
    ).rejects.toThrow('channel closed');
  });

  it('fires the configured cancel command on abort, carrying the same request_id', async () => {
    const { channel, notified } = fakeChannel();
    const unsubscribe = jest.fn();
    const subscribe = jest.fn(() => unsubscribe);
    const transport = createChannelStreamTransport(channel, subscribe, {
      cancelMethod: 'ai.cancel',
    });
    const controller = new AbortController();
    const request = buildRequest(
      'ai.rewrite',
      { text: 'x', request_id: 'ai-scoped-id' },
      { requestId: 'ai-scoped-id', sessionId: 'sess-1' },
    );

    const pending = transport(request, () => undefined, controller.signal);
    controller.abort();
    await pending;

    // The original rewrite call plus the cancel command it triggered.
    expect(notified).toHaveLength(2);
    expect(notified[1]).toMatchObject({
      method: 'ai.cancel',
      params: { request_id: 'ai-scoped-id' },
      session_id: 'sess-1',
      expects_response: false,
    });
  });

  it('does not fire a cancel command when none is configured', async () => {
    const { channel, notified } = fakeChannel();
    const subscribe = jest.fn(() => jest.fn());
    const transport = createChannelStreamTransport(channel, subscribe);
    const controller = new AbortController();

    const pending = transport(
      buildRequest('ai.rewrite', { text: 'x' }),
      () => undefined,
      controller.signal,
    );
    controller.abort();
    await pending;

    expect(notified).toHaveLength(1);
    expect(notified[0]?.method).toBe('ai.rewrite');
  });

  it('unsubscribes on abort so no further chunk is delivered', async () => {
    const { channel } = fakeChannel();
    const unsubscribe = jest.fn();
    const subscribe = jest.fn(() => unsubscribe);
    const transport = createChannelStreamTransport(channel, subscribe);
    const controller = new AbortController();

    const pending = transport(
      buildRequest('ai.rewrite', {}),
      () => undefined,
      controller.signal,
    );
    controller.abort();
    await pending;

    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });
});
