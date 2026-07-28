import { act, renderHook } from '@testing-library/react';

import {
  matchShortcut,
  useKeyboardShortcuts,
} from '../src/taskpane/hooks/useKeyboardShortcuts';
import {
  THEME_SETTING_KEY,
  detectTheme,
  isDark,
  stored,
  useOfficeTheme,
} from '../src/taskpane/hooks/useOfficeTheme';
import { installOfficeMock } from './officeMock';

function press(init: KeyboardEventInit): KeyboardEvent {
  return new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init });
}

describe('matchShortcut', () => {
  it.each([
    [{ key: 'z', ctrlKey: true }, 'onUndo'],
    [{ key: 'Z', metaKey: true }, 'onUndo'],
    [{ key: 'y', ctrlKey: true }, 'onRedo'],
    [{ key: 'z', ctrlKey: true, shiftKey: true }, 'onRedo'],
    [{ key: 'Enter', ctrlKey: true }, 'onCommit'],
    [{ key: 'Escape' }, 'onStop'],
  ] as const)('maps %o to %s', (init, expected) => {
    expect(matchShortcut(press(init))).toBe(expected);
  });

  it.each([
    { key: 'z' },
    { key: 'a', ctrlKey: true },
    { key: 'Enter' },
    { key: 'F5' },
  ])('does not claim %o', (init) => {
    expect(matchShortcut(press(init))).toBeNull();
  });
});

describe('useKeyboardShortcuts', () => {
  it('runs the bound handler and stops the default action', () => {
    const onUndo = jest.fn();
    renderHook(() => useKeyboardShortcuts({ onUndo }));

    const event = press({ key: 'z', ctrlKey: true });
    act(() => {
      document.dispatchEvent(event);
    });

    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it('leaves an unbound shortcut alone', () => {
    renderHook(() => useKeyboardShortcuts({ onUndo: jest.fn() }));

    const event = press({ key: 'y', ctrlKey: true });
    act(() => {
      document.dispatchEvent(event);
    });

    expect(event.defaultPrevented).toBe(false);
  });

  it('picks up a replaced handler without re-binding', () => {
    const first = jest.fn();
    const second = jest.fn();
    const { rerender } = renderHook(
      ({ onUndo }: { onUndo: () => void }) => useKeyboardShortcuts({ onUndo }),
      { initialProps: { onUndo: first } },
    );

    rerender({ onUndo: second });
    act(() => {
      document.dispatchEvent(press({ key: 'z', ctrlKey: true }));
    });

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('does nothing when disabled', () => {
    const onUndo = jest.fn();
    renderHook(() => useKeyboardShortcuts({ onUndo }, { enabled: false }));

    act(() => {
      document.dispatchEvent(press({ key: 'z', ctrlKey: true }));
    });

    expect(onUndo).not.toHaveBeenCalled();
  });

  it('unbinds on unmount', () => {
    const onUndo = jest.fn();
    const { unmount } = renderHook(() => useKeyboardShortcuts({ onUndo }));

    unmount();
    act(() => {
      document.dispatchEvent(press({ key: 'z', ctrlKey: true }));
    });

    expect(onUndo).not.toHaveBeenCalled();
  });

  it('binds Ctrl+Enter to commit and Escape to stop', () => {
    const onCommit = jest.fn();
    const onStop = jest.fn();
    renderHook(() => useKeyboardShortcuts({ onCommit, onStop }));

    act(() => {
      document.dispatchEvent(press({ key: 'Enter', ctrlKey: true }));
      document.dispatchEvent(press({ key: 'Escape' }));
    });

    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onStop).toHaveBeenCalledTimes(1);
  });
});

describe('isDark', () => {
  it.each(['#000000', '#1f1f1f', '#202020'])('reads %s as dark', (hex) => {
    expect(isDark(hex)).toBe(true);
  });

  it.each(['#ffffff', '#f3f2f1', '#e0e0e0'])('reads %s as light', (hex) => {
    expect(isDark(hex)).toBe(false);
  });

  it('is defensive about a malformed value', () => {
    expect(isDark('not-a-colour')).toBe(false);
    expect(isDark('#fff')).toBe(false);
  });
});

describe('useOfficeTheme', () => {
  it('defaults to light with no host and no preference', () => {
    const { result } = renderHook(() => useOfficeTheme({ persist: false }));

    expect(result.current.name).toBe('light');
  });

  it('reads a stored preference from document settings', () => {
    const host = installOfficeMock(['body']);
    host.state.settings[THEME_SETTING_KEY] = 'dark';

    expect(stored()).toBe('dark');
    expect(detectTheme()).toBe('dark');
  });

  it('ignores a stored value that is not a theme name', () => {
    const host = installOfficeMock(['body']);
    host.state.settings[THEME_SETTING_KEY] = 'chartreuse';

    expect(stored()).toBeNull();
  });

  it('persists a change through document settings', () => {
    const host = installOfficeMock(['body']);
    const { result } = renderHook(() => useOfficeTheme());

    act(() => result.current.setTheme('dark'));

    expect(host.state.settings[THEME_SETTING_KEY]).toBe('dark');
    expect(result.current.name).toBe('dark');
  });

  it('toggles between the two themes', () => {
    installOfficeMock(['body']);
    const { result } = renderHook(() => useOfficeTheme());

    act(() => result.current.toggle());
    expect(result.current.name).toBe('dark');

    act(() => result.current.toggle());
    expect(result.current.name).toBe('light');
  });

  it('does not write when persistence is off', () => {
    const host = installOfficeMock(['body']);
    const { result } = renderHook(() => useOfficeTheme({ persist: false }));

    act(() => result.current.setTheme('dark'));

    expect(host.state.settings[THEME_SETTING_KEY]).toBeUndefined();
  });

  it('hands a Fluent theme object to the provider', () => {
    const { result } = renderHook(() => useOfficeTheme({ persist: false }));

    expect(result.current.theme).toBeDefined();
    expect(typeof result.current.theme).toBe('object');
  });

  it('survives a host with no settings API', () => {
    expect(stored()).toBeNull();
    expect(() => detectTheme()).not.toThrow();
  });
});
