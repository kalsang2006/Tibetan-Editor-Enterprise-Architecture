import { fetchAnalysis } from '../src/taskpane/services/AnalysisBridge';
import { DaemonFaultError, resetRequestIds } from '../src/taskpane/services/IpcBridge';
import { ANALYSIS_PATH } from '../src/taskpane/types/ipc';

beforeEach(() => {
  resetRequestIds();
});

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  } as unknown as Response;
}

describe('fetchAnalysis', () => {
  it('posts an IpcRequest envelope to the analysis path', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse({ ok: true, request_id: 'req-1', result: { suggestions: [] } }),
    );

    await fetchAnalysis({ baseUrl: 'http://127.0.0.1:50505', text: 'hello', fetchImpl });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`http://127.0.0.1:50505${ANALYSIS_PATH}`);
    const body = JSON.parse(init.body as string);
    expect(body).toMatchObject({ method: 'analysis.run', params: { text: 'hello' } });
  });

  it('returns the suggestions from a successful response', async () => {
    const suggestion = {
      source: 'spell',
      span: { char_start: 0, char_end: 1, byte_start: 0, byte_end: 3 },
      replacement: 'x',
      score: 0.9,
      priority: 'high',
      message: 'typo',
    };
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse({ ok: true, request_id: 'req-1', result: { suggestions: [suggestion] } }),
    );

    const result = await fetchAnalysis({ baseUrl: 'http://127.0.0.1:50505', text: 'x', fetchImpl });

    expect(result).toEqual([suggestion]);
  });

  it('raises DaemonFaultError when the daemon reports a fault', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      jsonResponse({
        ok: false,
        request_id: 'req-1',
        error: {
          code: 'TEEA-0002',
          error_type: 'InputValidationError',
          message: 'text must be a string',
          context: {},
        },
      }),
    );

    await expect(
      fetchAnalysis({ baseUrl: 'http://127.0.0.1:50505', text: 'x', fetchImpl }),
    ).rejects.toThrow(DaemonFaultError);
  });

  it('raises DaemonFaultError when the connection itself fails', async () => {
    const fetchImpl = jest.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(
      fetchAnalysis({ baseUrl: 'http://127.0.0.1:50505', text: 'x', fetchImpl }),
    ).rejects.toThrow(/Could not reach/);
  });

  it('raises DaemonFaultError on a non-OK HTTP status', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse({}, { ok: false, status: 500 }));

    await expect(
      fetchAnalysis({ baseUrl: 'http://127.0.0.1:50505', text: 'x', fetchImpl }),
    ).rejects.toThrow(/rejected the analysis request/);
  });

  it('refuses a non-loopback base URL', async () => {
    const fetchImpl = jest.fn();

    await expect(
      fetchAnalysis({ baseUrl: 'http://example.com', text: 'x', fetchImpl }),
    ).rejects.toThrow();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('propagates an AbortError unchanged', async () => {
    const abortError = new DOMException('aborted', 'AbortError');
    const fetchImpl = jest.fn().mockRejectedValue(abortError);

    await expect(
      fetchAnalysis({ baseUrl: 'http://127.0.0.1:50505', text: 'x', fetchImpl }),
    ).rejects.toBe(abortError);
  });
});
