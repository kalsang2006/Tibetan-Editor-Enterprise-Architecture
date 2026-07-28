import { act, renderHook, waitFor } from '@testing-library/react';

import { MAX_HISTORY, type UndoCommand } from '../src/taskpane/services/CommandStack';
import { useUndoStack } from '../src/taskpane/hooks/useUndoStack';
import type { ApplyReport } from '../src/taskpane/services/WordDocument';

function command(index: number): UndoCommand {
  return {
    id: `cmd-${index}`,
    suggestionIds: [`sug-${index}`],
    operations: [
      {
        rangeStart: index * 10,
        rangeLength: 3,
        originalText: 'old',
        newText: 'newer',
      },
    ],
  };
}

function recordingApplier(): {
  apply: (ops: readonly UndoCommand['operations'][number][]) => Promise<ApplyReport>;
  calls: Array<readonly UndoCommand['operations'][number][]>;
} {
  const calls: Array<readonly UndoCommand['operations'][number][]> = [];
  return {
    calls,
    apply: async (operations) => {
      calls.push(operations);
      return { applied: [...operations], skipped: [] };
    },
  };
}

describe('useUndoStack', () => {
  it('starts with nothing to undo or redo', () => {
    const { result } = renderHook(() => useUndoStack({ apply: recordingApplier().apply }));

    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
    expect(result.current.depth).toBe(0);
  });

  it('enables undo once a command is pushed', () => {
    const { result } = renderHook(() => useUndoStack({ apply: recordingApplier().apply }));

    act(() => result.current.pushCommand(command(1)));

    expect(result.current.canUndo).toBe(true);
    expect(result.current.depth).toBe(1);
  });

  it('tracks fifty deep transactions and caps there', () => {
    const { result } = renderHook(() => useUndoStack({ apply: recordingApplier().apply }));

    act(() => {
      for (let index = 0; index < 60; index += 1) {
        result.current.pushCommand(command(index));
      }
    });

    expect(result.current.depth).toBe(MAX_HISTORY);
    expect(result.current.depth).toBe(50);
  });

  it('undoes all fifty retained commands', async () => {
    const applier = recordingApplier();
    const { result } = renderHook(() => useUndoStack({ apply: applier.apply }));

    act(() => {
      for (let index = 0; index < 50; index += 1) {
        result.current.pushCommand(command(index));
      }
    });

    for (let index = 0; index < 50; index += 1) {
      await act(async () => {
        await result.current.executeUndo();
      });
    }

    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(true);
    expect(applier.calls).toHaveLength(50);
  });

  it('sends the inverted operations to the document on undo', async () => {
    const applier = recordingApplier();
    const { result } = renderHook(() => useUndoStack({ apply: applier.apply }));
    act(() => result.current.pushCommand(command(1)));

    await act(async () => {
      await result.current.executeUndo();
    });

    expect(applier.calls[0]?.[0]).toEqual({
      rangeStart: 10,
      // The document holds "newer" now, five characters, not the original three.
      rangeLength: 5,
      originalText: 'newer',
      newText: 'old',
    });
  });

  it('sends the original operations on redo', async () => {
    const applier = recordingApplier();
    const { result } = renderHook(() => useUndoStack({ apply: applier.apply }));
    act(() => result.current.pushCommand(command(1)));
    await act(async () => {
      await result.current.executeUndo();
    });

    await act(async () => {
      await result.current.executeRedo();
    });

    expect(applier.calls[1]?.[0]).toEqual({
      rangeStart: 10,
      rangeLength: 3,
      originalText: 'old',
      newText: 'newer',
    });
    expect(result.current.canUndo).toBe(true);
    expect(result.current.canRedo).toBe(false);
  });

  it('does nothing when there is nothing to undo', async () => {
    const applier = recordingApplier();
    const { result } = renderHook(() => useUndoStack({ apply: applier.apply }));

    await act(async () => {
      await result.current.executeUndo();
    });

    expect(applier.calls).toHaveLength(0);
  });

  it('keeps the command on the stack when the document write fails', async () => {
    const apply = jest.fn().mockRejectedValue(new Error('Word refused'));
    const { result } = renderHook(() => useUndoStack({ apply }));
    act(() => result.current.pushCommand(command(1)));

    await act(async () => {
      await expect(result.current.executeUndo()).rejects.toThrow('Word refused');
    });

    expect(result.current.canUndo).toBe(true);
    expect(result.current.isBusy).toBe(false);
  });

  it('reports what the last undo actually did', async () => {
    const apply = jest.fn().mockResolvedValue({
      applied: [],
      skipped: [{ operation: command(1).operations[0], reason: 'stale' }],
    });
    const { result } = renderHook(() => useUndoStack({ apply }));
    act(() => result.current.pushCommand(command(1)));

    await act(async () => {
      await result.current.executeUndo();
    });

    await waitFor(() => {
      expect(result.current.lastReport?.skipped).toHaveLength(1);
    });
  });

  it('clears the redo stack when a new command arrives', async () => {
    const { result } = renderHook(() => useUndoStack({ apply: recordingApplier().apply }));
    act(() => result.current.pushCommand(command(1)));
    await act(async () => {
      await result.current.executeUndo();
    });
    expect(result.current.canRedo).toBe(true);

    act(() => result.current.pushCommand(command(2)));

    expect(result.current.canRedo).toBe(false);
  });

  it('reset forgets the whole history', async () => {
    const { result } = renderHook(() => useUndoStack({ apply: recordingApplier().apply }));
    act(() => result.current.pushCommand(command(1)));

    act(() => result.current.reset());

    expect(result.current.canUndo).toBe(false);
    expect(result.current.depth).toBe(0);
    expect(result.current.lastReport).toBeNull();
  });

  it('honours a custom capacity', () => {
    const { result } = renderHook(() =>
      useUndoStack({ capacity: 5, apply: recordingApplier().apply }),
    );

    act(() => {
      for (let index = 0; index < 20; index += 1) {
        result.current.pushCommand(command(index));
      }
    });

    expect(result.current.depth).toBe(5);
  });
});
