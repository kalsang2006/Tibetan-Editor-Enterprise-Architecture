import { act, renderHook } from '@testing-library/react';

import { useOnlineStatus } from '../src/taskpane/hooks/useOnlineStatus';

describe('useOnlineStatus', () => {
  const originalDescriptor = Object.getOwnPropertyDescriptor(globalThis.navigator, 'onLine');

  afterEach(() => {
    if (originalDescriptor) {
      Object.defineProperty(globalThis.navigator, 'onLine', originalDescriptor);
    }
  });

  function setOnLine(value: boolean): void {
    Object.defineProperty(globalThis.navigator, 'onLine', {
      configurable: true,
      value,
    });
  }

  it('starts from navigator.onLine', () => {
    setOnLine(false);
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(false);
  });

  it('flips to false on an offline event', () => {
    setOnLine(true);
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(true);

    act(() => {
      globalThis.dispatchEvent(new Event('offline'));
    });

    expect(result.current).toBe(false);
  });

  it('flips back to true on an online event', () => {
    setOnLine(false);
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(false);

    act(() => {
      globalThis.dispatchEvent(new Event('online'));
    });

    expect(result.current).toBe(true);
  });
});
