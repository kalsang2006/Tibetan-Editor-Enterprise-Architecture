/**
 * The wire contract between the task pane and the TEEA desktop daemon.
 *
 * These shapes mirror `src/teea/ipc/models.py` field for field. They are **not**
 * JSON-RPC 2.0: the daemon's `IpcRequest` and `IpcResponse` are frozen Pydantic
 * models declared with `extra="forbid"`, so a `jsonrpc: "2.0"` member would be
 * rejected at the boundary rather than ignored. A response reports success with
 * a boolean `ok` and carries an `IpcFault` rather than a numeric error code.
 *
 * `IpcServer` itself still composes over an injected `Transport` (ADR-020) and
 * ships no socket of its own. For the AI assistant specifically, though, a
 * concrete channel now exists: `teea.transport.http_server.AiHttpServer`, a
 * loopback-only HTTP+SSE bridge in front of `teea.ai.handlers` (not in front of
 * `IpcServer` itself -- see that package's own docstring for why). It speaks
 * exactly the `IpcRequest`/`IpcResponse` shapes below, so this file doubles as
 * that bridge's client-side contract.
 */

/** The protocol major version this build speaks. Checked at `$connect`. */
export const PROTOCOL_VERSION = '1.0';

/**
 * Path each AI method is served at over the loopback HTTP bridge.
 *
 * Mirrors `teea.ai.handlers.AI_ENDPOINT_METHODS`, inverted: the Python side is
 * keyed by path because a server routes an incoming path to a method: this
 * side is keyed by method because a client already has the method (from the
 * `IpcRequest` it is about to send) and needs the path to send it to.
 */
export const AI_METHOD_PATHS: Readonly<Record<string, string>> = {
  'ai.rewrite': '/api/ai/rewrite',
  'ai.explain': '/api/ai/explain',
  'ai.summarize': '/api/ai/summarize',
  'ai.cancel': '/api/ai/cancel',
  'ai.translate': '/api/ai/translate',
  'ai.ocr': '/api/ai/ocr',
  'ai.stt': '/api/ai/stt',
};

/**
 * The port `teea.transport.http_server`'s daemon-side entry point binds by
 * convention, pending a real daemon launcher deciding this for good. Kept in
 * one place so the day a daemon entrypoint exists, only this line needs to
 * change to match it.
 */
export const DEFAULT_AI_DAEMON_PORT = 50505;

/**
 * The method the document-analysis bridge answers, and the path it is served
 * at. Mirrors `teea.transport.analysis_server.ANALYSIS_METHOD` / `.ANALYSIS_PATH`.
 * One composite call rather than the daemon's separate `analyze` / `plugins` /
 * `fuse` IPC methods, so a book-length document's snapshot never round-trips
 * over HTTP between steps -- see that module's docstring.
 */
export const ANALYSIS_METHOD = 'analysis.run';
export const ANALYSIS_PATH = '/api/analysis/run';
export const PLAGIARISM_METHOD = 'plagiarism.check';
export const PLAGIARISM_PATH = '/api/plagiarism/check';

/**
 * The port `teea.transport.analysis_server`'s daemon-side entry point binds by
 * convention, pending a real daemon launcher deciding this for good -- same
 * caveat as {@link DEFAULT_AI_DAEMON_PORT}. Distinct constant, even though it
 * currently has the same value, because each bridge binds its own socket and a
 * future launcher may give them different ports.
 */
export const DEFAULT_ANALYSIS_DAEMON_PORT = 50505;

/** One call from the task pane to the daemon. */
export interface IpcRequest {
  /** The version the sender speaks. */
  protocol_version: string;
  /** Correlates a response to this request. Unique per connection. */
  request_id: string;
  /** The routed method name, e.g. `ai.rewrite`. */
  method: string;
  /** The call's arguments. */
  params: Record<string, unknown>;
  /** The session this call belongs to, or `null` for the handshake. */
  session_id: string | null;
  /** Whether the caller awaits a response. A query does; a command does not. */
  expects_response: boolean;
}

/** A failure, carried inside a response. Never contains document content. */
export interface IpcFault {
  /** The stable `TEEA-xxxx` code. */
  code: string;
  /** The exception class name, for diagnosis. */
  error_type: string;
  /** The human-readable message. */
  message: string;
  /** Structured, non-sensitive detail. */
  context: Record<string, unknown>;
}

/** The daemon's reply to a query. Exactly one of `result` and `error` is set. */
export interface IpcResponse {
  protocol_version: string;
  request_id: string;
  ok: boolean;
  result?: Record<string, unknown> | null;
  error?: IpcFault | null;
}

/** Whether a routed method answers or merely acts. */
export type MethodKind = 'query' | 'command';

/** A session, minted by `$connect`. */
export interface Session {
  session_id: string;
  protocol_version: string;
}

/**
 * One reviewable recommendation, as the task pane models it.
 *
 * This is the add-in's view model, not the daemon's `teea.fusion.Suggestion`.
 * The two differ deliberately and are bridged in `services/suggestionAdapter`:
 * the engine addresses ranges with a `TextSpan` carrying both character and
 * UTF-8 byte offsets, because Tibetan is three bytes per codepoint and the NLP
 * layer needs both. Word.js addresses text in characters only, so carrying byte
 * offsets into the UI would invite someone to use the wrong one.
 */
export interface Suggestion {
  /** Stable identity for the lifetime of one analysis. */
  id: string;
  /** Document-wide character offset of the first affected character. */
  start: number;
  /** How many characters the suggestion covers. Zero is an insertion point. */
  length: number;
  /** The text currently in that range, used to verify before replacing. */
  originalText: string;
  /** What to put there. Empty string is a deletion. */
  suggestedText: string;
  category: SuggestionCategory;
  severity: SuggestionSeverity;
  /** Why, in one sentence, for the card. */
  explanation: string;
  /** Which rule fired, for filtering and for reporting a false positive. */
  ruleId: string;
  /** The producing component's own confidence, 0.0 to 1.0. */
  confidence: number;
  /** Snippet of text before the offset for UI context. */
  contextBefore?: string;
  /** Snippet of text after the offset for UI context. */
  contextAfter?: string;
}

export type SuggestionCategory =
  | 'Grammar'
  | 'Spelling'
  | 'Style'
  | 'Typography'
  | 'Terminology';

export type SuggestionSeverity = 'critical' | 'warning' | 'suggestion';

/** Declaration order, which is also the order groups are presented in. */
export const SUGGESTION_CATEGORIES: readonly SuggestionCategory[] = [
  'Spelling',
  'Grammar',
  'Terminology',
  'Style',
  'Typography',
];

/** Most urgent first. */
export const SEVERITY_ORDER: Record<SuggestionSeverity, number> = {
  critical: 0,
  warning: 1,
  suggestion: 2,
};

/**
 * The daemon's own suggestion shape, as it crosses the boundary.
 *
 * `teea.fusion.Suggestion` serialized by Pydantic. Present so the adapter has
 * something typed to convert *from* rather than reaching into `unknown`.
 */
export interface DaemonSuggestion {
  source: string;
  span: {
    char_start: number;
    char_end: number;
    byte_start: number;
    byte_end: number;
  };
  replacement: string | null;
  score: number;
  priority: 'critical' | 'high' | 'medium' | 'low';
  message: string;
  error_type?: string;
}

/** One frame of an SSE token stream, already parsed. */
export type StreamFrame =
  | { kind: 'token'; token: string }
  | { kind: 'cancelled' }
  | { kind: 'error'; code: string; message: string }
  | { kind: 'done' };

/** A match reported by the plagiarism engine. */
export interface PlagiarismMatch {
  document_id: string;
  collection?: string | null;
  filename?: string | null;
  similarity: number;
  coverage: number;
  overlap_count: number;
  query_fingerprint_count: number;
  doc_fingerprint_count: number;
  source_span: {
    char_start: number;
    char_end: number;
    byte_start: number;
    byte_end: number;
  } | null;
}

/** Result payload returned by the plagiarism check endpoint. */
export interface PlagiarismCheckResult {
  originality_score: number;
  matches: PlagiarismMatch[];
  query_text?: string;
  query_fingerprint_count: number;
  total_corpus_documents: number;
  elapsed_ms: number;
}
