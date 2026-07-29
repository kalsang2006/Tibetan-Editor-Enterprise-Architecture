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
  terminology: 'Terminology',
  glossary: 'Terminology',
  typography: 'Typography',
  punctuation: 'Typography',
  style: 'Style',
  clarity: 'Style',
  'teea.plagiarism': 'Style',
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
  if (raw.replacement == null) {
  return null;
}
  const start = raw.span.char_start;
  const length = raw.span.char_end - raw.span.char_start;
  return {
    id: `${raw.source}:${raw.span.char_start}:${raw.span.char_end}`,
    start,
    length,
    originalText: documentText.slice(start, start + length),
    suggestedText: raw.replacement,
    category: categoryOf(raw.source),
    severity: PRIORITY_SEVERITY[raw.priority] ?? 'suggestion',
    explanation: raw.message,
    ruleId: raw.source,
    confidence: clampConfidence(raw.score),
  };
}

/**
 * Convert a batch, discarding advisories.
 *
 * @param raw What the Fusion Engine emitted.
 * @param documentText The text the offsets address.
 */
export function toSuggestions(
  raw: readonly DaemonSuggestion[],
  documentText: string,
): Suggestion[] {
  const converted: Suggestion[] = [];
  for (const item of raw) {
    const suggestion = toSuggestion(item, documentText);
    if (suggestion !== null) {
      converted.push(suggestion);
    }
  }
  return converted;
}

/** Which category a plugin's output is filed under. */
export function categoryOf(source: string): SuggestionCategory {
  return SOURCE_CATEGORIES[source.toLowerCase()] ?? FALLBACK_CATEGORY;
}

/**
 * Hold a confidence inside `[0, 1]`.
 *
 * The daemon validates the range on its own models, but a suggestion that
 * crossed the boundary from a future component with a looser contract would
 * otherwise render a progress bar past its own track.
 */
export function clampConfidence(score: number): number {
  if (!Number.isFinite(score)) {
    return 0;
  }
  return Math.min(1, Math.max(0, score));
}
