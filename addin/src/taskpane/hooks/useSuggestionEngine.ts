/**
 * Grouping, filtering and batch-applying the current suggestions.
 *
 * Everything derived is memoized on the suggestion array's identity. The pane
 * re-renders on every keystroke of the document, and re-sorting five hundred
 * cards each time is what would put the interactive path over NFR 5.1's 50 ms
 * budget.
 */

import { useCallback, useMemo, useState } from 'react';

import {
  SEVERITY_ORDER,
  SUGGESTION_CATEGORIES,
  type Suggestion,
  type SuggestionCategory,
} from '../types/ipc';
import {
  findConflicts,
  type UndoCommand,
  type UndoOperation,
} from '../services/CommandStack';
import { applyOperations, type ApplyReport } from '../services/WordDocument';

/** Below this confidence a suggestion is never applied without review. */
export const AUTO_APPLY_CONFIDENCE = 0.8;

/** One category's worth of suggestions. */
export interface SuggestionGroupModel {
  category: SuggestionCategory;
  suggestions: Suggestion[];
  /** How many in this group are critical. */
  criticalCount: number;
}

/** What the hook exposes. */
export interface SuggestionEngine {
  /** Every suggestion, most urgent first. */
  ordered: Suggestion[];
  /** The suggestions grouped by category, in presentation order. */
  groups: SuggestionGroupModel[];
  /** Those the batch action would apply. */
  autoApplicable: Suggestion[];
  /** Whether the list is large enough to need windowing. */
  needsVirtualization: boolean;
  total: number;
  /** Apply one suggestion. */
  applyOne: (suggestion: Suggestion) => Promise<UndoCommand | null>;
  /** Apply every auto-applicable suggestion as one reversible batch. */
  applyBatch: () => Promise<UndoCommand | null>;
  /** Remove a suggestion from the list without touching the document. */
  dismiss: (id: string) => void;
  /** Which ids the user has dismissed. */
  dismissed: ReadonlySet<string>;
  /** What the last application actually did. */
  lastReport: ApplyReport | null;
  isApplying: boolean;
}

/** Above this many cards the list is windowed rather than fully rendered. */
export const VIRTUALIZATION_THRESHOLD = 100;

/**
 * Whether a suggestion may be applied without the user reading it.
 *
 * Two conditions, both required: it must not be critical, and the producing
 * component must be at least {@link AUTO_APPLY_CONFIDENCE} sure. Critical is
 * excluded regardless of confidence — the severity exists to mean "a human
 * should look at this", and a confident critical is still one.
 */
export function isAutoApplicable(suggestion: Suggestion): boolean {
  return (
    suggestion.severity !== 'critical' &&
    suggestion.confidence >= AUTO_APPLY_CONFIDENCE
  );
}

/** Turn a suggestion into the operation that applies it. */
export function toOperation(suggestion: Suggestion): UndoOperation {
  return {
    rangeStart: suggestion.start,
    rangeLength: suggestion.length,
    originalText: suggestion.originalText,
    newText: suggestion.suggestedText,
  };
}

/**
 * Derive the review model from the current suggestions.
 *
 * @param suggestions What the daemon produced, already adapted.
 * @param options.apply How operations reach the document. Injected for tests.
 * @param options.now Clock used for command ids. Injected for determinism.
 */
export function useSuggestionEngine(
  suggestions: readonly Suggestion[],
  options: {
    apply?: typeof applyOperations;
    idFactory?: () => string;
  } = {},
): SuggestionEngine {
  const { apply = applyOperations, idFactory } = options;
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(
    () => new Set<string>(),
  );
  const [lastReport, setLastReport] = useState<ApplyReport | null>(null);
  const [isApplying, setIsApplying] = useState(false);

  const visible = useMemo(
    () => suggestions.filter((item) => !dismissed.has(item.id)),
    [suggestions, dismissed],
  );

  const ordered = useMemo(() => sortForReview(visible), [visible]);

  const groups = useMemo(() => groupByCategory(ordered), [ordered]);

  const autoApplicable = useMemo(
    () => ordered.filter(isAutoApplicable),
    [ordered],
  );

  const needsVirtualization = ordered.length > VIRTUALIZATION_THRESHOLD;

  const runBatch = useCallback(
    async (batch: readonly Suggestion[]): Promise<UndoCommand | null> => {
      if (batch.length === 0) {
        return null;
      }
      const operations = batch.map(toOperation);
      const conflicts = findConflicts(operations);
      if (conflicts.length > 0) {
        // Two operations addressing the same characters cannot both be applied:
        // whichever ran second would be editing text the first replaced. The
        // Fusion Engine already resolves overlaps (FR-7), so reaching here means
        // the pane was handed a batch it must not silently half-apply.
        throw new RangeError(
          `the batch contains ${conflicts.length} overlapping operation pair(s)`,
        );
      }

      setIsApplying(true);
      try {
        const report = await apply(operations);
        console.log("Apply report:", JSON.stringify(report, null, 2));
        console.log("Applied:", report.applied);
        console.log("Skipped:", report.skipped);
        setLastReport(report);
        if (report.applied.length === 0) {
          return null;
        }
        const appliedIds = new Set(
          report.applied.map((operation) => operation.rangeStart),
        );
        return {
          id: idFactory?.() ?? `cmd-${batch[0]?.id ?? 'batch'}-${batch.length}`,
          suggestionIds: batch
            .filter((item) => appliedIds.has(item.start))
            .map((item) => item.id),
          operations: report.applied,
        };
      } finally {
        setIsApplying(false);
      }
    },
    [apply, idFactory],
  );

  const applyOne = useCallback(
    (suggestion: Suggestion) => runBatch([suggestion]),
    [runBatch],
  );

  const applyBatch = useCallback(
    () => runBatch(autoApplicable),
    [runBatch, autoApplicable],
  );

  const dismiss = useCallback((id: string) => {
    setDismissed((current) => {
      if (current.has(id)) {
        return current;
      }
      const next = new Set(current);
      next.add(id);
      return next;
    });
  }, []);

  return useMemo(
    () => ({
      ordered,
      groups,
      autoApplicable,
      needsVirtualization,
      total: ordered.length,
      applyOne,
      applyBatch,
      dismiss,
      dismissed,
      lastReport,
      isApplying,
    }),
    [
      ordered,
      groups,
      autoApplicable,
      needsVirtualization,
      applyOne,
      applyBatch,
      dismiss,
      dismissed,
      lastReport,
      isApplying,
    ],
  );
}

/**
 * Order for review: most urgent first, then earliest in the document.
 *
 * Document order is the tiebreak rather than confidence because the user reads
 * the pane against the document; jumping around it is disorienting even when the
 * jumps are individually well justified.
 */
export function sortForReview(suggestions: readonly Suggestion[]): Suggestion[] {
  return [...suggestions].sort((left, right) => {
    const bySeverity = SEVERITY_ORDER[left.severity] - SEVERITY_ORDER[right.severity];
    if (bySeverity !== 0) {
      return bySeverity;
    }
    if (left.start !== right.start) {
      return left.start - right.start;
    }
    return left.id.localeCompare(right.id);
  });
}

/**
 * Cluster suggestions by category, dropping empty categories.
 *
 * The order is {@link SUGGESTION_CATEGORIES}, not whatever order the daemon
 * produced: the pane's shape should not change because a plugin ran faster.
 */
export function groupByCategory(
  suggestions: readonly Suggestion[],
): SuggestionGroupModel[] {
  const buckets = new Map<SuggestionCategory, Suggestion[]>();
  for (const suggestion of suggestions) {
    const bucket = buckets.get(suggestion.category);
    if (bucket === undefined) {
      buckets.set(suggestion.category, [suggestion]);
    } else {
      bucket.push(suggestion);
    }
  }
  const groups: SuggestionGroupModel[] = [];
  for (const category of SUGGESTION_CATEGORIES) {
    const bucket = buckets.get(category);
    if (bucket !== undefined && bucket.length > 0) {
      groups.push({
        category,
        suggestions: bucket,
        criticalCount: bucket.filter((item) => item.severity === 'critical').length,
      });
    }
  }
  return groups;
}
