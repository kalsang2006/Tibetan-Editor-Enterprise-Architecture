import { act, renderHook, waitFor } from '@testing-library/react';

import {
  HEALTH_CHECK_TIMEOUT_MS,
  unavailableTransport,
  useDaemonTransport,
} from '../src/taskpane/hooks/useDaemonTransport';
import { DEFAULT_AI_DAEMON_PORT } from '../src/taskpane/types/ipc';

describe('useDaemonTransport', () => {
  it('starts in the checking state', () => {
    const fetchImpl = jest.fn(() => new Promise<Response>(() => undefined));
    const { result } = renderHook(() => useDaemonTransport({ fetchImpl }));

    expect(result.current.status).toBe('checking');
    expect(result.current.transport).toBe(unavailableTransport);
  });

  it('reports connected once /health answers ok', async () => {
    const fetchImpl = jest.fn().mockResolvedValue({ ok: true, status: 200 });
    const { result } = renderHook(() => useDaemonTransport({ fetchImpl }));

    await waitFor(() => expect(result.current.status).toBe('connected'));

    expect(result.current.transport).not.toBe(unavailableTransport);
  });

  it('reports unavailable when /health answers with a non-OK status', async () => {
    const fetchImpl = jest.fn().mockResolvedValue({ ok: false, status: 503 });
    const { result } = renderHook(() => useDaemonTransport({ fetchImpl }));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));

    expect(result.current.transport).toBe(unavailableTransport);
  });

  it('reports unavailable when the fetch itself rejects', async () => {
    const fetchImpl = jest.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const { result } = renderHook(() => useDaemonTransport({ fetchImpl }));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
  });

  it('checks the health endpoint under the given base URL', async () => {
    const fetchImpl = jest.fn().mockResolvedValue({ ok: true, status: 200 });
    renderHook(() =>
      useDaemonTransport({ baseUrl: 'http://127.0.0.1:9999', fetchImpl }),
    );

    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());

    expect(fetchImpl.mock.calls[0]?.[0]).toBe('http://127.0.0.1:9999/health');
  });

  it('defaults to the documented convention port', () => {
    const fetchImpl = jest.fn(() => new Promise<Response>(() => undefined));
    const { result } = renderHook(() => useDaemonTransport({ fetchImpl }));

    expect(result.current.baseUrl).toBe(`http://127.0.0.1:${DEFAULT_AI_DAEMON_PORT}`);
  });

  it('exposes the same unavailableTransport instance the module exports', async () => {
    const fetchImpl = jest.fn().mockResolvedValue({ ok: false, status: 500 });
    const { result } = renderHook(() => useDaemonTransport({ fetchImpl }));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));

    const frames: unknown[] = [];
    await result.current.transport(
      { protocol_version: '1.0', request_id: 'r', method: 'ai.rewrite', params: {}, session_id: null, expects_response: false },
      (frame) => frames.push(frame),
      new AbortController().signal,
    );
    expect(frames[0]).toMatchObject({ kind: 'error', code: 'TEEA-4007' });
  });

  it('retry re-checks and can flip the status', async () => {
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    const { result } = renderHook(() => useDaemonTransport({ fetchImpl }));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.status).toBe('connected'));
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('ignores a slow first check that resolves after a later retry', async () => {
    let resolveFirst: ((value: { ok: boolean; status: number }) => void) | null = null;
    const fetchImpl = jest
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockResolvedValueOnce({ ok: true, status: 200 });
    const { result } = renderHook(() => useDaemonTransport({ fetchImpl }));

    expect(result.current.status).toBe('checking');
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe('connected'));

    // The stale first check now resolves as a failure; it must not override
    // the newer, successful attempt's result.
    act(() => resolveFirst?.({ ok: false, status: 500 }));
    await Promise.resolve();

    expect(result.current.status).toBe('connected');
  });

  it('names a real, positive timeout', () => {
    expect(HEALTH_CHECK_TIMEOUT_MS).toBeGreaterThan(0);
  });
});
