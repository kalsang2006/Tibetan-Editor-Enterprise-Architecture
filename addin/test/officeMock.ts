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
  constructor(private readonly host: MockHost) {}

  get text(): string {
    return this.host.state.selection;
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
  constructor(private readonly host: MockHost) {}

  get text(): string {
    return this.host.state.paragraphs.join(SEPARATOR);
  }

  get paragraphs(): MockCollection<MockParagraph> {
    const collection = new MockCollection<MockParagraph>(() =>
      this.host.state.paragraphs.map((_text, index) => new MockParagraph(this.host, index)),
    );
    this.host.pending.push(collection);
    return collection;
  }

  load(_properties?: string): MockBody {
    return this;
  }
}

/** The scripted host. */
export class MockHost {
  readonly state: MockHostState;

  /** Collections awaiting the next `sync()`. */
  readonly pending: Array<MockCollection<unknown>> = [];

  constructor(paragraphs: string[], selection = '') {
    this.state = {
      paragraphs: [...paragraphs],
      selection,
      edits: [],
      syncs: 0,
      settings: {},
      slicesRead: [],
    };
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
    const body = new MockBody(this);
    return {
      document: {
        body,
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
 * @returns The host, so a test can inspect what the add-in did to it.
 */
export function installOfficeMock(
  paragraphs: string[],
  options: {
    selection?: string;
    withGetFileAsync?: boolean;
    sliceSize?: number;
  } = {},
): MockHost {
  const host = new MockHost(paragraphs, options.selection ?? '');
  const withGetFileAsync = options.withGetFileAsync ?? false;
  const sliceSize = options.sliceSize ?? 65536;

  const office: Record<string, unknown> = {
    onReady: (callback: () => void) => {
      callback();
      return Promise.resolve();
    },
    AsyncResultStatus: { Succeeded: 'succeeded', Failed: 'failed' },
    FileType: { Text: 'text', Compressed: 'compressed', Pdf: 'pdf' },
    context: {
      document: {
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
                const text = host.text;
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
