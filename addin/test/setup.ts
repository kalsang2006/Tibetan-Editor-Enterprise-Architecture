import { ReadableStream } from 'node:stream/web';
import { TextDecoder, TextEncoder } from 'node:util';

import '@testing-library/jest-dom';

import { uninstallOfficeMock } from './officeMock';

/**
 * jsdom does not implement the WHATWG encoding or streams APIs. `SseParser` and
 * the fetch transport decode UTF-8 chunks off a `ReadableStream`, and Tibetan
 * text is exactly the case where a missing decoder would go unnoticed until it
 * mangled a multi-byte codepoint, so tests use the real Node implementations
 * rather than stubs.
 */
if (typeof globalThis.TextEncoder !== 'function') {
  Object.defineProperty(globalThis, 'TextEncoder', {
    writable: true,
    value: TextEncoder,
  });
}
if (typeof globalThis.TextDecoder !== 'function') {
  Object.defineProperty(globalThis, 'TextDecoder', {
    writable: true,
    value: TextDecoder,
  });
}
if (typeof globalThis.ReadableStream !== 'function') {
  Object.defineProperty(globalThis, 'ReadableStream', {
    writable: true,
    value: ReadableStream,
  });
}

/**
 * jsdom has no `matchMedia`, and the theme hook asks for one on mount. A
 * permanent light-mode answer keeps the default deterministic; a test that cares
 * overrides it.
 */
if (typeof globalThis.matchMedia !== 'function') {
  Object.defineProperty(globalThis, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

/**
 * Fluent UI's Griffel measures the DOM on first render. jsdom reports zero for
 * every box, which is harmless, but it also warns; silencing that keeps a real
 * warning visible.
 */
if (typeof globalThis.ResizeObserver !== 'function') {
  Object.defineProperty(globalThis, 'ResizeObserver', {
    writable: true,
    value: class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    },
  });
}

/**
 * `requestAnimationFrame` exists in jsdom but is tied to a timer the tests do
 * not advance. A microtask-backed frame keeps the streaming flush observable
 * with a plain `await`, which is what the assistant tests rely on.
 */
Object.defineProperty(globalThis, 'requestAnimationFrame', {
  writable: true,
  value: (callback: FrameRequestCallback): number => {
    queueMicrotask(() => callback(0));
    return 0;
  },
});

Object.defineProperty(globalThis, 'cancelAnimationFrame', {
  writable: true,
  value: (): void => undefined,
});

afterEach(() => {
  uninstallOfficeMock();
});
