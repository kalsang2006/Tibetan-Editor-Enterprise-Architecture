/**
 * The local assistant: pick an action, watch it generate, decide what to do
 * with the result.
 *
 * The streaming text lives in its own memoized component. `useAIAssistant`
 * already coalesces tokens onto an animation frame, and this is the second half
 * of that: when the frame publishes, only {@link StreamingText} re-renders. The
 * action bar, the dropdown and the five buttons are untouched, so a sixty-second
 * generation does not re-render its own controls a thousand times.
 */

import * as React from 'react';
import {
  Button,
  Dropdown,
  Option,
  Spinner,
  Text,
  Textarea,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import {
  type AssistantAction,
  type AssistantPrompt,
  type AIAssistant,
} from '../hooks/useAIAssistant';

/** The rewrite templates the pane offers, matching `REWRITE_TEMPLATES`. */
export const REWRITE_TEMPLATES: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'rewrite_fluent', label: 'Improve fluency' },
  { value: 'tone_formal', label: 'Make it formal' },
  { value: 'improve_clarity', label: 'Improve clarity' },
  { value: 'continue_text', label: 'Continue writing' },
];

/** The three actions, in the order the pane presents them. */
export const ACTIONS: ReadonlyArray<{ value: AssistantAction; label: string }> = [
  { value: 'rewrite', label: 'Rewrite' },
  { value: 'summarize', label: 'Summarize' },
  { value: 'explain', label: 'Explain grammar' },
];

const useStyles = makeStyles({
  panel: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
  },
  controls: {
    display: 'flex',
    columnGap: tokens.spacingHorizontalS,
    rowGap: tokens.spacingVerticalXS,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  output: {
    minHeight: '160px',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    padding: tokens.spacingHorizontalM,
    borderRadius: tokens.borderRadiusMedium,
    backgroundColor: tokens.colorNeutralBackground2,
    color: tokens.colorNeutralForeground1,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  placeholder: {
    color: tokens.colorNeutralForeground3,
  },
  error: {
    color: tokens.colorPaletteRedForeground1,
  },
  actions: {
    display: 'flex',
    columnGap: tokens.spacingHorizontalS,
    rowGap: tokens.spacingVerticalXS,
    flexWrap: 'wrap',
  },
});

/**
 * The generated text, isolated so a token does not re-render the panel.
 *
 * `aria-live` is `polite`, not the `adaptive` the specification named: ARIA
 * defines only `off`, `polite` and `assertive`, and an invalid value is ignored
 * outright by screen readers — which would have made the streaming output
 * entirely silent. `polite` announces without interrupting, which is the correct
 * behaviour for text that is still arriving.
 */
export const StreamingText = React.memo(function StreamingText({
  text,
  streaming,
}: {
  text: string;
  streaming: boolean;
}): JSX.Element {
  const styles = useStyles();
  return (
    <div
      className={styles.output}
      role="region"
      aria-label="Assistant output"
      aria-live="polite"
      aria-busy={streaming}
    >
      {text.length === 0 ? (
        <Text className={styles.placeholder}>
          {streaming ? 'Generating…' : 'Nothing generated yet.'}
        </Text>
      ) : (
        text
      )}
    </div>
  );
});

StreamingText.displayName = 'StreamingText';

export interface AIPanelProps {
  assistant: AIAssistant;
  /** The text the action runs over: the selection, or the whole document. */
  sourceText: string;
  /** Replace the current selection with the generated text. */
  onReplaceSelection: (text: string) => void | Promise<void>;
  /** Insert the generated text after the current selection. */
  onInsertBelow: (text: string) => void | Promise<void>;
  /** Copy to the clipboard. Injected so a test needs no clipboard permission. */
  onCopy?: (text: string) => void | Promise<void>;
}

export function AIPanel({
  assistant,
  sourceText,
  onReplaceSelection,
  onInsertBelow,
  onCopy,
}: AIPanelProps): JSX.Element {
  const styles = useStyles();
  const [action, setAction] = React.useState<AssistantAction>('rewrite');
  const [template, setTemplate] = React.useState<string>('rewrite_fluent');
  const [copied, setCopied] = React.useState(false);

  const { output, status, error, isStreaming } = assistant;
  const hasOutput = output.length > 0;

  const prompt = React.useMemo<AssistantPrompt>(
    () =>
      action === 'rewrite'
        ? { action, text: sourceText, template }
        : { action, text: sourceText },
    [action, sourceText, template],
  );

  const run = React.useCallback(() => {
    void assistant.generate(prompt);
  }, [assistant, prompt]);

  const regenerate = React.useCallback(() => {
    setCopied(false);
    void assistant.regenerate();
  }, [assistant]);

  const stop = React.useCallback(() => {
    assistant.stopGeneration();
  }, [assistant]);

  const replace = React.useCallback(() => {
    void onReplaceSelection(output);
  }, [onReplaceSelection, output]);

  const insert = React.useCallback(() => {
    void onInsertBelow(output);
  }, [onInsertBelow, output]);

  const copy = React.useCallback(async () => {
    const write =
      onCopy ?? ((text: string) => globalThis.navigator?.clipboard?.writeText(text));
    try {
      await write(output);
      setCopied(true);
    } catch {
      // A denied clipboard permission is not worth a banner; the user can still
      // select the text. Silence here, not a thrown error into the console.
      setCopied(false);
    }
  }, [onCopy, output]);

  return (
    <section className={styles.panel} aria-label="Local writing assistant">
      <div className={styles.controls}>
        <Dropdown
          aria-label="Assistant action"
          value={ACTIONS.find((item) => item.value === action)?.label ?? ''}
          selectedOptions={[action]}
          onOptionSelect={(_event, data) => {
            setAction((data.optionValue ?? 'rewrite') as AssistantAction);
          }}
          disabled={isStreaming}
        >
          {ACTIONS.map((item) => (
            <Option key={item.value} value={item.value}>
              {item.label}
            </Option>
          ))}
        </Dropdown>

        {action === 'rewrite' ? (
          <Dropdown
            aria-label="Rewrite style"
            value={
              REWRITE_TEMPLATES.find((item) => item.value === template)?.label ?? ''
            }
            selectedOptions={[template]}
            onOptionSelect={(_event, data) => {
              setTemplate(data.optionValue ?? 'rewrite_fluent');
            }}
            disabled={isStreaming}
          >
            {REWRITE_TEMPLATES.map((item) => (
              <Option key={item.value} value={item.value}>
                {item.label}
              </Option>
            ))}
          </Dropdown>
        ) : null}

        <Button
          appearance="primary"
          onClick={run}
          disabled={isStreaming || sourceText.trim().length === 0}
        >
          Generate
        </Button>
        {isStreaming ? <Spinner size="tiny" label="Generating" /> : null}
      </div>

      <Textarea
        aria-label="Source text"
        value={sourceText}
        readOnly
        resize="vertical"
        rows={3}
      />

      <StreamingText text={output} streaming={isStreaming} />

      {error !== null ? (
        <Text className={styles.error} role="alert">
          {error.code}: {error.message}
        </Text>
      ) : null}
      {status === 'cancelled' ? (
        <Text size={200}>Stopped. The output above is incomplete.</Text>
      ) : null}
      {copied ? <Text size={200}>Copied to the clipboard.</Text> : null}

      <div className={styles.actions}>
        <Button onClick={replace} disabled={!hasOutput || isStreaming}>
          Replace selection
        </Button>
        <Button onClick={insert} disabled={!hasOutput || isStreaming}>
          Insert below
        </Button>
        <Button onClick={() => void copy()} disabled={!hasOutput}>
          Copy
        </Button>
        <Button
          onClick={regenerate}
          disabled={isStreaming || assistant.lastPrompt === null}
        >
          Regenerate
        </Button>
        <Button appearance="secondary" onClick={stop} disabled={!isStreaming}>
          Stop
        </Button>
      </div>
    </section>
  );
}
