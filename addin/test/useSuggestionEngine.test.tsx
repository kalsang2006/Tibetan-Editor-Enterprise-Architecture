import { act, renderHook } from '@testing-library/react';

import {
  AUTO_APPLY_CONFIDENCE,
  VIRTUALIZATION_THRESHOLD,
  groupByCategory,
  isAutoApplicable,
  sortForReview,
  toOperation,
  useSuggestionEngine,
} from '../src/taskpane/hooks/useSuggestionEngine';
import type { ApplyReport } from '../src/taskpane/services/WordDocument';
import type { Suggestion } from '../src/taskpane/types/ipc';

function suggestion(overrides: Partial<Suggestion> = {}): Suggestion {
  return {
    id: 'sug-1',
    start: 0,
    length: 3,
    originalText: 'old',
    suggestedText: 'new',
    category: 'Spelling',
    severity: 'suggestion',
    explanation: 'because',
    ruleId: 'spell',
    confidence: 0.9,
    ...overrides,
  };
}

const passThrough = async (
  operations: readonly ReturnType<typeof toOperation>[],
): Promise<ApplyReport> => ({ applied: [...operations], skipped: [] });

describe('auto-applicability', () => {
  it('accepts a confident non-critical suggestion', () => {
    expect(isAutoApplicable(suggestion({ confidence: 0.8 }))).toBe(true);
  });

  it('rejects anything below the confidence floor', () => {
    expect(isAutoApplicable(suggestion({ confidence: 0.79 }))).toBe(false);
    expect(AUTO_APPLY_CONFIDENCE).toBe(0.8);
  });

  it('rejects a critical suggestion however confident', () => {
    expect(
      isAutoApplicable(suggestion({ severity: 'critical', confidence: 1 })),
    ).toBe(false);
  });

  it('accepts a warning at the floor', () => {
    expect(
      isAutoApplicable(suggestion({ severity: 'warning', confidence: 0.95 })),
    ).toBe(true);
  });
});

describe('ordering and grouping', () => {
  it('orders critical first, then by document position', () => {
    const ordered = sortForReview([
      suggestion({ id: 'a', start: 100, severity: 'suggestion' }),
      suggestion({ id: 'b', start: 50, severity: 'critical' }),
      suggestion({ id: 'c', start: 10, severity: 'warning' }),
      suggestion({ id: 'd', start: 5, severity: 'critical' }),
    ]);

    expect(ordered.map((item) => item.id)).toEqual(['d', 'b', 'c', 'a']);
  });

  it('groups by category in the declared presentation order', () => {
    const groups = groupByCategory([
      suggestion({ id: 'a', category: 'Style' }),
      suggestion({ id: 'b', category: 'Spelling' }),
      suggestion({ id: 'c', category: 'Grammar' }),
    ]);

    expect(groups.map((group) => group.category)).toEqual([
      'Spelling',
      'Grammar',
      'Style',
    ]);
  });

  it('drops empty categories', () => {
    const groups = groupByCategory([suggestion({ category: 'Typography' })]);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.category).toBe('Typography');
  });

  it('counts criticals per group', () => {
    const groups = groupByCategory([
      suggestion({ id: 'a', category: 'Grammar', severity: 'critical' }),
      suggestion({ id: 'b', category: 'Grammar', severity: 'warning' }),
    ]);

    expect(groups[0]?.criticalCount).toBe(1);
  });
});

describe('useSuggestionEngine', () => {
  it('exposes the ordered list and its groups', () => {
    const items = [
      suggestion({ id: 'a', category: 'Style', start: 20 }),
      suggestion({ id: 'b', category: 'Spelling', start: 5 }),
    ];
    const { result } = renderHook(() =>
      useSuggestionEngine(items, { apply: passThrough }),
    );

    expect(result.current.total).toBe(2);
    expect(result.current.groups.map((group) => group.category)).toEqual([
      'Spelling',
      'Style',
    ]);
  });

  it('memoizes derived state across renders with the same input', () => {
    const items = [suggestion()];
    const { result, rerender } = renderHook(() =>
      useSuggestionEngine(items, { apply: passThrough }),
    );
    const first = result.current.groups;

    rerender();

    expect(result.current.groups).toBe(first);
  });

  it('recomputes when the suggestions change', () => {
    let items = [suggestion({ id: 'a' })];
    const { result, rerender } = renderHook(() =>
      useSuggestionEngine(items, { apply: passThrough }),
    );
    const first = result.current.ordered;

    items = [suggestion({ id: 'a' }), suggestion({ id: 'b', start: 30 })];
    rerender();

    expect(result.current.ordered).not.toBe(first);
    expect(result.current.total).toBe(2);
  });

  it('selects only the auto-applicable entries for the batch', () => {
    const { result } = renderHook(() =>
      useSuggestionEngine(
        [
          suggestion({ id: 'a', confidence: 0.95 }),
          suggestion({ id: 'b', confidence: 0.5, start: 10 }),
          suggestion({ id: 'c', severity: 'critical', confidence: 1, start: 20 }),
        ],
        { apply: passThrough },
      ),
    );

    expect(result.current.autoApplicable.map((item) => item.id)).toEqual(['a']);
  });

  it('compiles the batch into one multi-operation command', async () => {
    const apply = jest.fn(passThrough);
    const { result } = renderHook(() =>
      useSuggestionEngine(
        [
          suggestion({ id: 'a', start: 0 }),
          suggestion({ id: 'b', start: 10 }),
          suggestion({ id: 'c', start: 20 }),
        ],
        { apply, idFactory: () => 'batch-1' },
      ),
    );

    let command = null as Awaited<ReturnType<typeof result.current.applyBatch>>;
    await act(async () => {
      command = await result.current.applyBatch();
    });

    expect(apply).toHaveBeenCalledTimes(1);
    expect(command?.id).toBe('batch-1');
    expect(command?.operations).toHaveLength(3);
    expect(command?.suggestionIds).toEqual(['a', 'b', 'c']);
  });

  it('applies one suggestion as a single-operation command', async () => {
    const { result } = renderHook(() =>
      useSuggestionEngine([suggestion({ id: 'a' })], { apply: passThrough }),
    );

    let command = null as Awaited<ReturnType<typeof result.current.applyOne>>;
    await act(async () => {
      command = await result.current.applyOne(suggestion({ id: 'a' }));
    });

    expect(command?.operations).toEqual([
      { rangeStart: 0, rangeLength: 3, originalText: 'old', newText: 'new' },
    ]);
  });

  it('returns null for an empty batch rather than an empty command', async () => {
    const { result } = renderHook(() =>
      useSuggestionEngine([suggestion({ confidence: 0.1 })], { apply: passThrough }),
    );

    let command = null as Awaited<ReturnType<typeof result.current.applyBatch>>;
    await act(async () => {
      command = await result.current.applyBatch();
    });

    expect(command).toBeNull();
  });

  it('refuses a batch whose operations overlap', async () => {
    const { result } = renderHook(() =>
      useSuggestionEngine(
        [
          suggestion({ id: 'a', start: 0, length: 5, originalText: 'abcde' }),
          suggestion({ id: 'b', start: 3, length: 5, originalText: 'defgh' }),
        ],
        { apply: passThrough },
      ),
    );

    await act(async () => {
      await expect(result.current.applyBatch()).rejects.toThrow(/overlapping/);
    });
  });

  it('returns null when the document rejected every operation', async () => {
    const apply = jest.fn().mockResolvedValue({ applied: [], skipped: [] });
    const { result } = renderHook(() =>
      useSuggestionEngine([suggestion({ id: 'a' })], { apply }),
    );

    let command = null as Awaited<ReturnType<typeof result.current.applyBatch>>;
    await act(async () => {
      command = await result.current.applyBatch();
    });

    expect(command).toBeNull();
  });

  it('dismisses a suggestion without touching the document', () => {
    const apply = jest.fn(passThrough);
    const { result } = renderHook(() =>
      useSuggestionEngine([suggestion({ id: 'a' })], { apply }),
    );

    act(() => result.current.dismiss('a'));

    expect(result.current.total).toBe(0);
    expect(apply).not.toHaveBeenCalled();
    expect(result.current.dismissed.has('a')).toBe(true);
  });

  it('dismissing the same id twice does not churn state', () => {
    const { result } = renderHook(() =>
      useSuggestionEngine([suggestion({ id: 'a' })], { apply: passThrough }),
    );
    act(() => result.current.dismiss('a'));
    const first = result.current.dismissed;

    act(() => result.current.dismiss('a'));

    expect(result.current.dismissed).toBe(first);
  });

  it('asks for windowing only past the threshold', () => {
    const many = Array.from({ length: VIRTUALIZATION_THRESHOLD + 1 }, (_value, index) =>
      suggestion({ id: `s-${index}`, start: index * 10 }),
    );
    const { result } = renderHook(() =>
      useSuggestionEngine(many, { apply: passThrough }),
    );

    expect(result.current.needsVirtualization).toBe(true);
  });

  it('does not window a short list', () => {
    const { result } = renderHook(() =>
      useSuggestionEngine([suggestion()], { apply: passThrough }),
    );

    expect(result.current.needsVirtualization).toBe(false);
  });
});

describe('toOperation', () => {
  it('carries the offsets and both texts', () => {
    expect(toOperation(suggestion({ start: 7, length: 2 }))).toEqual({
      rangeStart: 7,
      rangeLength: 2,
      originalText: 'old',
      newText: 'new',
    });
  });
});
