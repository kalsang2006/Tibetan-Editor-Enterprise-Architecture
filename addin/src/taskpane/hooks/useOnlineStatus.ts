/**
 * Whether the host machine currently has a network connection.
 *
 * Distinct from {@link useDaemonTransport}'s reachability check: the daemon is
 * a process on this same machine, so a user can be offline (no network at
 * all) and still fully served by it, or online with the daemon simply not
 * running. The pane surfaces both signals separately rather than collapsing
 * them into one "not working" banner, because the fix is different for each --
 * "the daemon is offline-first by design; the network is not what it needs."
 */

import { useEffect, useState } from 'react';

/**
 * Track `navigator.onLine`, updated on the browser's own `online`/`offline`
 * events.
 *
 * @returns Whether the network is currently reported as up. Defaults to
 *   `true` in a host that exposes neither the property nor the events, so an
 *   add-in running somewhere `navigator.onLine` is unavailable never shows a
 *   false offline banner.
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState<boolean>(() => globalThis.navigator?.onLine ?? true);

  useEffect(() => {
    if (typeof globalThis.addEventListener !== 'function') {
      return undefined;
    }
    const onOnline = (): void => setOnline(true);
    const onOffline = (): void => setOnline(false);
    globalThis.addEventListener('online', onOnline);
    globalThis.addEventListener('offline', onOffline);
    return () => {
      globalThis.removeEventListener('online', onOnline);
      globalThis.removeEventListener('offline', onOffline);
    };
  }, []);

  return online;
}
