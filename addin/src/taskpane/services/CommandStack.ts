/**
 * The undo/redo transaction history for applied suggestions.
 *
 * Word has its own undo stack, but it does not know that accepting a batch of
 * twelve spelling fixes was *one* decision the user made. This stack does: a
 * command groups every operation applied together, so one undo reverses the
 * batch rather than making the user press it twelve times.
 *
 * Capacity is fixed at {@link MAX_HISTORY}. Beyond that the oldest command is
 * shifted out, which bounds memory: each operation retains both the original and
 * the replacement text, so an unbounded stack over a long editing session
 * retains an unbounded copy of the document.
 */

/** One reversible batch. */
export interface UndoCommand {
  /** Stable identity for this batch. */
  id: string;
  /** Which suggestions were applied together. */
  suggestionIds: string[];
  /** The text replacements, in the order they were applied. */
  operations: Array<{
    rangeStart: number;
    rangeLength: number;
    originalText: string;
    newText: string;
  }>;
}

/** One operation within a command. */
export type UndoOperation = UndoCommand['operations'][number];

/** The most commands retained. Older ones are discarded. */
export const MAX_HISTORY = 50;

/**
 * A bounded undo/redo history.
 *
 * Pure data: it records what was done and computes what reversing it means, but
 * it never touches the document. Applying and reversing is the caller's job,
 * which is what lets this class be tested without an Office host.
 */
export class CommandStack {
  private undoStack: UndoCommand[] = [];

  private redoStack: UndoCommand[] = [];

  constructor(private readonly capacity: number = MAX_HISTORY) {
    if (!Number.isInteger(capacity) || capacity < 1) {
      throw new RangeError('CommandStack capacity must be a positive integer');
    }
  }

  /** Whether there is anything to undo. */
  get canUndo(): boolean {
    return this.undoStack.length > 0;
  }

  /** Whether there is anything to redo. */
  get canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  /** How many commands are retained. */
  get size(): number {
    return this.undoStack.length;
  }

  /** How many commands can be redone. */
  get redoSize(): number {
    return this.redoStack.length;
  }

  /** The retained commands, oldest first. A copy: the history is not editable. */
  get history(): readonly UndoCommand[] {
    return this.undoStack.map(cloneCommand);
  }

  /**
   * Record a command as applied.
   *
   * Clears the redo stack, because redoing something that was recorded before a
   * new edit would replay it against a document that has since moved underneath
   * it. That is the standard editor contract and the safe one here: the
   * operations carry absolute offsets.
   *
   * @param command The batch that was just applied.
   */
  push(command: UndoCommand): void {
    if (command.operations.length === 0) {
      throw new RangeError('a command must carry at least one operation');
    }
    this.undoStack.push(cloneCommand(command));
    this.redoStack = [];
    while (this.undoStack.length > this.capacity) {
      this.undoStack.shift();
    }
  }

  /**
   * Take the most recent command off the undo stack.
   *
   * The caller reverses it and, having done so, the command sits on the redo
   * stack. Returns `undefined` when there is nothing to undo, rather than
   * throwing: a disabled button that gets clicked anyway is not an error.
   */
  popUndo(): UndoCommand | undefined {
    const command = this.undoStack.pop();
    if (command === undefined) {
      return undefined;
    }
    this.redoStack.push(command);
    return cloneCommand(command);
  }

  /** Take the most recent command off the redo stack and re-arm undo for it. */
  popRedo(): UndoCommand | undefined {
    const command = this.redoStack.pop();
    if (command === undefined) {
      return undefined;
    }
    this.undoStack.push(command);
    while (this.undoStack.length > this.capacity) {
      this.undoStack.shift();
    }
    return cloneCommand(command);
  }

  /** Look at what undo would reverse, without reversing it. */
  peekUndo(): UndoCommand | undefined {
    const command = this.undoStack[this.undoStack.length - 1];
    return command === undefined ? undefined : cloneCommand(command);
  }

  /** Look at what redo would replay, without replaying it. */
  peekRedo(): UndoCommand | undefined {
    const command = this.redoStack[this.redoStack.length - 1];
    return command === undefined ? undefined : cloneCommand(command);
  }

  /** Forget everything. Used when a new document is analysed. */
  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
  }
}

/**
 * Turn a command into the operations that reverse it.
 *
 * Two things happen at once, and both matter. The original and replacement text
 * swap, and the range *length* becomes the length of the text that is actually
 * in the document now — which is the replacement's length, not the original's.
 * Reversing with the original length would address the wrong span whenever a
 * suggestion changed the text's length, which is most of them.
 *
 * The operations are returned in descending start order for the same reason
 * {@link sortForApplication} sorts that way: see its documentation.
 *
 * @param command The command to reverse.
 * @returns Operations that restore the document to its prior state.
 */
export function invertCommand(command: UndoCommand): UndoOperation[] {
  return sortForApplication(
    command.operations.map((operation) => ({
      rangeStart: operation.rangeStart,
      rangeLength: operation.newText.length,
      originalText: operation.newText,
      newText: operation.originalText,
    })),
  );
}

/**
 * Order operations so that applying them in sequence cannot invalidate the
 * offsets of the ones not yet applied.
 *
 * Replacing text of one length with text of another shifts every character
 * after it. Applying from the **bottom of the document upward** means every
 * pending operation sits before the edit that just happened, so its recorded
 * offset is still correct. Applying top-down would require re-deriving every
 * subsequent offset after every single edit.
 *
 * @param operations The operations to order.
 * @returns The same operations, highest start offset first.
 */
export function sortForApplication(
  operations: readonly UndoOperation[],
): UndoOperation[] {
  return [...operations].sort((left, right) => {
    if (right.rangeStart !== left.rangeStart) {
      return right.rangeStart - left.rangeStart;
    }
    return right.rangeLength - left.rangeLength;
  });
}

/**
 * Whether two operations address overlapping text.
 *
 * A batch containing an overlap cannot be applied atomically: whichever runs
 * second would address text the first one replaced.
 */
export function overlaps(left: UndoOperation, right: UndoOperation): boolean {
  const leftEnd = left.rangeStart + left.rangeLength;
  const rightEnd = right.rangeStart + right.rangeLength;
  if (left.rangeLength === 0 || right.rangeLength === 0) {
    return false;
  }
  return left.rangeStart < rightEnd && right.rangeStart < leftEnd;
}

/**
 * Find every overlapping pair in a batch.
 *
 * @param operations The batch to check.
 * @returns Index pairs that conflict. Empty when the batch is safe.
 */
export function findConflicts(
  operations: readonly UndoOperation[],
): Array<[number, number]> {
  const conflicts: Array<[number, number]> = [];
  for (let i = 0; i < operations.length; i += 1) {
    for (let j = i + 1; j < operations.length; j += 1) {
      const left = operations[i];
      const right = operations[j];
      if (left !== undefined && right !== undefined && overlaps(left, right)) {
        conflicts.push([i, j]);
      }
    }
  }
  return conflicts;
}

function cloneCommand(command: UndoCommand): UndoCommand {
  return {
    id: command.id,
    suggestionIds: [...command.suggestionIds],
    operations: command.operations.map((operation) => ({ ...operation })),
  };
}
