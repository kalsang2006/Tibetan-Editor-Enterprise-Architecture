/**
 * A scripted stand-in for the Office.js host.
 *
 * `Office` and `Word` only exist inside a Word process, so a suite that needed
 * the real ones could never run in CI. This mock models the parts the add-in
 * actually uses — paragraphs, search, `insertText`, the selection, `getFileAsync`
 * slices and document settings — over a plain array of paragraph strings, and
 * mutates that array exactly as Word would mutate the document.
 *
 * It is deliberately a *model*, not a stub returning fixed values: the offset
 * arithmetic in `WordDocument` is the thing most likely to be wrong, and a stub
 * that always returned the same range would agree with a broken implementation.
 */

/** What the mock document holds and how it changed. */
export interface MockHostState {
  paragraphs: string[];
  selection: string;
  /** Every `insertText` the add-in performed, in order. */
  edits: Array<{ paragraph: number; start: number; length: number; text: string }>;
  /** How many times `context.sync()` was awaited. */
  syncs: number;
  /** Settings written through `Office.context.document.settings`. */
  settings: Record<string, unknown>;
  /** Slices handed out by `getFileAsync`, for asserting the read path. */
  slicesRead: number[];
}

/** What Word puts between paragraphs in `body.text`. */
const SEPARATOR = '\r';

class MockRange {
  constructor(
    private readonly host: MockHost,
    readonly paragraphIndex: number,
    readonly start: number,
    readonly length: number,
  ) {}

  get text(): string {
    const paragraph = this.host.state.paragraphs[this.paragraphIndex] ?? '';
    return paragraph.slice(this.start, this.start + this.length);
  }

  insertText(text: string, location: string): MockRange {
    this.host.replace(this.paragraphIndex, this.start, this.length, text, location);
    return this;
  }

  load(): MockRange {
    return this;
  }

  /** Word's Range.select(): move the UI selection onto this range's text. */
  select(): void {
    this.host.state.selection = this.text;
  }
}

class MockCollection<T> {
  private loaded: T[] = [];

  constructor(private readonly produce: () => T[]) {}

  get items(): T[] {
    return this.loaded;
  }

  load(_properties?: string): MockCollection<T> {
    return this;
  }

  /** Called by the mock context on sync. */
  refresh(): void {
    this.loaded = this.produce();
  }
}

class MockParagraph {
  constructor(
    private readonly host: MockHost,
    readonly index: number,
  ) {}

  get text(): string {
    return this.host.state.paragraphs[this.index] ?? '';
  }

  search(
    query: string,
    _options?: { matchCase?: boolean; matchWholeWord?: boolean },
  ): MockCollection<MockRange> {
    const collection = new MockCollection<MockRange>(() => {
      const ranges: MockRange[] = [];
      const text = this.text;
      let cursor = text.indexOf(query);
      while (cursor !== -1) {
        ranges.push(new MockRange(this.host, this.index, cursor, query.length));
        cursor = text.indexOf(query, cursor + 1);
      }
      return ranges;
    });
    this.host.pending.push(collection);
    return collection;
  }

  getRange(location?: string): MockRange {
    return location === 'Start'
      ? new MockRange(this.host, this.index, 0, 0)
      : new MockRange(this.host, this.index, 0, this.text.length);
  }

  load(_properties?: string): MockParagraph {
    return this;
  }
}

class MockSelection {
  /** The selection value at proxy creation, used by select() to restore it. */
  private readonly captured: string;

  constructor(private readonly host: MockHost) {
    this.captured = host.state.selection;
  }

  get text(): string {
    return this.host.state.selection;
  }

  /** Word's Range.select(): restore this selection's captured range. */
  select(): void {
    this.host.state.selection = this.captured;
  }

  insertText(text: string, location: string): MockSelection {
    this.host.state.edits.push({
      paragraph: -1,
      start: 0,
      length: this.host.state.selection.length,
      text,
    });
    if (location === 'Replace') {
      this.host.state.selection = text;
    } else {
      this.host.state.selection = `${this.host.state.selection}${text}`;
    }
    return this;
  }

  load(_properties?: string): MockSelection {
    return this;
  }
}

class MockBody {
  constructor(protected readonly host: MockHost) {}

  get text(): string {
    // With `emptyBody`, the host reports an empty body even though the
    // document (host.text) has content -- exactly the cold-start/buggy-host
    // situation readDocumentText's select-all fallback exists to recover from.
    if (this.host.emptyBody) {
      return '';
    }
    return this.host.state.paragraphs.join(SEPARATOR);
  }

  get paragraphs(): MockCollection<MockParagraph> {
    const collection = new MockCollection<MockParagraph>(() =>
      this.host.emptyBody
        ? []
        : this.host.state.paragraphs.map((_text, index) => new MockParagraph(this.host, index)),
    );
    this.host.pending.push(collection);
    return collection;
  }

  load(_properties?: string): MockBody {
    return this;
  }
}

/**
 * A body that also models Word's select-all capabilities (`Body.select()` and
 * `Body.getRange()`), used only when a test opts in with
 * `withSelectionFallback`. Kept out of the base `MockBody` so hosts without
 * these APIs stay faithfully model-less -- `applyOperations` branches on
 * `typeof body.getRange === 'function'`, so the default mock must not expose it.
 *
 * Note: because `applyOperations` would take its `getRange` path on this body,
 * and only the 'Start' location is modelled (numeric `getRange(start, length)`
 * calls throw, so operations would be skipped, not applied), do not combine
 * `withSelectionFallback` with `applyOperations` in the same test.
 */
class MockSelectableBody extends MockBody {
  /** Word's body.select(): select the whole body (its real text, not the reported one). */
  select(): void {
    this.host.state.selection = this.host.text;
  }

  /** Word's body.getRange(): only the 'Start' location is modelled (collapse to top). */
  getRange(location?: string): MockRange {
    if (location !== 'Start') {
      throw new Error('MockSelectableBody.getRange only models the Start location');
    }
    return new MockRange(this.host, 0, 0, 0);
  }
}

/** The scripted host. */
export class MockHost {
  readonly state: MockHostState;

  /** Collections awaiting the next `sync()`. */
  readonly pending: Array<MockCollection<unknown>> = [];

  /** Whether the body reports empty even though the document has text. */
  readonly emptyBody: boolean;

  /** The Body object Word.run batches see (selectable when configured). */
  readonly body: MockBody;

  constructor(
    paragraphs: string[],
    selection = '',
    options: { emptyBody?: boolean; withSelectionFallback?: boolean } = {},
  ) {
    this.state = {
      paragraphs: [...paragraphs],
      selection,
      edits: [],
      syncs: 0,
      settings: {},
      slicesRead: [],
    };
    this.emptyBody = options.emptyBody ?? false;
    this.body = options.withSelectionFallback ? new MockSelectableBody(this) : new MockBody(this);
  }

  /** The whole document as `body.text` would report it. */
  get text(): string {
    return this.state.paragraphs.join(SEPARATOR);
  }

  replace(
    paragraphIndex: number,
    start: number,
    length: number,
    text: string,
    location: string,
  ): void {
    const paragraph = this.state.paragraphs[paragraphIndex] ?? '';
    const next =
      location === 'After'
        ? `${paragraph.slice(0, start + length)}${text}${paragraph.slice(start + length)}`
        : `${paragraph.slice(0, start)}${text}${paragraph.slice(start + length)}`;
    this.state.paragraphs[paragraphIndex] = next;
    this.state.edits.push({ paragraph: paragraphIndex, start, length, text });
  }

  buildContext(): {
    document: { body: MockBody; getSelection: () => MockSelection };
    sync: () => Promise<void>;
  } {
    return {
      document: {
        body: this.body,
        getSelection: () => new MockSelection(this),
      },
      sync: async () => {
        this.state.syncs += 1;
        for (const collection of this.pending.splice(0)) {
          collection.refresh();
        }
      },
    };
  }
}

/**
 * Install `Office` and `Word` globals backed by a scripted document.
 *
 * @param paragraphs The document's paragraphs.
 * @param options.selection What `getSelection()` reports.
 * @param options.withGetFileAsync Whether the host exposes the slicing read.
 * @param options.sliceSize How large each slice is, for exercising re-stitching.
 * @param options.emptyBody Simulate a host whose body reports empty
 *   (`body.text === ''`, no paragraphs) even though the document has text.
 * @param options.withSelectionFallback Expose Word's select-all capabilities
 *   (`body.select()`, `body.getRange('Start')`, selection restore) so
 *   readDocumentText's tier-3 fallback can be exercised.
 * @returns The host, so a test can inspect what the add-in did to it.
 */
export function installOfficeMock(
  paragraphs: string[],
  options: {
    selection?: string;
    withGetFileAsync?: boolean;
    sliceSize?: number;
    /** What `getFileAsync` places between paragraphs (defaults to `\r`).
     *  Real hosts differ -- on Windows `getFileAsync` emits `\r\n`. */
    fileSeparator?: string;
    emptyBody?: boolean;
    withSelectionFallback?: boolean;
  } = {},
): MockHost {
  const host = new MockHost(paragraphs, options.selection ?? '', {
    emptyBody: options.emptyBody ?? false,
    withSelectionFallback: options.withSelectionFallback ?? false,
  });
  const withGetFileAsync = options.withGetFileAsync ?? false;
  const sliceSize = options.sliceSize ?? 65536;
  const fileSeparator = options.fileSeparator ?? SEPARATOR;

  const office: Record<string, unknown> = {
    onReady: (callback: () => void) => {
      callback();
      return Promise.resolve();
    },
    AsyncResultStatus: { Succeeded: 'succeeded', Failed: 'failed' },
    FileType: { Text: 'text', Compressed: 'compressed', Pdf: 'pdf' },
    context: {
      document: {
        getSelectedDataAsync: (_type: string, callback: (result: unknown) => void) => {
          callback({ status: 'succeeded', value: host.state.selection });
        },
        settings: {
          get: (key: string) => host.state.settings[key],
          set: (key: string, value: unknown) => {
            host.state.settings[key] = value;
          },
          saveAsync: (callback?: (result: unknown) => void) => {
            callback?.({ status: 'succeeded' });
          },
        },
        ...(withGetFileAsync
          ? {
              getFileAsync: (
                _type: string,
                _opts: { sliceSize: number },
                callback: (result: unknown) => void,
              ) => {
                const text = host.state.paragraphs.join(fileSeparator);
                const count = Math.max(1, Math.ceil(text.length / sliceSize));
                callback({
                  status: 'succeeded',
                  value: {
                    sliceCount: count,
                    getSliceAsync: (
                      index: number,
                      sliceCallback: (result: unknown) => void,
                    ) => {
                      host.state.slicesRead.push(index);
                      sliceCallback({
                        status: 'succeeded',
                        value: {
                          data: text.slice(index * sliceSize, (index + 1) * sliceSize),
                        },
                      });
                    },
                    closeAsync: (closeCallback?: () => void) => closeCallback?.(),
                  },
                });
              },
            }
          : {}),
      },
    },
  };

  const word: Record<string, unknown> = {
    InsertLocation: {
      replace: 'Replace',
      after: 'After',
      before: 'Before',
      start: 'Start',
      end: 'End',
    },
    run: async <T>(callback: (context: unknown) => Promise<T>): Promise<T> =>
      callback(host.buildContext()),
  };

  Object.assign(globalThis, { Office: office, Word: word });
  return host;
}

/** Remove the installed globals. */
export function uninstallOfficeMock(): void {
  Reflect.deleteProperty(globalThis, 'Office');
  Reflect.deleteProperty(globalThis, 'Word');
}
