import { act, renderHook, waitFor } from '@testing-library/react';

import {
  ACTION_METHODS,
  useAIAssistant,
} from '../src/taskpane/hooks/useAIAssistant';
import type { StreamTransport } from '../src/taskpane/services/IpcBridge';
import type { IpcRequest, StreamFrame } from '../src/taskpane/types/ipc';

/** A transport that emits scripted frames, synchronously. */
function scripted(frames: StreamFrame[]): {
  transport: StreamTransport;
  requests: IpcRequest[];
} {
  const requests: IpcRequest[] = [];
  return {
    requests,
    transport: async (request, onFrame) => {
      requests.push(request);
      for (const frame of frames) {
        onFrame(frame);
      }
    },
  };
}

/** A transport that never finishes until aborted. */
function hanging(): {
  transport: StreamTransport;
  emit: (frame: StreamFrame) => void;
  aborted: () => boolean;
} {
  let sink: ((frame: StreamFrame) => void) | null = null;
  let wasAborted = false;
  return {
    aborted: () => wasAborted,
    emit: (frame) => sink?.(frame),
    transport: (_request, onFrame, signal) =>
      new Promise<void>((_resolve, reject) => {
        sink = onFrame;
        signal.addEventListener('abort', () => {
          wasAborted = true;
          const error = new Error('aborted');
          error.name = 'AbortError';
          reject(error);
        });
      }),
  };
}

/** Flush the microtask-backed animation frame the setup installs. */
const flush = async (): Promise<void> => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};

describe('useAIAssistant streaming', () => {
  it('starts idle', () => {
    const { result } = renderHook(() =>
      useAIAssistant({ transport: scripted([]).transport }),
    );

    expect(result.current.status).toBe('idle');
    expect(result.current.output).toBe('');
    expect(result.current.isStreaming).toBe(false);
  });

  it('accumulates tokens into the output', async () => {
    const { transport } = scripted([
      { kind: 'token', token: 'Tashi' },
      { kind: 'token', token: ' delek' },
      { kind: 'done' },
    ]);
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'draft' });
    });

    await waitFor(() => expect(result.current.output).toBe('Tashi delek'));
    expect(result.current.status).toBe('done');
  });

  it('batches tokens onto one frame rather than one state update each', async () => {
    const scheduled: Array<() => void> = [];
    const schedule = (callback: () => void): number => {
      scheduled.push(callback);
      return scheduled.length;
    };
    const { transport } = scripted([
      { kind: 'token', token: 'a' },
      { kind: 'token', token: 'b' },
      { kind: 'token', token: 'c' },
      { kind: 'done' },
    ]);
    const { result } = renderHook(() => useAIAssistant({ transport, schedule }));

    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'draft' });
    });

    // Three tokens, one scheduled flush.
    expect(scheduled).toHaveLength(1);
    expect(result.current.output).toBe('abc');
  });

  it('sends the method the action names', async () => {
    const { transport, requests } = scripted([{ kind: 'done' }]);
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.generate({ action: 'summarize', text: 'doc' });
    });

    expect(requests[0]?.method).toBe(ACTION_METHODS.summarize);
    // `params.request_id` must agree with the envelope's own id: it is what
    // the daemon handler actually keys cancellation by, since a `RequestHandler`
    // never sees the envelope, only `params`.
    expect(requests[0]?.params).toEqual({
      text: 'doc',
      request_id: requests[0]?.request_id,
    });
  });

  it('sends the rewrite template when one is chosen', async () => {
    const { transport, requests } = scripted([{ kind: 'done' }]);
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.generate({
        action: 'rewrite',
        text: 'doc',
        template: 'tone_formal',
      });
    });

    expect(requests[0]?.params).toEqual({
      text: 'doc',
      template: 'tone_formal',
      request_id: requests[0]?.request_id,
    });
  });

  it('forwards the analysis context when supplied', async () => {
    const { transport, requests } = scripted([{ kind: 'done' }]);
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.generate({
        action: 'explain',
        text: 'doc',
        posTags: 'n v',
        depTree: 'root(0)',
      });
    });

    expect(requests[0]?.params).toEqual({
      text: 'doc',
      pos_tags: 'n v',
      dep_tree: 'root(0)',
      request_id: requests[0]?.request_id,
    });
  });

  it('carries the session id and the daemon protocol version', async () => {
    const { transport, requests } = scripted([{ kind: 'done' }]);
    const { result } = renderHook(() =>
      useAIAssistant({ transport, sessionId: 'sess-7' }),
    );

    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'x' });
    });

    expect(requests[0]?.session_id).toBe('sess-7');
    expect(requests[0]?.protocol_version).toBe('1.0');
    // A streaming action is a command: the caller consumes frames, it does not
    // block on one reply.
    expect(requests[0]?.expects_response).toBe(false);
  });

  it('treats explain as a query', async () => {
    const { transport, requests } = scripted([{ kind: 'done' }]);
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.generate({ action: 'explain', text: 'x' });
    });

    expect(requests[0]?.expects_response).toBe(true);
  });
});

describe('useAIAssistant cancellation', () => {
  it('aborts the transport when stopGeneration is called', async () => {
    const { transport, aborted } = hanging();
    const { result } = renderHook(() => useAIAssistant({ transport }));

    act(() => {
      void result.current.generate({ action: 'rewrite', text: 'draft' });
    });
    await flush();
    act(() => result.current.stopGeneration());
    await flush();

    expect(aborted()).toBe(true);
    expect(result.current.status).toBe('cancelled');
  });

  it('does not surface an abort as an error', async () => {
    const { transport } = hanging();
    const { result } = renderHook(() => useAIAssistant({ transport }));

    act(() => {
      void result.current.generate({ action: 'rewrite', text: 'draft' });
    });
    await flush();
    act(() => result.current.stopGeneration());
    await flush();

    expect(result.current.error).toBeNull();
  });

  it('keeps the partial output after a stop', async () => {
    const { transport, emit } = hanging();
    const { result } = renderHook(() => useAIAssistant({ transport }));

    act(() => {
      void result.current.generate({ action: 'rewrite', text: 'draft' });
    });
    act(() => emit({ kind: 'token', token: 'partial' }));
    await flush();
    act(() => result.current.stopGeneration());
    await flush();

    expect(result.current.output).toBe('partial');
  });

  it('stopping when idle is harmless', () => {
    const { result } = renderHook(() =>
      useAIAssistant({ transport: scripted([]).transport }),
    );

    act(() => result.current.stopGeneration());

    expect(result.current.status).toBe('idle');
  });

  it('records a cancellation frame from the daemon', async () => {
    const { transport } = scripted([
      { kind: 'token', token: 'half' },
      { kind: 'cancelled' },
      { kind: 'done' },
    ]);
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'draft' });
    });

    expect(result.current.status).toBe('cancelled');
    expect(result.current.output).toBe('half');
  });
});

describe('useAIAssistant failure and lifecycle', () => {
  it('surfaces an error frame with its code', async () => {
    const { transport } = scripted([
      { kind: 'error', code: 'TEEA-3004', message: 'no model' },
      { kind: 'done' },
    ]);
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'draft' });
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toEqual({ code: 'TEEA-3004', message: 'no model' });
  });

  it('surfaces a thrown transport failure', async () => {
    const transport: StreamTransport = async () => {
      throw new Error('channel closed');
    };
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'draft' });
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error?.message).toBe('channel closed');
  });

  it('regenerate replays the last prompt', async () => {
    const { transport, requests } = scripted([
      { kind: 'token', token: 'x' },
      { kind: 'done' },
    ]);
    const { result } = renderHook(() => useAIAssistant({ transport }));
    await act(async () => {
      await result.current.generate({
        action: 'rewrite',
        text: 'draft',
        template: 'improve_clarity',
      });
    });

    await act(async () => {
      await result.current.regenerate();
    });

    expect(requests).toHaveLength(2);
    // A regenerate is a new request and earns its own id; everything else
    // about the prompt is replayed unchanged.
    expect(requests[1]?.params).toEqual({
      ...requests[0]?.params,
      request_id: requests[1]?.params?.request_id,
    });
    expect(requests[1]?.request_id).not.toBe(requests[0]?.request_id);
    expect(requests[1]?.params?.request_id).not.toBe(requests[0]?.params?.request_id);
  });

  it('regenerate does nothing before a first generation', async () => {
    const { transport, requests } = scripted([{ kind: 'done' }]);
    const { result } = renderHook(() => useAIAssistant({ transport }));

    await act(async () => {
      await result.current.regenerate();
    });

    expect(requests).toHaveLength(0);
  });

  it('clear discards the output and the prompt', async () => {
    const { transport } = scripted([
      { kind: 'token', token: 'x' },
      { kind: 'done' },
    ]);
    const { result } = renderHook(() => useAIAssistant({ transport }));
    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'draft' });
    });

    act(() => result.current.clear());

    expect(result.current.output).toBe('');
    expect(result.current.status).toBe('idle');
    expect(result.current.lastPrompt).toBeNull();
  });

  it('a second generation replaces the first output', async () => {
    const { transport } = scripted([
      { kind: 'token', token: 'second' },
      { kind: 'done' },
    ]);
    const { result } = renderHook(() => useAIAssistant({ transport }));
    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'a' });
    });

    await act(async () => {
      await result.current.generate({ action: 'rewrite', text: 'b' });
    });

    expect(result.current.output).toBe('second');
  });

  it('aborts an in-flight generation when the component unmounts', async () => {
    const { transport, aborted } = hanging();
    const { result, unmount } = renderHook(() => useAIAssistant({ transport }));
    act(() => {
      void result.current.generate({ action: 'rewrite', text: 'draft' });
    });
    await flush();

    unmount();

    expect(aborted()).toBe(true);
  });
});
