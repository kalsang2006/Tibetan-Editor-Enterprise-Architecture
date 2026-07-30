import {
  FALLBACK_CATEGORY,
  categoryOf,
  clampConfidence,
  toSuggestion,
  toSuggestions,
} from '../src/taskpane/services/suggestionAdapter';
import type { DaemonSuggestion } from '../src/taskpane/types/ipc';

const DOCUMENT = 'the cat sat on the mat';

function daemon(overrides: Partial<DaemonSuggestion> = {}): DaemonSuggestion {
  return {
    source: 'spell',
    span: { char_start: 4, char_end: 7, byte_start: 4, byte_end: 7 },
    replacement: 'dog',
    score: 0.92,
    priority: 'medium',
    message: 'unknown word',
    ...overrides,
  };
}

describe('toSuggestion', () => {
  it('takes the original text from the document, not from the daemon', () => {
    const converted = toSuggestion(daemon(), DOCUMENT);

    expect(converted?.originalText).toBe('cat');
    expect(converted?.start).toBe(4);
    expect(converted?.length).toBe(3);
  });

  it('discards an advisory that recommends no edit', () => {
    expect(toSuggestion(daemon({ replacement: null }), DOCUMENT)).toBeNull();
  });

  it('derives a stable id from the source and span', () => {
    expect(toSuggestion(daemon(), DOCUMENT)?.id).toContain('spell:4:7');
  });

  it('uses character offsets and never byte offsets', () => {
    const converted = toSuggestion(
      daemon({
        span: { char_start: 0, char_end: 3, byte_start: 0, byte_end: 9 },
      }),
      'བཀྲ་ཤིས།',
    );

    expect(converted?.length).toBe(3);
    expect(converted?.originalText).toBe('བཀྲ');
  });

  it.each([
    ['critical', 'critical'],
    ['high', 'warning'],
    ['medium', 'suggestion'],
    ['low', 'suggestion'],
  ] as const)('maps priority %s to severity %s', (priority, severity) => {
    expect(toSuggestion(daemon({ priority }), DOCUMENT)?.severity).toBe(severity);
  });

  it('keeps a deletion, which is an empty replacement', () => {
    const converted = toSuggestion(daemon({ replacement: '' }), DOCUMENT);

    expect(converted?.suggestedText).toBe('');
  });
});

describe('toSuggestions', () => {
  it('converts a batch and drops advisories', () => {
    const converted = toSuggestions(
      [
        daemon({ source: 'spell' }),
        daemon({ source: 'plagiarism', replacement: null }),
        daemon({
          source: 'grammar',
          span: { char_start: 8, char_end: 11, byte_start: 8, byte_end: 11 },
        }),
      ],
      DOCUMENT,
    );

    expect(converted.map((item) => item.ruleId)).toEqual(['spell', 'grammar']);
  });

  it('returns an empty array for an empty batch', () => {
    expect(toSuggestions([], DOCUMENT)).toEqual([]);
  });
});

describe('categoryOf', () => {
  it.each([
    ['spell', 'Spelling'],
    ['spelling', 'Spelling'],
    ['teea.spelling', 'Spelling'],
    ['grammar', 'Grammar'],
    ['teea.grammar', 'Grammar'],
    ['terminology', 'Terminology'],
    ['typography', 'Typography'],
    ['teea.typography', 'Typography'],
    ['style', 'Style'],
    ['teea.plagiarism', 'Style'],
    ['teea.diagnostics', 'Style'],
  ] as const)('files %s under %s', (source, category) => {
    expect(categoryOf(source)).toBe(category);
  });

  it('is case-insensitive', () => {
    expect(categoryOf('SPELL')).toBe('Spelling');
  });

  it('falls back rather than throwing for an unknown plugin', () => {
    expect(categoryOf('some-future-plugin')).toBe(FALLBACK_CATEGORY);
  });
});

describe('clampConfidence', () => {
  it('passes a value already in range', () => {
    expect(clampConfidence(0.42)).toBe(0.42);
  });

  it.each([
    [1.5, 1],
    [-0.2, 0],
    [Number.NaN, 0],
    [Number.POSITIVE_INFINITY, 0],
  ])('clamps %p to %p', (input, expected) => {
    expect(clampConfidence(input)).toBe(expected);
  });
});
