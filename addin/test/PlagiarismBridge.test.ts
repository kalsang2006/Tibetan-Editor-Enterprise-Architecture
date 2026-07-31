import { fetchPlagiarismCheck } from '../src/taskpane/services/PlagiarismBridge';
import { DaemonFaultError } from '../src/taskpane/services/IpcBridge';

describe('fetchPlagiarismCheck', () => {
  it('sends plagiarism.check request and unwraps result', async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        protocol_version: '1.0',
        request_id: 'req-1',
        ok: true,
        result: {
          originality_score: 85.5,
          matches: [
            {
              document_id: 'ref1',
              similarity: 0.145,
              coverage: 0.5,
              overlap_count: 3,
              query_fingerprint_count: 20,
              doc_fingerprint_count: 6,
              source_span: { char_start: 0, char_end: 15, byte_start: 0, byte_end: 45 },
            },
          ],
          query_fingerprint_count: 20,
          total_corpus_documents: 10,
          elapsed_ms: 2.5,
        },
      }),
    });

    const res = await fetchPlagiarismCheck({
      baseUrl: 'http://127.0.0.1:50505',
      text: 'some query text',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    expect(res.originality_score).toBe(85.5);
    expect(res.matches).toHaveLength(1);
    expect(res.matches[0]!.document_id).toBe('ref1');
    expect(res.matches[0]!.source_span).toEqual({ char_start: 0, char_end: 15, byte_start: 0, byte_end: 45 });
  });

  it('handles empty response gracefully', async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        result: {
          originality_score: 100,
          matches: [],
          query_fingerprint_count: 0,
          total_corpus_documents: 0,
          elapsed_ms: 0.1,
        },
      }),
    });

    const res = await fetchPlagiarismCheck({
      baseUrl: 'http://127.0.0.1:50505',
      text: '',
      fetchImpl: mockFetch as unknown as typeof fetch,
    });

    expect(res.originality_score).toBe(100);
    expect(res.matches).toEqual([]);
  });

  it('throws DaemonFaultError on unreachable server', async () => {
    const mockFetch = jest.fn().mockRejectedValue(new Error('Connection refused'));

    await expect(
      fetchPlagiarismCheck({
        baseUrl: 'http://127.0.0.1:50505',
        text: 'query',
        fetchImpl: mockFetch as unknown as typeof fetch,
      }),
    ).rejects.toThrow(DaemonFaultError);
  });
});
