/**
 * {@link CommandStack} as a React hook.
 *
 * The stack itself is deliberately not React state. It is a mutable object held
 * in a ref, and a monotonic counter is what re-renders the pane. Putting the
 * stack in `useState` would mean cloning fifty commands on every push, and the
 * commands retain document text.
 */

import { useCallback, useMemo, useRef, useState } from 'react';

import {
  CommandStack,
  MAX_HISTORY,
  type UndoCommand,
  invertCommand,
} from '../services/CommandStack';
import { applyOperations, type ApplyReport } from '../services/WordDocument';

/** What the hook exposes. */
export interface UndoStack {
  canUndo: boolean;
  canRedo: boolean;
  /** How many commands are retained, capped at {@link MAX_HISTORY}. */
  depth: number;
  /** Record a batch as applied. */
  pushCommand: (command: UndoCommand) => void;
  /** Reverse the most recent batch. */
  executeUndo: () => Promise<void>;
  /** Re-apply the most recently undone batch. */
  executeRedo: () => Promise<void>;
  /** Whether an undo or redo is in flight. */
  isBusy: boolean;
  /** What the last undo or redo actually did, or `null` before the first. */
  lastReport: ApplyReport | null;
  /** Forget everything. Called when a new document is analysed. */
  reset: () => void;
}

/** How a batch reaches the document. Injected so the hook is testable. */
export type OperationApplier = typeof applyOperations;

/**
 * Track applied batches and reverse them on request.
 *
 * @param options.capacity History depth. Defaults to {@link MAX_HISTORY}.
 * @param options.apply How operations reach the document. Defaults to Word.
 */
export function useUndoStack(
  options: { capacity?: number; apply?: OperationApplier } = {},
): UndoStack {
  const { capacity = MAX_HISTORY, apply = applyOperations } = options;
  const stackRef = useRef<CommandStack | null>(null);
  if (stackRef.current === null) {
    stackRef.current = new CommandStack(capacity);
  }
  const stack = stackRef.current;

  const [revision, setRevision] = useState(0);
  const [isBusy, setIsBusy] = useState(false);
  const [lastReport, setLastReport] = useState<ApplyReport | null>(null);
  const bump = useCallback(() => setRevision((value) => value + 1), []);

  const pushCommand = useCallback(
    (command: UndoCommand) => {
      stack.push(command);
      bump();
    },
    [stack, bump],
  );

  const executeUndo = useCallback(async () => {
    const command = stack.peekUndo();
    if (command === undefined) {
      return;
    }
    setIsBusy(true);
    try {
      const report = await apply(invertCommand(command));
      setLastReport(report);
      // The command only leaves the undo stack once the document has actually
      // been reversed. A failed undo that had already popped would leave the
      // history claiming a state the document is not in.
      stack.popUndo();
      bump();
    } finally {
      setIsBusy(false);
    }
  }, [stack, apply, bump]);

  const executeRedo = useCallback(async () => {
    const command = stack.peekRedo();
    if (command === undefined) {
      return;
    }
    setIsBusy(true);
    try {
      const report = await apply(command.operations);
      setLastReport(report);
      stack.popRedo();
      bump();
    } finally {
      setIsBusy(false);
    }
  }, [stack, apply, bump]);

  const reset = useCallback(() => {
    stack.clear();
    setLastReport(null);
    bump();
  }, [stack, bump]);

  return useMemo(
    () => ({
      canUndo: stack.canUndo,
      canRedo: stack.canRedo,
      depth: stack.size,
      pushCommand,
      executeUndo,
      executeRedo,
      isBusy,
      lastReport,
      reset,
    }),
    // `revision` is the dependency that matters, even though nothing in the
    // callback body reads it: the stack is mutated in place, so its own
    // reference never changes and cannot drive the memo on its own. Bumping
    // `revision` after every mutation is what forces recomputation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stack, revision, pushCommand, executeUndo, executeRedo, isBusy, lastReport, reset],
  );
}
