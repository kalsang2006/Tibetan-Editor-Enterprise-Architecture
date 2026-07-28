/**
 * Keeping the pane's theme in step with Word's, and remembering the choice.
 *
 * Three sources, in priority order: what the user last chose (persisted in the
 * document's own settings, so it travels with the document), what Word reports,
 * and the OS preference. Word's `officeTheme` is only present on some hosts, so
 * every read is guarded — an add-in that throws during startup because a host
 * lacks an optional API shows the user a blank pane.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  type Theme,
  webDarkTheme,
  webLightTheme,
} from '@fluentui/react-components';

/** The persisted setting's key. */
export const THEME_SETTING_KEY = 'teeaTheme';

/** Which theme the pane is showing. */
export type ThemeName = 'light' | 'dark';

/** What the hook exposes. */
export interface OfficeTheme {
  name: ThemeName;
  /** The Fluent theme to hand `FluentProvider`. */
  theme: Theme;
  /** Switch and persist. */
  setTheme: (name: ThemeName) => void;
  /** Flip and persist. */
  toggle: () => void;
}

/**
 * Resolve and track the pane's theme.
 *
 * @param options.persist Whether to write the choice back to document settings.
 */
export function useOfficeTheme(options: { persist?: boolean } = {}): OfficeTheme {
  const { persist = true } = options;
  const [name, setName] = useState<ThemeName>(() => detectTheme());

  useEffect(() => {
    const media = globalThis.matchMedia?.('(prefers-color-scheme: dark)');
    if (media === undefined || stored() !== null) {
      // A stored choice is the user's, and must not be overwritten because the
      // OS switched to night mode underneath it.
      return undefined;
    }
    const onChange = (event: MediaQueryListEvent): void => {
      setName(event.matches ? 'dark' : 'light');
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const setTheme = useCallback(
    (next: ThemeName) => {
      setName(next);
      if (persist) {
        save(next);
      }
    },
    [persist],
  );

  const toggle = useCallback(() => {
    setTheme(name === 'dark' ? 'light' : 'dark');
  }, [name, setTheme]);

  return useMemo(
    () => ({
      name,
      theme: name === 'dark' ? webDarkTheme : webLightTheme,
      setTheme,
      toggle,
    }),
    [name, setTheme, toggle],
  );
}

/** Read the persisted choice, or `null` when the host offers no settings. */
export function stored(): ThemeName | null {
  try {
    const value = globalThis.Office?.context?.document?.settings?.get(
      THEME_SETTING_KEY,
    ) as unknown;
    return value === 'dark' || value === 'light' ? value : null;
  } catch {
    return null;
  }
}

/**
 * Resolve the theme from every available source.
 *
 * @returns The theme to start in.
 */
export function detectTheme(): ThemeName {
  const persisted = stored();
  if (persisted !== null) {
    return persisted;
  }
  const office = globalThis.Office as unknown as
    | { context?: { officeTheme?: { bodyBackgroundColor?: string } } }
    | undefined;
  const background = office?.context?.officeTheme?.bodyBackgroundColor;
  if (typeof background === 'string' && background.length > 0) {
    return isDark(background) ? 'dark' : 'light';
  }
  return globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches === true
    ? 'dark'
    : 'light';
}

/**
 * Whether a Word-reported background colour is a dark one.
 *
 * Word reports `#RRGGBB`. Relative luminance decides it rather than a table of
 * known theme colours, because Word's themes are user-customisable.
 */
export function isDark(hex: string): boolean {
  const cleaned = hex.replace('#', '');
  if (cleaned.length !== 6) {
    return false;
  }
  const red = Number.parseInt(cleaned.slice(0, 2), 16);
  const green = Number.parseInt(cleaned.slice(2, 4), 16);
  const blue = Number.parseInt(cleaned.slice(4, 6), 16);
  if ([red, green, blue].some(Number.isNaN)) {
    return false;
  }
  // Rec. 601 luma, which is what WCAG's own contrast guidance is built on.
  return (0.299 * red + 0.587 * green + 0.114 * blue) / 255 < 0.5;
}

function save(name: ThemeName): void {
  try {
    const settings = globalThis.Office?.context?.document?.settings;
    if (settings === undefined) {
      return;
    }
    settings.set(THEME_SETTING_KEY, name);
    settings.saveAsync(() => undefined);
  } catch {
    // Persisting a preference is a convenience. A host that refuses is not a
    // reason to fail the render.
  }
}
