/**
 * Word document interaction helpers for the TEEA add‑in.
 * Uses Word.run (preferred) with Office.js fallback.
 */

export const SLICE_SIZE = 65536;
export const LARGE_DOCUMENT_THRESHOLD = 5000;

/**
 * Retry delays (ms) for the Word.run body read in {@link readDocumentText}.
 * Hoisted so tests can shrink them; the first attempt runs immediately.
 */
export const READ_RETRY_BACKOFF_MS = [0, 300, 700];

/**
 * How long to wait for the getFileAsync callback before treating tier 1 as
 * failed and falling through. Guards against hosts that expose the method but
 * never invoke the callback (which would otherwise hang the whole read).
 */
export const GET_FILE_ASYNC_TIMEOUT_MS = 1500;

export interface Operation {
  rangeStart: number;
  rangeLength: number;
  originalText: string;
  newText: string;
  reason?: string;
}

export interface ApplyReport {
  applied: Operation[];
  skipped: Operation[];
}

/**
 * Read the entire document text using the Word JavaScript API.
 *
 * Five-tier fallback chain, so a document that reads empty on one code path
 * still gets its text:
 *   1. Office.js getFileAsync – opportunistic, only when the host exposes it.
 *   2. Word.run body read – loads body.text + paragraph text; retried with
 *      backoff (300ms, 700ms) to ride out cold-start races where the document
 *      model is not yet hydrated.
 *   3. Select-all fallback – body.select() then read getSelection().text,
 *      restoring the original selection afterwards so the user is never left
 *      with a full-document highlight.
 *   4. Story extensions – text boxes/shapes, headers/footers and
 *      footnotes/endnotes live outside the main body story, so they are read
 *      separately (feature-detected; not all hosts expose them).
 *   5. Exhausted – return "" only after every tier above failed, with a
 *      detailed warning of what was tried.
 *
 * Returns empty string only after all five tiers have been exhausted.
 */
export async function readDocumentText(options?: { sliceSize?: number }): Promise<string> {
  const office = (window as any).Office || (globalThis as any).Office;
  // Collected per-tier failure reasons, reported together only if every tier
  // fails, so an exhausted read is distinguishable from a truly empty document.
  const reasons: string[] = [];

  // ---- Tier 1: Office.js getFileAsync (opportunistic) ---------------------
  if (office?.context?.document && typeof office.context.document.getFileAsync === 'function') {
    // Tracks whether a specific failure was already recorded, so the generic
    // "returned empty text" reason below is not pushed twice on partial failure.
    let tier1SpecificFailure = false;
    try {
      const text = await new Promise<string>((resolve) => {
        console.log('[TEEA] readDocumentText: tier 1/5 – using Office.js getFileAsync');
        const sliceSize = options?.sliceSize || SLICE_SIZE;
        // If the host never calls back (or calls back without a result), bail
        // out after a timeout so tiers 2-5 still get a chance to read.
        const timeoutId = setTimeout(() => {
          tier1SpecificFailure = true;
          reasons.push(`getFileAsync timed out after ${GET_FILE_ASYNC_TIMEOUT_MS}ms`);
          console.warn(`[TEEA] readDocumentText: getFileAsync timed out after ${GET_FILE_ASYNC_TIMEOUT_MS}ms`);
          resolve('');
        }, GET_FILE_ASYNC_TIMEOUT_MS);
        const settle = (value: string) => {
          clearTimeout(timeoutId);
          resolve(value);
        };
        office.context.document.getFileAsync('text', { sliceSize }, (result: any) => {
          if (result.status !== 'succeeded') {
            tier1SpecificFailure = true;
            reasons.push(`getFileAsync failed: ${result.error?.message ?? 'unknown error'}`);
            console.warn('[TEEA] readDocumentText: getFileAsync failed', result.error?.message);
            settle('');
            return;
          }
          const file = result.value;
          let fullText = '';
          let received = 0;
          const processSlice = (index: number) => {
            file.getSliceAsync(index, (sliceResult: any) => {
              if (sliceResult.status !== 'succeeded') {
                tier1SpecificFailure = true;
                file.closeAsync();
                reasons.push(`getSliceAsync failed: ${sliceResult.error?.message ?? 'unknown error'}`);
                console.warn('[TEEA] readDocumentText: getSliceAsync failed', sliceResult.error?.message);
                settle('');
                return;
              }
              const sliceData = sliceResult.value.data;
              fullText += sliceData;
              received++;
              if (received < file.sliceCount) {
                processSlice(received);
              } else {
                file.closeAsync();
                settle(fullText || '');
              }
            });
          };
          processSlice(0);
        });
      });
      if (text.trim().length > 0) {
        console.log(`[TEEA] readDocumentText: tier 1 succeeded (${text.length} chars)`);
        return canonicalizeDocumentText(text);
      }
      if (!tier1SpecificFailure) {
        reasons.push('getFileAsync returned empty text');
      }
      console.warn('[TEEA] readDocumentText: tier 1 returned empty text');
    } catch (error) {
      reasons.push(`getFileAsync threw: ${error instanceof Error ? error.message : String(error)}`);
      console.warn('[TEEA] readDocumentText: tier 1 threw', error);
    }
  } else {
    reasons.push('getFileAsync not available on this host');
    console.log('[TEEA] readDocumentText: tier 1 skipped – getFileAsync not available on this host');
  }

  // ---- Tier 2: Word.run body read, retried for cold-start races -----------
  if (typeof Word !== 'undefined' && Word.run) {
    for (let attempt = 0; attempt < READ_RETRY_BACKOFF_MS.length; attempt++) {
      if (attempt > 0) {
        await sleep(READ_RETRY_BACKOFF_MS[attempt] ?? 0);
      }
      try {
        const text = await Word.run(async (context) => {
          const body = context.document.body;
          body.load('text');
          const paragraphs = body.paragraphs;
          // Load the paragraph text too: `load('items')` alone only gives item
          // proxies, so `p.text` would be unloaded when reconstructing below.
          paragraphs.load('items, text');
          await context.sync();

          console.log('[TEEA] Word.run: body.text length =', body.text ? body.text.length : 0);
          console.log('[TEEA] Word.run: paragraph count =', paragraphs.items ? paragraphs.items.length : 0);

          if (body.text && body.text.trim().length > 0) {
            return body.text;
          }
          // If body.text is empty but paragraphs exist, reconstruct from them.
          if (paragraphs.items && paragraphs.items.length > 0) {
            console.log('[TEEA] Word.run: reconstructing from paragraphs');
            return canonicalizeDocumentText(
              paragraphs.items
                .map((p) => p.text || '')
                .join('\n')
                .trim(),
            );
          }
          return '';
        });

        if (text && text.trim().length > 0) {
          console.log(`[TEEA] readDocumentText: tier 2 succeeded on attempt ${attempt + 1} (${text.length} chars)`);
          return canonicalizeDocumentText(text);
        }
        reasons.push(`Word.run attempt ${attempt + 1} returned empty body`);
        console.warn(`[TEEA] readDocumentText: tier 2 attempt ${attempt + 1} returned empty`);
      } catch (error) {
        reasons.push(`Word.run attempt ${attempt + 1} threw: ${error instanceof Error ? error.message : String(error)}`);
        console.warn(`[TEEA] readDocumentText: tier 2 attempt ${attempt + 1} failed`, error);
      }
    }

    // ---- Tier 3: select-all, read selection, restore selection ------------
    try {
      const text = await Word.run(async (context) => {
        // Save the user's current selection first so it can be restored. The
        // proxy itself is what gets re-selected later; no property needs loading.
        const original = context.document.getSelection();

        // Select the whole body, then read the selection text.
        context.document.body.select();
        await context.sync();
        const selection = context.document.getSelection();
        selection.load('text');
        await context.sync();
        const selected = selection.text || '';

        // Restore the original selection so the user is not left with a
        // full-document highlight. If the saved range is no longer valid,
        // collapse to the start of the document as a safe fallback.
        try {
          original.select();
          await context.sync();
        } catch {
          try {
            context.document.body.getRange('Start').select();
            await context.sync();
          } catch (collapseError) {
            console.warn('[TEEA] readDocumentText: selection restore/collapse failed', collapseError);
          }
        }

        return canonicalizeDocumentText(selected);
      });
      if (text && text.trim().length > 0) {
        console.log(`[TEEA] readDocumentText: tier 3 (select-all) succeeded (${text.length} chars)`);
        return text;
      }
      reasons.push('select-all read returned empty');
      console.warn('[TEEA] readDocumentText: tier 3 returned empty');
    } catch (error) {
      reasons.push(`select-all threw: ${error instanceof Error ? error.message : String(error)}`);
      console.warn('[TEEA] readDocumentText: tier 3 failed', error);
    }

    // ---- Tier 4: story extensions (text boxes, headers/footers, notes) ----
    try {
      const text = await Word.run(async (context) => {
        const body = context.document.body as any;
        const parts: string[] = [];
        const push = (value: string | undefined) => {
          if (value && value.trim().length > 0) {
            parts.push(value);
          }
        };

        // 4a. Text boxes / shapes (WordApi 1.5+)
        if (body.shapes && typeof body.shapes.load === 'function') {
          try {
            body.shapes.load('items');
            await context.sync();
            for (const shape of body.shapes.items || []) {
              try {
                const frame = shape.textFrame;
                if (frame && frame.body) {
                  frame.body.load('text');
                  await context.sync();
                  push(frame.body.text);
                }
              } catch {
                // Shape without a text frame (picture, canvas, etc.)
              }
            }
          } catch (error) {
            console.warn('[TEEA] readDocumentText: tier 4 shapes failed', error);
          }
        }

        // 4b. Headers and footers
        if (body.sections && typeof body.sections.load === 'function') {
          try {
            const HeaderFooterType = (Word as any).HeaderFooterType || {};
            const primaryType = HeaderFooterType.primary || 'primary';
            body.sections.load('items');
            await context.sync();
            for (const section of body.sections.items || []) {
              try {
                if (typeof section.getHeader === 'function') {
                  const header = section.getHeader(primaryType);
                  header.load('text');
                  await context.sync();
                  push(header.text);
                }
              } catch {
                // Header missing / unsupported on this host
              }
              try {
                if (typeof section.getFooter === 'function') {
                  const footer = section.getFooter(primaryType);
                  footer.load('text');
                  await context.sync();
                  push(footer.text);
                }
              } catch {
                // Footer missing / unsupported on this host
              }
            }
          } catch (error) {
            console.warn('[TEEA] readDocumentText: tier 4 sections failed', error);
          }
        }

        // 4c. Footnotes and endnotes (WordApi 1.5+)
        for (const notes of [body.footnotes, body.endnotes]) {
          if (notes && typeof notes.load === 'function') {
            try {
              notes.load('items');
              await context.sync();
              for (const note of notes.items || []) {
                try {
                  if (note.body) {
                    note.body.load('text');
                    await context.sync();
                    push(note.body.text);
                  }
                } catch {
                  // Note without a readable body
                }
              }
            } catch (error) {
              console.warn('[TEEA] readDocumentText: tier 4 notes failed', error);
            }
          }
        }

        return canonicalizeDocumentText(parts.join('\n'));
      });
      if (text && text.trim().length > 0) {
        console.log(`[TEEA] readDocumentText: tier 4 (story extensions) succeeded (${text.length} chars)`);
        return text;
      }
      reasons.push('story extensions returned empty');
      console.warn('[TEEA] readDocumentText: tier 4 returned empty');
    } catch (error) {
      reasons.push(`story extensions threw: ${error instanceof Error ? error.message : String(error)}`);
      console.warn('[TEEA] readDocumentText: tier 4 failed', error);
    }
  } else {
    reasons.push('Word.run not available');
    console.warn('[TEEA] readDocumentText: tiers 2-4 skipped – Word.run not available');
  }

  // ---- Tier 5: exhausted --------------------------------------------------
  // Reached only when every tier above failed; report exactly what was tried so
  // a genuinely empty document is distinguishable from an unreadable one.
  console.warn(
    '[TEEA] readDocumentText: all 5 tiers exhausted – returning empty string. Reasons: ' +
      reasons.join(' | '),
  );
  return '';
}

/** Wait for the given number of milliseconds (used by the tier 2 retry backoff). */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Reduce a document text snapshot to one canonical paragraph representation
 * before it is handed to the daemon (or any consumer that derives offsets).
 *
 * The read tiers disagree on paragraph breaks: `getFileAsync` returns `\r\n`
 * on Windows, `body.text` uses `\r`, and the paragraph-reconstruction fallback
 * joins with `\n`. The daemon computes character offsets against exactly the
 * string it receives, while `applyOperations` reconstructs document offsets
 * assuming every paragraph boundary is exactly ONE character (`pLen + 1` per
 * paragraph). If the analysis text used two characters per boundary (CRLF),
 * every operation after the first paragraph is off by one character per
 * preceding paragraph and the whole batch is skipped with
 * "Original text no longer holds at specified range". Collapsing every break
 * to a single `\r` (Word's native paragraph mark, which the apply-time math
 * models) makes the analysis text and the apply-time reconstruction agree, so
 * offsets stay valid regardless of which tier produced the snapshot.
 */
export function canonicalizeDocumentText(text: string): string {
  return text
    .replace(/^\uFEFF/, '') // a BOM is an encoding artifact, not document content
    .replace(/\r\n/g, '\r')
    .replace(/\n/g, '\r');
}

/**
 * Read the currently selected text (if any).
 */
export async function readSelectionText(): Promise<string> {
  return new Promise((resolve, reject) => {
    const office = (window as any).Office;
    if (!office?.context?.document) {
      reject(new Error('Office.context.document not available'));
      return;
    }
    office.context.document.getSelectedDataAsync('text', (result: any) => {
      if (result.status === 'succeeded') resolve(result.value || '');
      else reject(new Error(result.error?.message || 'Failed to read selection'));
    });
  });
}

/**
 * Check if document length exceeds a threshold (e.g., for truncation).
 */
export function isLargeDocument(length: number, threshold = LARGE_DOCUMENT_THRESHOLD): boolean {
  return length > threshold;
}

/**
 * Apply a batch of text replacement operations to the Word document.
 *
 * Operations must be sorted in descending `rangeStart` order to ensure
 * safe application without offset invalidation. The caller is responsible
 * for this ordering.
 *
 * @param operations - Array of text replacements.
 * @returns A report detailing which operations were applied and which were skipped.
 */
export async function applyOperations(operations: Operation[]): Promise<ApplyReport> {
  // 1. Handle empty batch early.
  if (!operations || operations.length === 0) {
    return { applied: [], skipped: [] };
  }

  // 2. Guard against missing Word API.
  if (typeof Word === 'undefined' || typeof Word.run !== 'function') {
    console.warn('[TEEA] Word.run not available; operations skipped.');
    return { applied: [], skipped: operations };
  }

  console.log('[TEEA] applyOperations: received', operations.length, 'operations');

  try {
    // 3. Run the Word batch.
    return await Word.run(async (context) => {
      const applied: Operation[] = [];
      const skipped: Operation[] = [];

      // Sort operations bottom-up (descending rangeStart) so earlier offsets stay
      // valid: replacing text at the bottom of the document first means every
      // pending operation still sits before the edit that just happened.
      const sorted = [...operations].sort((a, b) => (b.rangeStart ?? 0) - (a.rangeStart ?? 0));

      // 4. Iterate over operations (in descending order).
      //
      // Word's Body.getRange() does not accept numeric character offsets -- it
      // takes a Word.RangeLocation enum string ('Whole' | 'Start' | 'End' | ...),
      // so addressing a range with `getRange(start, length)` throws and silently
      // swallows the whole batch as skipped. The document is therefore addressed
      // through its paragraphs instead: each operation's character offset is
      // resolved to a paragraph + local offset, verified against `originalText`,
      // and the exact occurrence replaced. Offsets are recomputed against the
      // *current* document per operation, which keeps them correct even after an
      // edit below shifted the text above.
      for (const op of sorted) {
        try {
          // 4a. Basic input validation.
          if (
            op.rangeStart < 0 ||
            op.rangeLength < 0 ||
            op.newText === undefined ||
            op.newText === null
          ) {
            console.warn('[TEEA] Skipping invalid operation:', op);
            skipped.push({ ...op, reason: 'Invalid range or operation input' });
            continue;
          }

          // 4b. Resolve the character offset against the current paragraphs.
          const body = context.document.body;
          const paragraphs = body.paragraphs;
          if (!paragraphs) {
            skipped.push({ ...op, reason: 'No paragraphs found' });
            continue;
          }
          paragraphs.load('items, text');
          await context.sync();

          let totalDocLength = 0;
          const pOffsets: Array<{ pIndex: number; start: number; end: number; pNode: any }> = [];

          for (let i = 0; i < paragraphs.items.length; i++) {
            const p = paragraphs.items[i];
            if (p === undefined) {
              continue;
            }
            const pLen = (p.text || '').length;
            pOffsets.push({
              pIndex: i,
              start: totalDocLength,
              end: totalDocLength + pLen,
              pNode: p,
            });
            totalDocLength += pLen + 1;
          }

          const start = op.rangeStart ?? 0;
          const length = op.rangeLength ?? (op.originalText ? op.originalText.length : 0);

          if (start >= totalDocLength) {
            skipped.push({ ...op, reason: 'Offset past the end of the document' });
            continue;
          }

          const targetP = pOffsets.find((p) => start >= p.start && start <= p.end);
          if (!targetP || start + length > targetP.end) {
            if (op.originalText) {
              const rescue = await findSingleOccurrence(context, paragraphs, op.originalText);
              if (rescue !== null) {
                console.warn(
                  `[TEEA] rescued offset drift for "${op.originalText}" via document-wide search`,
                );
                rescue.insertText(op.newText, Word.InsertLocation.replace);
                applied.push(op);
                continue;
              }
            }
            skipped.push({
              ...op,
              reason: !targetP
                ? 'Offset past the end of the document'
                : 'Range crosses a paragraph boundary',
            });
            continue;
          }

          const localStart = start - targetP.start;
          const pText = targetP.pNode.text || '';
          const actualText = pText.substring(localStart, localStart + length);

          if (op.originalText && actualText !== op.originalText) {
            // The offset no longer addresses the text recorded at analysis
            // time. The primary cause is a paragraph-separator width
            // difference between the analysis snapshot and this reconstruction
            // (CRLF vs single-char) -- canonicalizeDocumentText eliminates
            // that on the read side. As a second line of defence, rescue the
            // operation when the original text is found exactly once in the
            // whole document, e.g. a small edit above shifted the offset.
            console.warn(
              `[TEEA] offset check failed at ${op.rangeStart}: expected "${op.originalText}" but found "${actualText}"`,
            );
            const rescue = await findSingleOccurrence(context, paragraphs, op.originalText);
            if (rescue !== null) {
              console.warn(
                `[TEEA] rescued offset drift for "${op.originalText}" via document-wide search`,
              );
              rescue.insertText(op.newText, Word.InsertLocation.replace);
              applied.push(op);
              continue;
            }
            skipped.push({ ...op, reason: 'Original text no longer holds at specified range' });
            continue;
          }

          // Diagnostic: log the exact offsets right before the replacement is
          // applied, so a stale or mismatched range is visible at apply time.
          console.log(
            `[TEEA] first operation: rangeStart=${op.rangeStart}, rangeLength=${op.rangeLength}, originalText="${op.originalText}", newText="${op.newText}"`,
          );

          const occIndex = countOccurrencesBefore(pText, op.originalText || actualText, localStart);
          const searchResults = targetP.pNode.search(op.originalText || actualText, { matchCase: true });
          searchResults.load('items');
          await context.sync();

          if (searchResults.items && searchResults.items[occIndex]) {
            searchResults.items[occIndex].insertText(op.newText, Word.InsertLocation.replace);
            applied.push(op);
          } else if (searchResults.items && searchResults.items.length > 0) {
            searchResults.items[0].insertText(op.newText, Word.InsertLocation.replace);
            applied.push(op);
          } else {
            skipped.push({ ...op, reason: 'Original text search failed in paragraph' });
          }
        } catch (error) {
          // 4c. Per-operation failure: log, skip, and continue.
          console.warn('[TEEA] Skipping operation due to error:', op, error);
          skipped.push({ ...op, reason: String(error) });
        }
      }

      // 5. Commit all changes to the document in one sync.
      await context.sync();

      // 6. Log summary.
      console.log(
        '[TEEA] applyOperations: applied',
        applied.length,
        'skipped',
        skipped.length,
      );

      // 7. Return the detailed report.
      return { applied, skipped };
    });
  } catch (error) {
    // 8. Top-level error recovery (e.g., host context lost).
    console.error('[TEEA] Word.run failed:', error);
    return { applied: [], skipped: operations };
  }
}

/**
 * Replace active document selection.
 */
export async function replaceSelection(text: string): Promise<void> {
  if (typeof Word !== 'undefined' && typeof Word.run === 'function') {
    return Word.run(async (context) => {
      const selection = context.document.getSelection();
      selection.insertText(text, Word.InsertLocation.replace);
      await context.sync();
    });
  }
}

/**
 * Insert text after current selection.
 */
export async function insertAfterSelection(text: string): Promise<void> {
  if (typeof Word !== 'undefined' && typeof Word.run === 'function') {
    return Word.run(async (context) => {
      const selection = context.document.getSelection();
      selection.insertText(text, Word.InsertLocation.after);
      await context.sync();
    });
  }
}

/**
 * Highlight plagiarism matches in Word document.
 */
export async function highlightPlagiarismMatches(
  matches: Array<{ start: number; length: number; originalText: string }>,
  color = '#FFF200',
): Promise<void> {
  if (typeof Word !== 'undefined' && typeof Word.run === 'function') {
    return Word.run(async (context) => {
      const body = context.document.body;
      for (const match of matches) {
        if (match.originalText) {
          const results = body.search(match.originalText, { matchCase: true });
          results.load('items');
          await context.sync();
          for (const range of results.items) {
            range.font.highlightColor = color;
          }
        }
      }
      await context.sync();
    });
  }
}

/**
 * Clear plagiarism highlights.
 */
export async function clearPlagiarismHighlights(
  matches: Array<{ start: number; length: number; originalText: string }>,
): Promise<void> {
  return highlightPlagiarismMatches(matches, 'NoColor');
}

/**
 * Insert footnote citation.
 */
export async function insertFootnoteCitation(citation: string): Promise<void> {
  if (typeof Word !== 'undefined' && typeof Word.run === 'function') {
    return Word.run(async (context) => {
      const selection = context.document.getSelection();
      selection.insertFootnote(citation);
      await context.sync();
    });
  }
}

/**
 * Find the one range in the whole document whose text equals `needle`.
 *
 * Used only as a rescue path after the offset check has failed, when the
 * recorded offset is no longer trustworthy. Returns `null` unless the needle
 * occurs exactly once across every paragraph: a document-wide search cannot
 * tell which instance a stale offset meant when the needle repeats, so an
 * ambiguous match must not be applied by guesswork. Searching the whole body
 * (not just the paragraph the drifting offset happened to resolve to) is what
 * keeps this safe -- a mis-resolved paragraph containing the text once must
 * not become a wrong-location replacement.
 */
async function findSingleOccurrence(
  context: { sync: () => Promise<void> },
  paragraphs: { items?: Array<{ search?: (q: string, o?: { matchCase?: boolean }) => { load: (p?: string) => void; items?: unknown[] } }> },
  needle: string,
): Promise<{ insertText: (text: string, location: string) => void } | null> {
  if (!needle || needle.length === 0) {
    return null;
  }
  let found: { insertText: (text: string, location: string) => void } | null = null;
  for (const paragraph of paragraphs.items ?? []) {
    if (paragraph === undefined || paragraph.search === undefined) {
      continue;
    }
    const results = paragraph.search(needle, { matchCase: true });
    results.load('items');
    await context.sync();
    for (const item of results.items ?? []) {
      const range = item as { insertText: (text: string, location: string) => void };
      if (found !== null) {
        // A second occurrence anywhere in the document: ambiguous, do not guess.
        return null;
      }
      found = range;
    }
  }
  return found;
}

/**
 * Count occurrences of a string before an index.
 */
export function countOccurrencesBefore(haystack: string, needle: string, index: number): number {
  if (needle.length === 0) return 0;
  let count = 0;
  let cursor = haystack.indexOf(needle);
  while (cursor !== -1 && cursor < index) {
    count += 1;
    cursor = haystack.indexOf(needle, cursor + 1);
  }
  return count;
}
