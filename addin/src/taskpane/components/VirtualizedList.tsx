/**
 * A windowed list, rendering only the rows near the viewport.
 *
 * Five hundred suggestion cards is five hundred mounted subtrees, and the first
 * paint of that is well past the 100 ms budget the pane holds itself to. Above
 * the threshold the list renders a spacer of the full scroll height and mounts
 * only the visible slice plus an overscan margin.
 *
 * Written rather than taken from a library on purpose: the behaviour is eighty
 * lines, and the add-in's dependency surface is a thing shipped to every user's
 * machine.
 */

import * as React from 'react';
import { makeStyles, tokens } from '@fluentui/react-components';

const useStyles = makeStyles({
  viewport: {
    overflowY: 'auto',
    overflowX: 'hidden',
    position: 'relative',
  },
  spacer: {
    position: 'relative',
    width: '100%',
  },
  window: {
    position: 'absolute',
    left: 0,
    right: 0,
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
  },
});

/** How many rows outside the viewport are mounted on each side. */
export const OVERSCAN = 4;

export interface VirtualizedListProps<T> {
  items: readonly T[];
  /** Fixed row height in pixels, including the gap beneath it. */
  itemHeight: number;
  /** Viewport height in pixels. */
  height: number;
  /** Stable key for a row. */
  keyOf: (item: T, index: number) => string;
  /** Render one row. */
  children: (item: T, index: number) => React.ReactNode;
  /** Accessible name for the scroll region. */
  label: string;
}

/**
 * Compute which rows must be mounted for a given scroll position.
 *
 * Pure, and exported, so the arithmetic is testable without a layout engine —
 * jsdom reports every element as zero-height, so a test that scrolled a real
 * list would be asserting against a fiction.
 */
export function windowFor(options: {
  scrollTop: number;
  itemHeight: number;
  height: number;
  count: number;
  overscan?: number;
}): { start: number; end: number; offset: number } {
  const { scrollTop, itemHeight, height, count } = options;
  const overscan = options.overscan ?? OVERSCAN;
  if (count === 0 || itemHeight <= 0) {
    return { start: 0, end: 0, offset: 0 };
  }
  const first = Math.floor(scrollTop / itemHeight);
  const visible = Math.ceil(height / itemHeight) + 1;
  const start = Math.max(0, first - overscan);
  const end = Math.min(count, first + visible + overscan);
  return { start, end, offset: start * itemHeight };
}

/**
 * Render `items` in a scrolling viewport, mounting only what is near it.
 */
export function VirtualizedList<T>(props: VirtualizedListProps<T>): JSX.Element {
  const { items, itemHeight, height, keyOf, children, label } = props;
  const styles = useStyles();
  const [scrollTop, setScrollTop] = React.useState(0);

  const { start, end, offset } = React.useMemo(
    () =>
      windowFor({
        scrollTop,
        itemHeight,
        height,
        count: items.length,
      }),
    [scrollTop, itemHeight, height, items.length],
  );

  const onScroll = React.useCallback((event: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

  const slice = items.slice(start, end);

  return (
    // `region`, not `list`, on the scrollable container: `tabIndex` makes it
    // keyboard-operable (the WAI-ARIA APG pattern for a scrollable area with no
    // other focusable ancestor), and `tabIndex` is only valid ARIA on an
    // interactive role. The `list` semantics belong on the element that
    // actually holds the items, one level in, which is also why the count is
    // left to the group header's badge rather than an `aria-rowcount` no
    // `list` role supports.
    <div
      className={styles.viewport}
      style={{ height }}
      onScroll={onScroll}
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      <div
        className={styles.spacer}
        style={{ height: items.length * itemHeight }}
      >
        <div
          className={styles.window}
          style={{ transform: `translateY(${offset}px)` }}
          role="list"
          aria-label={label}
        >
          {slice.map((item, index) => (
            <div role="listitem" key={keyOf(item, start + index)}>
              {children(item, start + index)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
