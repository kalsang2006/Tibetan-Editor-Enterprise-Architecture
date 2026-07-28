import {
  LARGE_DOCUMENT_THRESHOLD,
  SLICE_SIZE,
  applyOperations,
  countOccurrencesBefore,
  insertAfterSelection,
  isLargeDocument,
  readDocumentText,
  readSelectionText,
  replaceSelection,
} from '../src/taskpane/services/WordDocument';
import { installOfficeMock } from './officeMock';

describe('reading the document', () => {
  it('falls back to a single body read when the host has no slicing API', async () => {
    installOfficeMock(['first paragraph', 'second paragraph']);

    await expect(readDocumentText()).resolves.toBe(
      'first paragraph\rsecond paragraph',
    );
  });

  it('reads through getFileAsync when the host exposes it', async () => {
    const host = installOfficeMock(['alpha', 'beta'], { withGetFileAsync: true });

    await expect(readDocumentText()).resolves.toBe('alpha\rbeta');
    expect(host.state.slicesRead).toEqual([0]);
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
