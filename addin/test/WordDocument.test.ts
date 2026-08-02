import {
  LARGE_DOCUMENT_THRESHOLD,
  READ_RETRY_BACKOFF_MS,
  SLICE_SIZE,
  applyOperations,
  canonicalizeDocumentText,
  countOccurrencesBefore,
  insertAfterSelection,
  isLargeDocument,
  readDocumentText,
  readSelectionText,
  replaceSelection,
} from '../src/taskpane/services/WordDocument';
import { installOfficeMock } from './officeMock';

describe('reading the document', () => {
  /** Make the tier-2 retry loop instant, then restore the real delays. */
  const withZeroBackoff = async <T>(run: () => Promise<T>): Promise<T> => {
    const saved = [...READ_RETRY_BACKOFF_MS];
    READ_RETRY_BACKOFF_MS.splice(0, READ_RETRY_BACKOFF_MS.length, 0, 0, 0);
    try {
      return await run();
    } finally {
      READ_RETRY_BACKOFF_MS.splice(0, READ_RETRY_BACKOFF_MS.length, ...saved);
    }
  };

  it('falls back to a single body read when the host has no slicing API', async () => {
    installOfficeMock(['first paragraph', 'second paragraph']);

    await expect(readDocumentText()).resolves.toBe(
      'first paragraph\rsecond paragraph',
    );
  });

  it('tier 3 select-all reads through a body that reports empty, then restores the selection', async () => {
    const host = installOfficeMock(['first paragraph', 'second paragraph'], {
      selection: 'the cursor',
      emptyBody: true,
      withSelectionFallback: true,
    });

    await withZeroBackoff(async () => {
      await expect(readDocumentText()).resolves.toBe(
        'first paragraph\rsecond paragraph',
      );
    });

    // The user's original selection must be restored, not the whole body.
    expect(host.state.selection).toBe('the cursor');
  });

  it('tier 3 restores a collapsed cursor when there was no prior selection', async () => {
    const host = installOfficeMock(['only paragraph'], {
      emptyBody: true,
      withSelectionFallback: true,
    });

    await withZeroBackoff(async () => {
      await expect(readDocumentText()).resolves.toBe('only paragraph');
    });

    // No selection option means the initial selection was an empty string,
    // standing in for a collapsed cursor; the restore puts it back to empty.
    expect(host.state.selection).toBe('');
  });

  it('returns "" only after every tier has been exhausted', async () => {
    // No getFileAsync, an empty document, and no select-all capability:
    // every tier must fail before "" is returned.
    installOfficeMock([], {});
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);

    try {
      await withZeroBackoff(async () => {
        await expect(readDocumentText()).resolves.toBe('');
      });
      expect(warn).toHaveBeenCalledWith(expect.stringContaining('all 5 tiers exhausted'));
    } finally {
      warn.mockRestore();
    }
  });

  it('reads through getFileAsync when the host exposes it', async () => {
    const host = installOfficeMock(['alpha', 'beta'], { withGetFileAsync: true });

    await expect(readDocumentText()).resolves.toBe('alpha\rbeta');
    expect(host.state.slicesRead).toEqual([0]);
  });

  it('collapses CRLF paragraph breaks from getFileAsync to the canonical CR', async () => {
    // On Windows, getFileAsync emits \r\n between paragraphs; the daemon's
    // offsets are computed against exactly that text. readDocumentText must
    // collapse every break to a single CR so the apply-time reconstruction
    // (which assumes one character per paragraph boundary) stays in sync.
    installOfficeMock(['alpha', 'beta'], {
      withGetFileAsync: true,
      fileSeparator: '\r\n',
    });

    await expect(readDocumentText()).resolves.toBe('alpha\rbeta');
  });

  it('canonicalizes every paragraph-break convention to a single CR', () => {
    expect(canonicalizeDocumentText('a\r\nb\rc\nd')).toBe('a\rb\rc\rd');
    expect(canonicalizeDocumentText('\uFEFFབོད་ཡིག')).toBe('བོད་ཡིག');
    expect(canonicalizeDocumentText('no breaks')).toBe('no breaks');
  });

  it('re-stitches a document that spans several slices', async () => {
    const paragraph = 'x'.repeat(1000);
    const host = installOfficeMock([paragraph, paragraph, paragraph], {
      withGetFileAsync: true,
      sliceSize: 256,
    });

    const text = await readDocumentText();

    expect(text).toHaveLength(3002);
    expect(text).toBe(`${paragraph}\r${paragraph}\r${paragraph}`);
    expect(host.state.slicesRead.length).toBeGreaterThan(1);
    expect(host.state.slicesRead).toEqual(
      host.state.slicesRead.map((_value, index) => index),
    );
  });

  it('reads the selection', async () => {
    installOfficeMock(['body'], { selection: 'chosen words' });

    await expect(readSelectionText()).resolves.toBe('chosen words');
  });

  it('names the documented slice size and threshold', () => {
    expect(SLICE_SIZE).toBe(65536);
    expect(LARGE_DOCUMENT_THRESHOLD).toBe(5000);
    expect(isLargeDocument(5001)).toBe(true);
    expect(isLargeDocument(5000)).toBe(false);
  });
});

describe('applying operations', () => {
  it('applies a single replacement', async () => {
    const host = installOfficeMock(['the cat sat']);

    const report = await applyOperations([
      { rangeStart: 4, rangeLength: 3, originalText: 'cat', newText: 'dog' },
    ]);

    expect(host.state.paragraphs[0]).toBe('the dog sat');
    expect(report.applied).toHaveLength(1);
    expect(report.skipped).toHaveLength(0);
  });

  it('applies a batch bottom-up so earlier offsets stay valid', async () => {
    // "one two three": replacing "one" with a longer word shifts "three" if the
    // batch runs top-down. Applying bottom-up is what keeps offset 8 correct.
    const host = installOfficeMock(['one two three']);

    await applyOperations([
      { rangeStart: 0, rangeLength: 3, originalText: 'one', newText: 'ONE-LONGER' },
      { rangeStart: 8, rangeLength: 5, originalText: 'three', newText: 'THREE' },
    ]);

    expect(host.state.paragraphs[0]).toBe('ONE-LONGER two THREE');
  });

  it('records the edits in bottom-up order', async () => {
    const host = installOfficeMock(['aaa bbb ccc']);

    await applyOperations([
      { rangeStart: 0, rangeLength: 3, originalText: 'aaa', newText: 'A' },
      { rangeStart: 8, rangeLength: 3, originalText: 'ccc', newText: 'C' },
      { rangeStart: 4, rangeLength: 3, originalText: 'bbb', newText: 'B' },
    ]);

    expect(host.state.edits.map((edit) => edit.start)).toEqual([8, 4, 0]);
    expect(host.state.paragraphs[0]).toBe('A B C');
  });

  it('shortening text earlier in the document does not corrupt later edits', async () => {
    const host = installOfficeMock(['aaaaaaaa middle zzzzzzzz']);

    await applyOperations([
      { rangeStart: 0, rangeLength: 8, originalText: 'aaaaaaaa', newText: 'a' },
      { rangeStart: 16, rangeLength: 8, originalText: 'zzzzzzzz', newText: 'z' },
    ]);

    expect(host.state.paragraphs[0]).toBe('a middle z');
  });

  it('skips an operation whose text no longer matches', async () => {
    const host = installOfficeMock(['the cat sat']);

    const report = await applyOperations([
      { rangeStart: 4, rangeLength: 3, originalText: 'dog', newText: 'fox' },
    ]);

    expect(host.state.paragraphs[0]).toBe('the cat sat');
    expect(report.applied).toHaveLength(0);
    expect(report.skipped[0]?.reason).toMatch(/no longer holds/);
  });

  it('skips an offset past the end of the document', async () => {
    installOfficeMock(['short']);

    const report = await applyOperations([
      { rangeStart: 900, rangeLength: 2, originalText: 'xx', newText: 'yy' },
    ]);

    expect(report.skipped[0]?.reason).toMatch(/past the end/);
  });

  it('skips a range that crosses a paragraph boundary', async () => {
    installOfficeMock(['abc', 'def']);

    const report = await applyOperations([
      { rangeStart: 1, rangeLength: 5, originalText: 'bc\rde', newText: 'x' },
    ]);

    expect(report.skipped[0]?.reason).toMatch(/paragraph boundary/);
  });

  it('applies a good operation even when another in the batch is stale', async () => {
    const host = installOfficeMock(['keep this', 'and this']);

    const report = await applyOperations([
      { rangeStart: 0, rangeLength: 4, originalText: 'WRONG', newText: 'x' },
      { rangeStart: 14, rangeLength: 4, originalText: 'this', newText: 'THAT' },
    ]);

    expect(report.applied).toHaveLength(1);
    expect(report.skipped).toHaveLength(1);
    expect(host.state.paragraphs[1]).toBe('and THAT');
  });

  it('addresses the right occurrence when a word repeats in one paragraph', async () => {
    const host = installOfficeMock(['cat cat cat']);

    await applyOperations([
      { rangeStart: 4, rangeLength: 3, originalText: 'cat', newText: 'DOG' },
    ]);

    expect(host.state.paragraphs[0]).toBe('cat DOG cat');
  });

  it('resolves an offset in the second paragraph', async () => {
    const host = installOfficeMock(['first', 'second']);

    await applyOperations([
      { rangeStart: 6, rangeLength: 6, originalText: 'second', newText: 'SECOND' },
    ]);

    expect(host.state.paragraphs[1]).toBe('SECOND');
  });

  it('handles Tibetan text without mangling offsets', async () => {
    const host = installOfficeMock(['བཀྲ་ཤིས་བདེ་ལེགས།']);
    const text = 'བཀྲ་ཤིས་བདེ་ལེགས།';
    const target = text.slice(0, 4);

    await applyOperations([
      { rangeStart: 0, rangeLength: 4, originalText: target, newText: 'XX' },
    ]);

    expect(host.state.paragraphs[0]).toBe(`XX${text.slice(4)}`);
  });

  it('rescues an operation whose offset drifted but whose text still exists once', async () => {
    // A separator-width skew shifts the recorded offset by one character; the
    // text itself is still there. applyOperations must not throw the whole
    // batch away -- it searches the paragraph and applies when unambiguous.
    const host = installOfficeMock(['the cat sat']);

    const report = await applyOperations([
      { rangeStart: 3, rangeLength: 3, originalText: 'cat', newText: 'dog' },
    ]);

    expect(report.applied).toHaveLength(1);
    expect(report.skipped).toHaveLength(0);
    expect(host.state.paragraphs[0]).toBe('the dog sat');
  });

  it('does not rescue when the drifted text appears more than once', async () => {
    // Ambiguous: two candidate occurrences, so applying by search could hit the
    // wrong one. The operation must be skipped rather than guessed.
    const host = installOfficeMock(['cat cat cat']);

    const report = await applyOperations([
      { rangeStart: 1, rangeLength: 3, originalText: 'cat', newText: 'DOG' },
    ]);

    expect(report.applied).toHaveLength(0);
    expect(report.skipped).toHaveLength(1);
    expect(host.state.paragraphs[0]).toBe('cat cat cat');
  });

  it('rescues across paragraphs when the text exists exactly once document-wide', async () => {
    // The drifting offset resolves to paragraph 0 (start + length stays inside
    // its bounds, so the boundary check passes), but the text actually lives
    // in paragraph 1. A paragraph-scoped rescue would either miss it or
    // replace the wrong location -- the document-wide uniqueness check is what
    // makes this safe: 'three' exists exactly once, so it is unambiguous.
    const host = installOfficeMock(['the quick brown fox jumps', 'lazy three']);

    const report = await applyOperations([
      { rangeStart: 5, rangeLength: 5, originalText: 'three', newText: 'THREE' },
    ]);

    expect(report.applied).toHaveLength(1);
    expect(report.skipped).toHaveLength(0);
    expect(host.state.paragraphs[1]).toBe('lazy THREE');
  });

  it('refuses a cross-paragraph rescue when the text appears in two paragraphs', async () => {
    // 'cat' exists once in each paragraph, so a document-wide search cannot
    // tell which instance the stale offset meant. Must skip, never guess.
    const host = installOfficeMock(['cat two', 'and cat']);

    const report = await applyOperations([
      { rangeStart: 1, rangeLength: 3, originalText: 'cat', newText: 'DOG' },
    ]);

    expect(report.applied).toHaveLength(0);
    expect(report.skipped).toHaveLength(1);
    expect(host.state.paragraphs[0]).toBe('cat two');
    expect(host.state.paragraphs[1]).toBe('and cat');
  });

  it('is a no-op for an empty batch', async () => {
    const host = installOfficeMock(['unchanged']);

    const report = await applyOperations([]);

    expect(report.applied).toEqual([]);
    expect(host.state.edits).toEqual([]);
    expect(host.state.syncs).toBe(0);
  });
});

describe('selection writes', () => {
  it('replaces the selection', async () => {
    const host = installOfficeMock(['body'], { selection: 'old' });

    await replaceSelection('new');

    expect(host.state.selection).toBe('new');
  });

  it('inserts after the selection', async () => {
    const host = installOfficeMock(['body'], { selection: 'kept' });

    await insertAfterSelection(' added');

    expect(host.state.selection).toBe('kept added');
  });
});

describe('countOccurrencesBefore', () => {
  it('counts occurrences strictly before the index', () => {
    expect(countOccurrencesBefore('cat cat cat', 'cat', 8)).toBe(2);
    expect(countOccurrencesBefore('cat cat cat', 'cat', 0)).toBe(0);
  });

  it('counts overlapping occurrences the way search reports them', () => {
    expect(countOccurrencesBefore('aaaa', 'aa', 3)).toBe(3);
  });

  it('returns zero for an empty needle', () => {
    expect(countOccurrencesBefore('anything', '', 5)).toBe(0);
  });
});
