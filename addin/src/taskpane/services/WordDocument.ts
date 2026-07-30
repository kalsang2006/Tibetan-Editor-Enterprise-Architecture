/**
 * Every read from, and write to, the Word document.
 *
 * Concentrated in one module on purpose. Two hazards live here and nowhere else:
 * how a large document is read without stalling the pane, and how an offset
 * recorded before an edit is still correct after it.
 *
 * Reading large documents
 * -----------------------
 * Pulling a whole book through a single range query serializes the entire body
 * into one payload. Above {@link LARGE_DOCUMENT_THRESHOLD} characters the file
 * is read in {@link SLICE_SIZE} slices through `getFileAsync` and re-stitched
 * from an array buffer, which keeps each round trip bounded.
 *
 * Offset drift
 * ------------
 * Replacing text of one length with text of another shifts every character after
 * it, invalidating the recorded offsets of every suggestion further down. The
 * countermeasure is ordering, not recomputation: operations are applied from the
 * **bottom of the document upward**, so an edit only ever moves text that no
 * pending operation addresses. See {@link sortForApplication}.
 */

import {
  type UndoOperation,
  sortForApplication,
} from './CommandStack';

/** Above this many characters, read the document in slices. */
export const LARGE_DOCUMENT_THRESHOLD = 5000;

/** Slice size for `getFileAsync`, in bytes. */
export const SLICE_SIZE = 65536;

/** What Word puts between paragraphs in `body.text`. */
export const PARAGRAPH_SEPARATOR = '\r';

/** Raised when a range cannot be addressed, so a caller can report it. */
export class RangeResolutionError extends Error {
  constructor(
    message: string,
    readonly detail: { start: number; length: number; expected: string },
  ) {
    super(message);
    this.name = 'RangeResolutionError';
  }
}

/** What one applied batch actually did. */
export interface ApplyReport {
  /** Operations that were applied, in the order they ran. */
  applied: UndoOperation[];
  /** Operations that were skipped, with why. */
  skipped: Array<{ operation: UndoOperation; reason: string }>;
}

/**
 * Read the whole document as plain text.
 *
 * Uses `getFileAsync` when the host exposes it, because that is the slicing path
 * and it is correct for a document of any size. Falls back to a single body read
 * where it is unavailable, which is what the test host and older builds do.
 *
 * @returns The document text.
 */
export async function readDocumentText(): Promise<string> {
  const office = globalThis.Office;
  const getFileAsync = office?.context?.document?.getFileAsync;
  if (typeof getFileAsync !== 'function') {
    return readBodyText();
  }
  return readSlicedText();
}

/**
 * Read the current selection as plain text.
 *
 * @returns The selected text, or `''` when nothing is selected.
 */
export async function readSelectionText(): Promise<string> {
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.load('text');
    await context.sync();
    return selection.text ?? '';
  });
}

/**
 * Whether a body of text is large enough to warrant the slicing path.
 *
 * Exposed so a caller can decide *before* reading, rather than discovering it
 * after the expensive read has already happened.
 */
export function isLargeDocument(length: number): boolean {
  return length > LARGE_DOCUMENT_THRESHOLD;
}

/**
 * Apply a batch of replacements to the document.
 *
 * Ordering is the whole point: {@link sortForApplication} puts the highest start
 * offset first so that each edit only disturbs text no pending operation refers
 * to. An operation whose recorded `originalText` no longer matches what is in
 * the document is **skipped, not forced** — the document moved under the
 * suggestion, and overwriting on a stale offset would corrupt the user's text.
 *
 * @param operations The replacements to apply.
 * @returns What was applied and what was skipped.
 */
export async function applyOperations(
  operations: readonly UndoOperation[],
): Promise<ApplyReport> {
  const ordered = sortForApplication(operations);
  const report: ApplyReport = { applied: [], skipped: [] };
  if (ordered.length === 0) {
    return report;
  }

  await Word.run(async (context) => {
    for (const operation of ordered) {
      try {
        const range = await resolveRange(context, operation);
        
        range.load('text');
        await context.sync();
        console.log(`[INSTRUMENTATION 1] BEFORE INSERT: range.text='${range.text}'`);
        
        range.insertText(operation.newText, Word.InsertLocation.replace);
        console.log(`[INSTRUMENTATION 2] AFTER insertText CALLED`);
        
        await context.sync();
        console.log(`[INSTRUMENTATION 3] AFTER context.sync()`);
        
        range.load('text');
        await context.sync();
        console.log(`[INSTRUMENTATION 4] RE-LOADED RANGE: range.text='${range.text}'`);
        
        const body = context.document.body;
        body.load('text');
        await context.sync();
        console.log(`[INSTRUMENTATION 5] BODY TEXT AFTER SYNC: ${body.text}`);
        
        report.applied.push(operation);
      } catch (error) {
        report.skipped.push({
          operation,
          reason: error instanceof Error ? error.message : String(error),
        });
      }
    }
  });

  return report;
}

/**
 * Replace whatever is currently selected.
 *
 * @param text The replacement.
 */
export async function replaceSelection(text: string): Promise<void> {
  await Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.insertText(text, Word.InsertLocation.replace);
    await context.sync();
  });
}

/**
 * Insert text immediately after the current selection.
 *
 * @param text The text to insert.
 */
export async function insertAfterSelection(text: string): Promise<void> {
  await Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.insertText(text, Word.InsertLocation.after);
    await context.sync();
  });
}

/**
 * Locate the Word range a document-wide character offset addresses.
 *
 * Word.js has no "give me the range at character N" primitive, so the offset is
 * resolved through the paragraph structure: paragraphs are walked in order, the
 * one containing the offset is identified, and the exact occurrence of the
 * expected text inside it is searched for. Counting occurrences before the
 * offset is what disambiguates a word that appears several times in the same
 * paragraph — searching alone would return the first one every time.
 *
 * @param context The active Word request context.
 * @param operation The operation whose range is wanted.
 * @returns The range to replace.
 * @throws RangeResolutionError If the offset is outside the document, spans a
 *   paragraph boundary, or no longer holds the expected text.
 */
export async function resolveRange(
  context: Word.RequestContext,
  operation: UndoOperation,
): Promise<Word.Range> {
  const { rangeStart, rangeLength, originalText } = operation;
  const detail = {
    start: rangeStart,
    length: rangeLength,
    expected: originalText,
  };

  if (originalText.includes('\r') || originalText.includes('\n')) {
    throw new RangeResolutionError(
      'the range crosses a paragraph boundary',
      detail,
    );
  }

  const paragraphs = context.document.body.paragraphs;
  paragraphs.load('items/text');
  await context.sync();

  let bestParagraph: Word.Paragraph | null = null;
  let bestParagraphText = '';
  let bestLocal = -1;
  let minDistance = Infinity;

  let offset = 0;
  for (const paragraph of paragraphs.items) {
    const text = paragraph.text ?? '';
    const end = offset + text.length;

    const candidateLocal = rangeStart - offset;

    // Check exact match first at candidateLocal
    if (
      candidateLocal >= 0 &&
      candidateLocal + rangeLength <= text.length &&
      text.slice(candidateLocal, candidateLocal + rangeLength) === originalText
    ) {
      bestParagraph = paragraph;
      bestParagraphText = text;
      bestLocal = candidateLocal;
      minDistance = 0;
      break;
    }

    // If exact match at candidateLocal failed, search for originalText within this paragraph
    if (originalText.length > 0) {
      const idx = findBestLocalIndex(text, originalText, candidateLocal);
      if (idx !== -1) {
        const dist = Math.abs(offset + idx - rangeStart);
        if (dist < minDistance) {
          minDistance = dist;
          bestParagraph = paragraph;
          bestParagraphText = text;
          bestLocal = idx;
        }
      }
    }

    offset = end + PARAGRAPH_SEPARATOR.length;
  }

  if (bestParagraph !== null && bestLocal !== -1) {
    return findOccurrence(context, bestParagraph, bestParagraphText, bestLocal, originalText, detail);
  }

  const totalLength = offset > 0 ? offset - PARAGRAPH_SEPARATOR.length : 0;
  if (rangeStart >= totalLength) {
    throw new RangeResolutionError(
      'the offset is past the end of the document',
      detail,
    );
  }

  throw new RangeResolutionError(
    'the document no longer holds the expected text at that offset',
    detail,
  );
}

function findBestLocalIndex(text: string, needle: string, targetLocal: number): number {
  let bestIdx = -1;
  let minDiff = Infinity;
  let idx = text.indexOf(needle);
  while (idx !== -1) {
    const diff = Math.abs(idx - targetLocal);
    if (diff < minDiff) {
      minDiff = diff;
      bestIdx = idx;
    }
    idx = text.indexOf(needle, idx + 1);
  }
  return bestIdx;
}

async function findOccurrence(
  context: Word.RequestContext,
  paragraph: Word.Paragraph,
  paragraphText: string,
  local: number,
  expected: string,
  detail: { start: number; length: number; expected: string },
): Promise<Word.Range> {
  if (expected.length === 0) {
    // An insertion point has no text to search for; the paragraph range is the
    // only anchor Word.js offers without a match.
    return paragraph.getRange('Start');
  }

  const wanted = countOccurrencesBefore(paragraphText, expected, local);
  const results = paragraph.search(expected, {
    matchCase: true,
    matchWholeWord: false,
  });
  results.load('items');
  await context.sync();

  const range = results.items[wanted];
  if (range === undefined) {
    throw new RangeResolutionError(
      'the expected text was not found in its paragraph',
      detail,
    );
  }
  return range;
}

/**
 * How many times `needle` occurs in `haystack` strictly before `index`.
 *
 * Overlapping occurrences are counted the way `search` reports them: advancing
 * by one character, not by the needle's length.
 */
export function countOccurrencesBefore(
  haystack: string,
  needle: string,
  index: number,
): number {
  if (needle.length === 0) {
    return 0;
  }
  let count = 0;
  let cursor = haystack.indexOf(needle);
  while (cursor !== -1 && cursor < index) {
    count += 1;
    cursor = haystack.indexOf(needle, cursor + 1);
  }
  return count;
}

async function readBodyText(): Promise<string> {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.load('text');
    await context.sync();
    return body.text ?? '';
  });
}

function readSlicedText(): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    Office.context.document.getFileAsync(
      Office.FileType.Text,
      { sliceSize: SLICE_SIZE },
      (result) => {
        if (result.status !== Office.AsyncResultStatus.Succeeded) {
          reject(new Error(result.error?.message ?? 'getFileAsync failed'));
          return;
        }
        readAllSlices(result.value).then(resolve, reject);
      },
    );
  });
}

async function readAllSlices(file: Office.File): Promise<string> {
  // An array builder, joined once at the end: repeated string concatenation over
  // a book-length document is quadratic, and this path exists precisely for the
  // documents where that would show.
  const parts: string[] = [];
  try {
    for (let index = 0; index < file.sliceCount; index += 1) {
      parts.push(await readSlice(file, index));
    }
  } finally {
    file.closeAsync(() => undefined);
  }
  return parts.join('');
}

function readSlice(file: Office.File, index: number): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    file.getSliceAsync(index, (result) => {
      if (result.status !== Office.AsyncResultStatus.Succeeded) {
        reject(new Error(result.error?.message ?? `slice ${index} failed`));
        return;
      }
      const data: unknown = result.value.data;
      resolve(typeof data === 'string' ? data : decodeBytes(data));
    });
  });
}

function decodeBytes(data: unknown): string {
  if (data instanceof Uint8Array) {
    return new TextDecoder('utf-8').decode(data);
  }
  if (Array.isArray(data)) {
    return new TextDecoder('utf-8').decode(Uint8Array.from(data as number[]));
  }
  return String(data ?? '');
}
