import {
  CommandStack,
  MAX_HISTORY,
  findConflicts,
  invertCommand,
  overlaps,
  sortForApplication,
  type UndoCommand,
} from '../src/taskpane/services/CommandStack';

function command(index: number, overrides: Partial<UndoCommand> = {}): UndoCommand {
  return {
    id: `cmd-${index}`,
    suggestionIds: [`sug-${index}`],
    operations: [
      {
        rangeStart: index * 10,
        rangeLength: 3,
        originalText: 'old',
        newText: 'new',
      },
    ],
    ...overrides,
  };
}

describe('CommandStack capacity', () => {
  it('starts empty', () => {
    const stack = new CommandStack();

    expect(stack.canUndo).toBe(false);
    expect(stack.canRedo).toBe(false);
    expect(stack.size).toBe(0);
  });

  it('retains exactly fifty commands by default', () => {
    const stack = new CommandStack();

    for (let index = 0; index < 50; index += 1) {
      stack.push(command(index));
    }

    expect(stack.size).toBe(MAX_HISTORY);
    expect(stack.size).toBe(50);
  });

  it('shifts the oldest command out on overflow', () => {
    const stack = new CommandStack();

    for (let index = 0; index < 60; index += 1) {
      stack.push(command(index));
    }

    expect(stack.size).toBe(50);
    expect(stack.history[0]?.id).toBe('cmd-10');
    expect(stack.history[49]?.id).toBe('cmd-59');
  });

  it('undoes all fifty retained commands in reverse order', () => {
    const stack = new CommandStack();
    for (let index = 0; index < 50; index += 1) {
      stack.push(command(index));
    }

    const seen: string[] = [];
    while (stack.canUndo) {
      seen.push(stack.popUndo()!.id);
    }

    expect(seen).toHaveLength(50);
    expect(seen[0]).toBe('cmd-49');
    expect(seen[49]).toBe('cmd-0');
  });

  it('redoes all fifty back in the original order', () => {
    const stack = new CommandStack();
    for (let index = 0; index < 50; index += 1) {
      stack.push(command(index));
    }
    while (stack.canUndo) {
      stack.popUndo();
    }

    const seen: string[] = [];
    while (stack.canRedo) {
      seen.push(stack.popRedo()!.id);
    }

    expect(seen).toEqual(
      Array.from({ length: 50 }, (_value, index) => `cmd-${index}`),
    );
    expect(stack.size).toBe(50);
  });

  it('honours a custom capacity', () => {
    const stack = new CommandStack(3);

    for (let index = 0; index < 10; index += 1) {
      stack.push(command(index));
    }

    expect(stack.size).toBe(3);
    expect(stack.history.map((item) => item.id)).toEqual([
      'cmd-7',
      'cmd-8',
      'cmd-9',
    ]);
  });

  it('refuses a capacity that is not a positive integer', () => {
    expect(() => new CommandStack(0)).toThrow(RangeError);
    expect(() => new CommandStack(-1)).toThrow(RangeError);
    expect(() => new CommandStack(1.5)).toThrow(RangeError);
  });

  it('refuses a command with no operations', () => {
    const stack = new CommandStack();

    expect(() => stack.push({ id: 'x', suggestionIds: [], operations: [] })).toThrow(
      RangeError,
    );
  });
});

describe('CommandStack redo invalidation', () => {
  it('clears the redo stack when a new command is pushed', () => {
    const stack = new CommandStack();
    stack.push(command(1));
    stack.popUndo();
    expect(stack.canRedo).toBe(true);

    stack.push(command(2));

    expect(stack.canRedo).toBe(false);
  });

  it('returns undefined rather than throwing on an empty stack', () => {
    const stack = new CommandStack();

    expect(stack.popUndo()).toBeUndefined();
    expect(stack.popRedo()).toBeUndefined();
    expect(stack.peekUndo()).toBeUndefined();
    expect(stack.peekRedo()).toBeUndefined();
  });

  it('clear forgets both stacks', () => {
    const stack = new CommandStack();
    stack.push(command(1));
    stack.popUndo();

    stack.clear();

    expect(stack.canUndo).toBe(false);
    expect(stack.canRedo).toBe(false);
  });
});

describe('CommandStack isolation', () => {
  it('does not expose the stored command for mutation', () => {
    const stack = new CommandStack();
    const original = command(1);
    stack.push(original);

    original.operations[0]!.newText = 'tampered';

    expect(stack.peekUndo()?.operations[0]?.newText).toBe('new');
  });

  it('returns a copy from peek so a caller cannot mutate the history', () => {
    const stack = new CommandStack();
    stack.push(command(1));

    const peeked = stack.peekUndo()!;
    peeked.suggestionIds.push('injected');

    expect(stack.peekUndo()?.suggestionIds).toEqual(['sug-1']);
  });
});

describe('invertCommand', () => {
  it('swaps the original and replacement text', () => {
    const inverted = invertCommand({
      id: 'c',
      suggestionIds: ['s'],
      operations: [
        { rangeStart: 0, rangeLength: 3, originalText: 'cat', newText: 'dog' },
      ],
    });

    expect(inverted[0]).toEqual({
      rangeStart: 0,
      rangeLength: 3,
      originalText: 'dog',
      newText: 'cat',
    });
  });

  it('uses the replacement length as the range to reverse', () => {
    const inverted = invertCommand({
      id: 'c',
      suggestionIds: ['s'],
      operations: [
        { rangeStart: 5, rangeLength: 2, originalText: 'ab', newText: 'abcdef' },
      ],
    });

    // The document now holds six characters at offset five, not two.
    expect(inverted[0]?.rangeLength).toBe(6);
  });

  it('orders the inverted operations bottom-up', () => {
    const inverted = invertCommand({
      id: 'c',
      suggestionIds: ['s'],
      operations: [
        { rangeStart: 0, rangeLength: 1, originalText: 'a', newText: 'x' },
        { rangeStart: 40, rangeLength: 1, originalText: 'b', newText: 'y' },
        { rangeStart: 20, rangeLength: 1, originalText: 'c', newText: 'z' },
      ],
    });

    expect(inverted.map((item) => item.rangeStart)).toEqual([40, 20, 0]);
  });
});

describe('sortForApplication', () => {
  it('puts the highest start offset first', () => {
    const sorted = sortForApplication([
      { rangeStart: 5, rangeLength: 1, originalText: 'a', newText: 'b' },
      { rangeStart: 50, rangeLength: 1, originalText: 'a', newText: 'b' },
      { rangeStart: 20, rangeLength: 1, originalText: 'a', newText: 'b' },
    ]);

    expect(sorted.map((item) => item.rangeStart)).toEqual([50, 20, 5]);
  });

  it('breaks ties on the longer range first', () => {
    const sorted = sortForApplication([
      { rangeStart: 10, rangeLength: 2, originalText: 'ab', newText: 'x' },
      { rangeStart: 10, rangeLength: 5, originalText: 'abcde', newText: 'y' },
    ]);

    expect(sorted[0]?.rangeLength).toBe(5);
  });

  it('does not mutate its argument', () => {
    const input = [
      { rangeStart: 1, rangeLength: 1, originalText: 'a', newText: 'b' },
      { rangeStart: 9, rangeLength: 1, originalText: 'a', newText: 'b' },
    ];

    sortForApplication(input);

    expect(input[0]?.rangeStart).toBe(1);
  });
});

describe('overlap detection', () => {
  it('sees an overlap between intersecting ranges', () => {
    expect(
      overlaps(
        { rangeStart: 0, rangeLength: 5, originalText: 'abcde', newText: 'x' },
        { rangeStart: 3, rangeLength: 5, originalText: 'defgh', newText: 'y' },
      ),
    ).toBe(true);
  });

  it('does not see an overlap between adjacent ranges', () => {
    expect(
      overlaps(
        { rangeStart: 0, rangeLength: 3, originalText: 'abc', newText: 'x' },
        { rangeStart: 3, rangeLength: 3, originalText: 'def', newText: 'y' },
      ),
    ).toBe(false);
  });

  it('treats an insertion point as overlapping nothing', () => {
    expect(
      overlaps(
        { rangeStart: 2, rangeLength: 0, originalText: '', newText: 'x' },
        { rangeStart: 0, rangeLength: 5, originalText: 'abcde', newText: 'y' },
      ),
    ).toBe(false);
  });

  it('reports every conflicting pair in a batch', () => {
    const conflicts = findConflicts([
      { rangeStart: 0, rangeLength: 5, originalText: 'abcde', newText: 'x' },
      { rangeStart: 3, rangeLength: 5, originalText: 'defgh', newText: 'y' },
      { rangeStart: 100, rangeLength: 2, originalText: 'zz', newText: 'w' },
    ]);

    expect(conflicts).toEqual([[0, 1]]);
  });

  it('reports nothing for a disjoint batch', () => {
    expect(
      findConflicts([
        { rangeStart: 0, rangeLength: 2, originalText: 'ab', newText: 'x' },
        { rangeStart: 10, rangeLength: 2, originalText: 'cd', newText: 'y' },
      ]),
    ).toEqual([]);
  });
});
