import * as React from 'react';
import { FluentProvider, webLightTheme } from '@fluentui/react-components';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AIPanel } from '../src/taskpane/components/AIPanel';
import { BatchActionBar } from '../src/taskpane/components/BatchActionBar';
import {
  SEVERITY_INTENT,
  SuggestionItem,
} from '../src/taskpane/components/SuggestionItem';
import {
  OVERSCAN,
  windowFor,
} from '../src/taskpane/components/VirtualizedList';
import type { AIAssistant } from '../src/taskpane/hooks/useAIAssistant';
import type { Suggestion } from '../src/taskpane/types/ipc';

function wrap(node: React.ReactNode): React.ReactElement {
  return <FluentProvider theme={webLightTheme}>{node}</FluentProvider>;
}

function suggestion(overrides: Partial<Suggestion> = {}): Suggestion {
  return {
    id: 'sug-1',
    start: 4,
    length: 3,
    originalText: 'cat',
    suggestedText: 'dog',
    category: 'Spelling',
    severity: 'warning',
    explanation: 'Unknown word in the Tibetan lexicon.',
    ruleId: 'spell.oov',
    confidence: 0.87,
    ...overrides,
  };
}

describe('SuggestionItem', () => {
  it('shows both texts, the rule and the confidence', () => {
    render(
      wrap(
        <SuggestionItem
          suggestion={suggestion()}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
        />,
      ),
    );

    expect(screen.getByLabelText('Current text')).toHaveTextContent('cat');
    expect(screen.getByLabelText('Suggested text')).toHaveTextContent('dog');
    expect(screen.getByText('spell.oov')).toBeInTheDocument();
    expect(screen.getByText('0.87')).toBeInTheDocument();
  });

  it('exposes the confidence as a labelled progress bar', () => {
    render(
      wrap(
        <SuggestionItem
          suggestion={suggestion({ confidence: 0.42 })}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
        />,
      ),
    );

    expect(screen.getByLabelText('Confidence 0.42')).toBeInTheDocument();
  });

  it('maps every severity to a Fluent intent', () => {
    expect(SEVERITY_INTENT).toEqual({
      critical: 'error',
      warning: 'warning',
      suggestion: 'info',
    });
  });

  it('announces the severity in the card title', () => {
    render(
      wrap(
        <SuggestionItem
          suggestion={suggestion({ severity: 'critical' })}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
        />,
      ),
    );

    expect(screen.getByText(/Critical: Spelling/)).toBeInTheDocument();
  });

  it('applies and dismisses through its callbacks', async () => {
    const onApply = jest.fn();
    const onDismiss = jest.fn();
    const user = userEvent.setup();
    render(
      wrap(
        <SuggestionItem
          suggestion={suggestion()}
          onApply={onApply}
          onDismiss={onDismiss}
        />,
      ),
    );

    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));

    expect(onApply).toHaveBeenCalledWith(suggestion());
    expect(onDismiss).toHaveBeenCalledWith('sug-1');
  });

  it('disables apply while a batch is running', () => {
    render(
      wrap(
        <SuggestionItem
          suggestion={suggestion()}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
          disabled
        />,
      ),
    );

    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  });

  it('does not re-render when an unrelated prop identity changes', () => {
    const { rerender } = render(
      wrap(
        <SuggestionItem
          suggestion={suggestion()}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
        />,
      ),
    );
    const before = screen.getByLabelText('Suggested text').textContent;

    rerender(
      wrap(
        <SuggestionItem
          suggestion={suggestion()}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
        />,
      ),
    );

    expect(screen.getByLabelText('Suggested text').textContent).toBe(before);
  });
});

describe('BatchActionBar', () => {
  const defaults = {
    total: 12,
    criticalCount: 2,
    autoApplicableCount: 7,
    canUndo: false,
    canRedo: false,
    busy: false,
    onApplyBatch: jest.fn(),
    onUndo: jest.fn(),
    onRedo: jest.fn(),
  };

  it('states how many fixes the batch covers', () => {
    render(wrap(<BatchActionBar {...defaults} />));

    expect(screen.getByRole('button', { name: /Apply 7 safe fixes/ })).toBeInTheDocument();
  });

  it('uses the singular for one fix', () => {
    render(wrap(<BatchActionBar {...defaults} autoApplicableCount={1} />));

    expect(screen.getByRole('button', { name: /Apply 1 safe fix$/ })).toBeInTheDocument();
  });

  it('disables the batch when nothing qualifies', () => {
    render(wrap(<BatchActionBar {...defaults} autoApplicableCount={0} />));

    expect(screen.getByRole('button', { name: 'No safe fixes' })).toBeDisabled();
  });

  it('reflects the undo and redo availability', () => {
    render(wrap(<BatchActionBar {...defaults} canUndo canRedo={false} />));

    expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();
  });

  it('disables everything while busy', () => {
    render(wrap(<BatchActionBar {...defaults} canUndo canRedo busy />));

    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();
  });

  it('shows the critical count', () => {
    render(wrap(<BatchActionBar {...defaults} />));

    expect(screen.getByText('2 critical')).toBeInTheDocument();
  });
});

describe('windowFor', () => {
  it('mounts nothing for an empty list', () => {
    expect(windowFor({ scrollTop: 0, itemHeight: 100, height: 500, count: 0 })).toEqual({
      start: 0,
      end: 0,
      offset: 0,
    });
  });

  it('mounts the visible slice plus overscan at the top', () => {
    const window = windowFor({
      scrollTop: 0,
      itemHeight: 100,
      height: 500,
      count: 200,
    });

    expect(window.start).toBe(0);
    expect(window.end).toBe(6 + OVERSCAN);
    expect(window.offset).toBe(0);
  });

  it('advances the window and the offset as the list scrolls', () => {
    const window = windowFor({
      scrollTop: 5000,
      itemHeight: 100,
      height: 500,
      count: 200,
    });

    expect(window.start).toBe(50 - OVERSCAN);
    expect(window.offset).toBe((50 - OVERSCAN) * 100);
  });

  it('never runs past the end of the list', () => {
    const window = windowFor({
      scrollTop: 19_500,
      itemHeight: 100,
      height: 500,
      count: 200,
    });

    expect(window.end).toBe(200);
  });

  it('mounts far fewer rows than the list holds', () => {
    const window = windowFor({
      scrollTop: 0,
      itemHeight: 100,
      height: 500,
      count: 500,
    });

    expect(window.end - window.start).toBeLessThan(20);
  });
});

describe('AIPanel', () => {
  function assistant(overrides: Partial<AIAssistant> = {}): AIAssistant {
    return {
      output: '',
      status: 'idle',
      error: null,
      isStreaming: false,
      generate: jest.fn().mockResolvedValue(undefined),
      regenerate: jest.fn().mockResolvedValue(undefined),
      stopGeneration: jest.fn(),
      clear: jest.fn(),
      lastPrompt: null,
      ...overrides,
    };
  }

  const writers = {
    onReplaceSelection: jest.fn(),
    onInsertBelow: jest.fn(),
    onCopy: jest.fn().mockResolvedValue(undefined),
  };

  it('offers the five documented result actions', () => {
    render(
      wrap(
        <AIPanel assistant={assistant({ output: 'result' })} sourceText="draft" {...writers} />,
      ),
    );

    for (const label of ['Replace selection', 'Insert below', 'Copy', 'Regenerate', 'Stop']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });

  it('marks the output region as a polite live region', () => {
    render(
      wrap(<AIPanel assistant={assistant()} sourceText="draft" {...writers} />),
    );

    const region = screen.getByRole('region', { name: 'Assistant output' });
    expect(region).toHaveAttribute('aria-live', 'polite');
  });

  it('marks the region busy while streaming', () => {
    render(
      wrap(
        <AIPanel
          assistant={assistant({ isStreaming: true, status: 'streaming' })}
          sourceText="draft"
          {...writers}
        />,
      ),
    );

    expect(screen.getByRole('region', { name: 'Assistant output' })).toHaveAttribute(
      'aria-busy',
      'true',
    );
  });

  it('only enables Stop while a generation is running', () => {
    const { rerender } = render(
      wrap(<AIPanel assistant={assistant()} sourceText="draft" {...writers} />),
    );
    expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled();

    rerender(
      wrap(
        <AIPanel
          assistant={assistant({ isStreaming: true, status: 'streaming' })}
          sourceText="draft"
          {...writers}
        />,
      ),
    );

    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
  });

  it('stops the generation through the assistant', async () => {
    const stopGeneration = jest.fn();
    const user = userEvent.setup();
    render(
      wrap(
        <AIPanel
          assistant={assistant({ isStreaming: true, status: 'streaming', stopGeneration })}
          sourceText="draft"
          {...writers}
        />,
      ),
    );

    await user.click(screen.getByRole('button', { name: 'Stop' }));

    expect(stopGeneration).toHaveBeenCalledTimes(1);
  });

  it('replaces the selection with the generated text', async () => {
    const onReplaceSelection = jest.fn();
    const user = userEvent.setup();
    render(
      wrap(
        <AIPanel
          assistant={assistant({ output: 'generated' })}
          sourceText="draft"
          {...writers}
          onReplaceSelection={onReplaceSelection}
        />,
      ),
    );

    await user.click(screen.getByRole('button', { name: 'Replace selection' }));

    expect(onReplaceSelection).toHaveBeenCalledWith('generated');
  });

  it('copies through the injected writer and confirms', async () => {
    const onCopy = jest.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      wrap(
        <AIPanel
          assistant={assistant({ output: 'generated' })}
          sourceText="draft"
          {...writers}
          onCopy={onCopy}
        />,
      ),
    );

    await user.click(screen.getByRole('button', { name: 'Copy' }));

    expect(onCopy).toHaveBeenCalledWith('generated');
    await waitFor(() =>
      expect(screen.getByText('Copied to the clipboard.')).toBeInTheDocument(),
    );
  });

  it('disables the result actions before anything is generated', () => {
    render(
      wrap(<AIPanel assistant={assistant()} sourceText="draft" {...writers} />),
    );

    expect(screen.getByRole('button', { name: 'Replace selection' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Insert below' })).toBeDisabled();
  });

  it('reports a failure with its code', () => {
    render(
      wrap(
        <AIPanel
          assistant={assistant({
            status: 'error',
            error: { code: 'TEEA-3004', message: 'no model' },
          })}
          sourceText="draft"
          {...writers}
        />,
      ),
    );

    expect(screen.getByRole('alert')).toHaveTextContent('TEEA-3004: no model');
  });

  it('says the output is incomplete after a stop', () => {
    render(
      wrap(
        <AIPanel
          assistant={assistant({ status: 'cancelled', output: 'half' })}
          sourceText="draft"
          {...writers}
        />,
      ),
    );

    expect(screen.getByText(/output above is incomplete/)).toBeInTheDocument();
  });

  it('refuses to generate from empty source text', () => {
    render(wrap(<AIPanel assistant={assistant()} sourceText="   " {...writers} />));

    expect(screen.getByRole('button', { name: 'Generate' })).toBeDisabled();
  });
});
