/**
 * The pane's keyboard shortcuts.
 *
 * Bound on the task pane's own document, not on Word's. The pane runs in a
 * webview; a key pressed with focus in the document never reaches it, and a key
 * pressed with focus in the pane never reaches Word. That separation is why
 * `Ctrl+Z` here reverses the pane's own batch rather than fighting Word's undo.
 *
 * `preventDefault` is called only for a binding that actually ran, so a
 * shortcut the pane does not handle still does whatever the webview would do.
 */

import { useEffect, useRef } from 'react';

/** What the pane binds. */
export interface ShortcutHandlers {
  /** `Ctrl+Z` / `Cmd+Z`. */
  onUndo?: () => void;
  /** `Ctrl+Y`, and `Ctrl+Shift+Z` for the platforms that use it. */
  onRedo?: () => void;
  /** `Ctrl+Enter`: commit the selected suggestion. */
  onCommit?: () => void;
  /** `Escape`: stop a running generation. */
  onStop?: () => void;
}

/** Which binding a key event matched, or `null`. */
export type ShortcutName = keyof ShortcutHandlers;

/**
 * Decide which binding an event matches.
 *
 * Exported so the mapping can be tested without mounting a component, and so
 * the same rules are used by any future command palette.
 *
 * @param event The keyboard event.
 * @returns The handler name, or `null` when nothing matches.
 */
export function matchShortcut(event: KeyboardEvent): ShortcutName | null {
  const modifier = event.ctrlKey || event.metaKey;
  const key = event.key.toLowerCase();

  if (key === 'escape') {
    return 'onStop';
  }
  if (!modifier) {
    return null;
  }
  if (key === 'enter') {
    return 'onCommit';
  }
  if (key === 'y') {
    return 'onRedo';
  }
  if (key === 'z') {
    return event.shiftKey ? 'onRedo' : 'onUndo';
  }
  return null;
}

/**
 * Bind the pane's shortcuts for as long as the component is mounted.
 *
 * The handlers are held in a ref and the listener is registered once. Binding a
 * fresh listener whenever a handler identity changed would re-attach on every
 * render, which is both wasteful and a way to drop a keypress mid-swap.
 *
 * @param handlers What each shortcut should do.
 * @param options.target Where to listen. Defaults to the pane's document.
 * @param options.enabled Whether the bindings are live.
 */
export function useKeyboardShortcuts(
  handlers: ShortcutHandlers,
  options: { target?: EventTarget | null; enabled?: boolean } = {},
): void {
  const { enabled = true } = options;
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    const target = options.target ?? globalThis.document;
    if (target === null || target === undefined) {
      return undefined;
    }

    const listener = (event: Event): void => {
      const keyboardEvent = event as KeyboardEvent;
      const name = matchShortcut(keyboardEvent);
      if (name === null) {
        return;
      }
      const handler = handlersRef.current[name];
      if (handler === undefined) {
        return;
      }
      event.preventDefault();
      handler();
    };

    target.addEventListener('keydown', listener);
    return () => target.removeEventListener('keydown', listener);
  }, [enabled, options.target]);
}
