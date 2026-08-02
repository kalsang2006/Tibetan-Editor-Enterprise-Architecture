/**
 * Converting the daemon's suggestions into the task pane's view model.
 *
 * The two shapes differ deliberately. `teea.fusion.Suggestion` addresses text
 * with a `TextSpan` carrying character *and* UTF-8 byte offsets, because Tibetan
 * is three bytes per codepoint and the NLP layer needs both. Word.js addresses
 * text in characters only. Carrying byte offsets into the UI would put two
 * plausible numbers in front of every call site, and one of them would be wrong.
 *
 * The daemon also has no notion of the categories the pane groups by: its
 * `source` is a free-form plugin identifier (ADR-017 left it free-form because
 * the Plugin Runtime, not the Fusion Engine, owns plugin identity). The mapping
 * from source to category therefore lives here, on the consuming side, and falls
 * back rather than throwing — an unrecognised plugin must still be reviewable.
 */

import type {
  DaemonSuggestion,
  Suggestion,
  SuggestionCategory,
  SuggestionSeverity,
} from '../types/ipc';

/** Plugin source identifier to the category the pane groups it under. */
const SOURCE_CATEGORIES: Record<string, SuggestionCategory> = {
  spell: 'Spelling',
  spelling: 'Spelling',
  spellcheck: 'Spelling',
  'teea.spelling': 'Spelling',
  grammar: 'Grammar',
  syntax: 'Grammar',
  'teea.grammar': 'Grammar',
  'teea.grammar_correction': 'Grammar',
  terminology: 'Terminology',
  glossary: 'Terminology',
  typography: 'Typography',
  punctuation: 'Typography',
  'teea.typography': 'Typography',
  style: 'Style',
  clarity: 'Style',
  'teea.plagiarism': 'Style',
  'teea.diagnostics': 'Style',
};

/** Where an unrecognised plugin's output is filed. */
export const FALLBACK_CATEGORY: SuggestionCategory = 'Style';

/**
 * The daemon's four priority classes collapsed onto the pane's three severities.
 *
 * `high` becomes a warning rather than critical on purpose: the pane reserves
 * `critical` for the one severity that batch-apply refuses to touch, and folding
 * `high` into it would make the batch button do almost nothing.
 */
const PRIORITY_SEVERITY: Record<
  DaemonSuggestion['priority'],
  SuggestionSeverity
> = {
  critical: 'critical',
  high: 'warning',
  medium: 'suggestion',
  low: 'suggestion',
};

/**
 * Map error_type or source to UI category cleanly.
 */
export function categoryOf(source: string, errorType?: string): SuggestionCategory {
  const normType = (errorType || '').toUpperCase();
  if (
    normType.includes('GRAMMAR') ||
    normType.includes('TENSE') ||
    normType.includes('VERB') ||
    normType.includes('ADJ')
  ) {
    return 'Grammar';
  }
  if (
    normType.includes('CONTEXT') ||
    normType.includes('SEMANTIC') ||
    normType.includes('TERM')
  ) {
    return 'Terminology';
  }
  if (
    normType.includes('STRUCTURAL') ||
    normType.includes('SPELL') ||
    normType.includes('TYPO')
  ) {
    return 'Spelling';
  }
  return SOURCE_CATEGORIES[source.toLowerCase()] ?? FALLBACK_CATEGORY;
}

/**
 * Convert one daemon suggestion.
 *
 * @param raw What the Fusion Engine emitted.
 * @param documentText The text the offsets address, for `originalText`.
 * @returns The view model, or `null` for an advisory that recommends no edit.
 */
export function toSuggestion(
  raw: DaemonSuggestion,
  documentText: string,
): Suggestion | null {
  if (raw.replacement == null || raw.replacement === undefined) {
    return null;
  }
  const span =
    raw.span ||
    (raw as typeof raw & { range?: typeof raw.span }).range;
  if (!span || span.char_start == null || span.char_end == null) {
    return null;
  }
  const start = span.char_start;
  const length = span.char_end - span.char_start;
  const originalText = documentText.slice(start, start + length);
  const ruleId = raw.error_type || raw.source || 'teea';

  return {
    id: `${raw.source || 'teea'}:${start}:${span.char_end}:${raw.replacement}`,
    start,
    length,
    originalText,
    suggestedText: raw.replacement,
    category: categoryOf(raw.source || 'teea', raw.error_type),
    severity: (raw.priority && PRIORITY_SEVERITY[raw.priority]) ?? 'suggestion',
    explanation: raw.message || '',
    ruleId,
    confidence: clampConfidence(raw.score ?? 0.8),
  };
}

/**
 * Convert a batch, discarding advisories.
 *
 * @param raw What the Fusion Engine emitted (array or wrapper object).
 * @param documentText The text the offsets address.
 */
export function toSuggestions(
  raw: unknown,
  documentText: string,
): Suggestion[] {
  let list: DaemonSuggestion[] = [];
  if (Array.isArray(raw)) {
    list = raw as DaemonSuggestion[];
  } else if (raw && typeof raw === 'object') {
    const record = raw as Record<string, unknown>;
    const result = record.result;
    if (Array.isArray(record.suggestions)) {
      list = record.suggestions as DaemonSuggestion[];
    } else if (result && typeof result === 'object') {
      const resultRecord = result as Record<string, unknown>;
      if (Array.isArray(resultRecord.suggestions)) {
        list = resultRecord.suggestions as DaemonSuggestion[];
      } else if (
        resultRecord.patch &&
        typeof resultRecord.patch === 'object' &&
        Array.isArray((resultRecord.patch as Record<string, unknown>).operations)
      ) {
        const ops = (resultRecord.patch as Record<string, unknown>).operations as Array<
          Record<string, unknown>
        >;
        list = ops.map((op) => {
          const sources = op.sources;
          const span = op.span;
          const replacement = op.replacement;
          return {
            source:
              (Array.isArray(sources) && typeof sources[0] === 'string' ? sources[0] : null) ??
              'teea.grammar',
            span: (span ?? undefined) as DaemonSuggestion['span'],
            replacement: typeof replacement === 'string' ? replacement : null,
            score: 0.9,
            priority: 'high',
            message: `Suggestion: replace with ${replacement}`,
            error_type: 'GRAMMAR',
          } as DaemonSuggestion;
        });
      }
    }
  }

  const converted: Suggestion[] = [];
  for (const item of list) {
    if (item && typeof item === 'object') {
      const suggestion = toSuggestion(item, documentText);
      if (suggestion !== null) {
        converted.push(suggestion);
      }
    }
  }
  return converted;
}

/**
 * Hold a confidence inside `[0, 1]`.
 */
export function clampConfidence(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value));
}
