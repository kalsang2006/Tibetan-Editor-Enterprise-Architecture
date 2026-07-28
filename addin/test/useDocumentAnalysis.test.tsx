import { act, renderHook, waitFor } from '@testing-library/react';

import { useDocumentAnalysis } from '../src/taskpane/hooks/useDocumentAnalysis';
import { resetRequestIds } from '../src/taskpane/services/IpcBridge';

beforeEach(() => {
  resetRequestIds();
});

const DOCUMENT = 'the document text';

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  } as unknown as Response;
}

const suggestion = {
  source: 'spell',
  span: { char_start: 0, char_end: 3, byte_start: 0, byte_end: 9 },
  replacement: 'THE',
  score: 0.9,
  priority: 'high' as const,
  message: 'Consider capitalizing.',
};

describe('useDocumentAnalysis', () => {
  it('runs on mount and reports the ranked suggestions', async () => {
    const fetchImpl = jest
      .fn()
      .mockResolvedValue(
        jsonResponse({ ok: true, request_id: 'req-1', result: { suggestions: [suggestion] } }),
      );
    const getText = jest.fn().mockResolvedValue(DOCUMENT);

    const { result } = renderHook(() => useDocumentAnalysis({ getText, fetchImpl }));

    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('ready'));

    expect(result.current.suggestions).toHaveLength(1);
    expect(result.current.suggestions[0]?.suggestedText).toBe('THE');
    expect(result.current.error).toBeNull();
  });

  it('reports unavailable when the daemon cannot be reached', async () => {
    const fetchImpl = jest.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const getText = jest.fn().mockResolvedValue(DOCUMENT);

    const { result } = renderHook(() => useDocumentAnalysis({ getText, fetchImpl }));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
    expect(result.current.suggestions).toEqual([]);
  });

  it('reports error when the daemon rejects the request', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse({}, { ok: false, status: 500 }));
    const getText = jest.fn().mockResolvedValue(DOCUMENT);

    const { result } = renderHook(() => useDocumentAnalysis({ getText, fetchImpl }));

    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('reports error when reading the document itself fails', async () => {
    const fetchImpl = jest.fn();
    const getText = jest.fn().mockRejectedValue(new Error('Word.run failed'));

    const { result } = renderHook(() => useDocumentAnalysis({ getText, fetchImpl }));

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error).toBe('Word.run failed');
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('refresh re-reads the document and re-runs the pipeline', async () => {
    const fetchImpl = jest
      .fn()
      .mockResolvedValue(jsonResponse({ ok: true, request_id: 'req-1', result: { suggestions: [] } }));
    const getText = jest.fn().mockResolvedValueOnce(DOCUMENT).mockResolvedValueOnce('edited text');

    const { result } = renderHook(() => useDocumentAnalysis({ getText, fetchImpl }));
    await waitFor(() => expect(result.current.status).toBe('ready'));

    act(() => result.current.refresh());
    await waitFor(() => expect(getText).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.status).toBe('ready'));
  });

  it('ignores a slow first run that resolves after a later refresh', async () => {
    let resolveFirst: ((value: Response) => void) | null = null;
    const fetchImpl = jest
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, request_id: 'req-2', result: { suggestions: [suggestion] } }),
      );
    const getText = jest.fn().mockResolvedValue(DOCUMENT);

    const { result } = renderHook(() => useDocumentAnalysis({ getText, fetchImpl }));
    expect(result.current.status).toBe('loading');

    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.status).toBe('ready'));

    act(() => resolveFirst?.(jsonResponse({ ok: false, request_id: 'req-1' }, { ok: false, status: 500 })));
    await Promise.resolve();

    expect(result.current.status).toBe('ready');
    expect(result.current.suggestions).toHaveLength(1);
  });
});
