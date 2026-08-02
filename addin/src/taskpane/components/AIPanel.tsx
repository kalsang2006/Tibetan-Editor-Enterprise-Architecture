import * as React from 'react';
import {
  Button,
  Dropdown,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  Switch,
  Text,
  Textarea,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import {
  type UseCloudAIResult,
  useCloudAI,
} from '../hooks/useCloudAI';

/** Which operation is being asked for. */
export type AssistantAction = 'rewrite' | 'explain' | 'summarize';

export const REWRITE_TEMPLATES: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'rewrite_fluent', label: 'Improve fluency' },
  { value: 'tone_formal', label: 'Transform to Formal Honorific (zhe-sa)' },
  { value: 'improve_clarity', label: 'Improve clarity' },
  { value: 'translate_english', label: 'Translate to English' },
  { value: 'continue_text', label: 'Continue writing' },
];

export const ACTIONS: ReadonlyArray<{ value: AssistantAction; label: string }> = [
  { value: 'rewrite', label: 'Rewrite' },
  { value: 'summarize', label: 'Summarize' },
  { value: 'explain', label: 'Explain grammar' },
];

const QUICK_PILLS = [
  { label: 'Improve writing', template: 'rewrite_fluent', action: 'rewrite' as AssistantAction },
  { label: 'Fix spelling & grammar', template: 'improve_clarity', action: 'rewrite' as AssistantAction },
  { label: 'Make it more professional', template: 'tone_formal', action: 'rewrite' as AssistantAction },
  { label: 'Make text simpler', template: 'improve_clarity', action: 'rewrite' as AssistantAction },
];

const useStyles = makeStyles({
  panel: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    width: '100%',
  },
  headerGroup: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalXXS,
  },
  title: {
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightBold,
    color: tokens.colorNeutralForeground1,
  },
  subtitle: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorNeutralForeground3,
    lineHeight: tokens.lineHeightBase200,
  },
  pillsContainer: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: tokens.spacingHorizontalS,
    marginTop: tokens.spacingVerticalXS,
    marginBottom: tokens.spacingVerticalXS,
  },
  pillButton: {
    borderRadius: tokens.borderRadiusCircular,
    fontSize: tokens.fontSizeBase200,
    padding: '4px 12px',
    border: `1px solid ${tokens.colorNeutralStroke1}`,
    backgroundColor: tokens.colorNeutralBackground1,
    color: tokens.colorNeutralForeground1,
    cursor: 'pointer',
    ':hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
      border: `1px solid ${tokens.colorBrandBackground}`,
    },
  },
  promptContainer: {
    position: 'relative',
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalXXS,
  },
  textareaInput: {
    width: '100%',
    minHeight: '110px',
  },
  promptFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: tokens.spacingVerticalXXS,
  },
  attachmentIcon: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: tokens.colorNeutralForeground3,
    cursor: 'pointer',
  },
  charCounter: {
    fontSize: tokens.fontSizeBase100,
    color: tokens.colorNeutralForeground3,
  },
  optionsRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  goButton: {
    width: '100%',
    marginTop: tokens.spacingVerticalS,
    fontWeight: tokens.fontWeightSemibold,
  },
  controls: {
    display: 'flex',
    columnGap: tokens.spacingHorizontalS,
    rowGap: tokens.spacingVerticalXS,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  output: {
    minHeight: '120px',
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
  /**
   * The cloud AI connection, owned by the caller (e.g. App) so its state
   * survives tab switches. When omitted the panel creates its own.
   */
  assistant?: UseCloudAIResult;
  sourceText: string;
  onReplaceSelection: (text: string) => void | Promise<void>;
  onInsertBelow: (text: string) => void | Promise<void>;
  onCopy?: (text: string) => void | Promise<void>;
  isOnline?: boolean | undefined;
}

export function AIPanel({
  assistant,
  sourceText,
  onReplaceSelection,
  onInsertBelow,
  onCopy,
  isOnline,
}: AIPanelProps): JSX.Element {
  const styles = useStyles();
  const [action, setAction] = React.useState<AssistantAction>('rewrite');
  const [template, setTemplate] = React.useState<string>('rewrite_fluent');
  const [customPrompt, setCustomPrompt] = React.useState<string>('');
  const [replaceSelectedText, setReplaceSelectedText] = React.useState<boolean>(true);
  const [copied, setCopied] = React.useState(false);
  const [stopped, setStopped] = React.useState(false);
  const [lastUsedPrompt, setLastUsedPrompt] = React.useState<{ text: string; systemPrompt: string } | null>(null);

  const fallbackCloudAI = useCloudAI();
  const cloudAI = assistant ?? fallbackCloudAI;

  const output = cloudAI.output;
  const isStreaming = cloudAI.isStreaming || cloudAI.isLoading;
  const error = cloudAI.error;

  const isDisabled = isOnline === false || isStreaming;
  const hasOutput = output.length > 0;

  const getSystemPrompt = React.useCallback((act: AssistantAction, tmpl: string) => {
    if (act === 'summarize') {
      return 'You are an expert Tibetan language assistant. Provide a concise summary of the given text in Tibetan.';
    }
    if (act === 'explain') {
      return 'You are an expert Tibetan linguist. Explain the grammar, key vocabulary, and syntax of the given Tibetan text.';
    }
    switch (tmpl) {
      case 'tone_formal':
        return 'You are an expert Tibetan language writing and editing assistant. Transform the text into formal Tibetan honorific (zhe-sa).';
      case 'improve_clarity':
        return 'You are an expert Tibetan language writing and editing assistant. Improve the clarity, spelling, and sentence structure of the text.';
      case 'translate_english':
        return 'You are a professional Tibetan-to-English translator. Translate the given Tibetan text into clear English.';
      case 'continue_text':
        return 'You are an expert Tibetan language author. Continue writing the following text naturally in Tibetan.';
      case 'rewrite_fluent':
      default:
        return 'You are an expert Tibetan language writing and editing assistant. Rewrite the following text to improve fluency and natural expression in Tibetan.';
    }
  }, []);

  const run = React.useCallback(() => {
    const promptText = customPrompt || sourceText;
    if (!promptText.trim()) return;

    const sysPrompt = getSystemPrompt(action, template);
    setStopped(false);
    setLastUsedPrompt({ text: promptText, systemPrompt: sysPrompt });
    setCopied(false);
    void cloudAI.generate(promptText, sysPrompt);
  }, [cloudAI, customPrompt, sourceText, action, template, getSystemPrompt]);

  const handlePillClick = (pill: typeof QUICK_PILLS[0]) => {
    setAction(pill.action);
    setTemplate(pill.template);
    setCustomPrompt(pill.label);
  };

  const handleGo = React.useCallback(() => {
    if (hasOutput && replaceSelectedText) {
      void onReplaceSelection(output);
    } else {
      run();
    }
  }, [hasOutput, replaceSelectedText, onReplaceSelection, output, run]);

  const regenerate = React.useCallback(() => {
    setCopied(false);
    setStopped(false);
    if (lastUsedPrompt) {
      void cloudAI.generate(lastUsedPrompt.text, lastUsedPrompt.systemPrompt);
    }
  }, [cloudAI, lastUsedPrompt]);

  const stop = React.useCallback(() => {
    cloudAI.stopGeneration();
    setStopped(true);
  }, [cloudAI]);

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
      setCopied(false);
    }
  }, [onCopy, output]);

  const isRegenerateDisabled = isStreaming || !lastUsedPrompt;

  return (
    <section className={styles.panel} aria-label="Cloud AI writing assistant">
      {/* Header */}
      <div className={styles.headerGroup}>
        <Text className={styles.title}>Let AI magic begin</Text>
        <Text className={styles.subtitle}>
          Select content in your document to edit with Monlam Cloud AI, or describe what you&apos;d like to create.
        </Text>
      </div>

      {isOnline === false ? (
        <MessageBar intent="warning">
          <MessageBarBody>
            The AI Assistant requires an active internet connection to connect to Monlam Cloud AI.
          </MessageBarBody>
        </MessageBar>
      ) : null}

      {/* Quick Action Pills */}
      <div className={styles.pillsContainer}>
        {QUICK_PILLS.map((pill) => (
          <button
            key={pill.label}
            type="button"
            className={styles.pillButton}
            onClick={() => handlePillClick(pill)}
            disabled={isDisabled}
          >
            {pill.label}
          </button>
        ))}
      </div>

      {/* Action Controls & Style Selector */}
      <div className={styles.controls}>
        <Dropdown
          aria-label="Assistant action"
          value={ACTIONS.find((item) => item.value === action)?.label ?? ''}
          selectedOptions={[action]}
          onOptionSelect={(_event, data) => {
            setAction((data.optionValue ?? 'rewrite') as AssistantAction);
          }}
          disabled={isDisabled}
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
            disabled={isDisabled}
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
          disabled={isDisabled || (sourceText.trim().length === 0 && customPrompt.trim().length === 0)}
        >
          Generate
        </Button>
        {isStreaming ? <Spinner size="tiny" label="Generating" /> : null}
      </div>

      {/* Prompt / Instruction Input Area */}
      <div className={styles.promptContainer}>
        <Textarea
          aria-label="Describe what you want to do"
          className={styles.textareaInput}
          value={customPrompt || sourceText}
          onChange={(_e, data) => setCustomPrompt(data.value)}
          placeholder="Describe what you want to do"
          maxLength={2000}
          rows={3}
          disabled={isDisabled}
        />
        <div className={styles.promptFooter}>
          <span className={styles.attachmentIcon} title="Attach context">
            📎
          </span>
          <span className={styles.charCounter}>
            {(customPrompt || sourceText).length}/2000
          </span>
        </div>
      </div>

      {/* Options Row & Main Action */}
      <div className={styles.optionsRow}>
        <Switch
          checked={replaceSelectedText}
          onChange={(_e, data) => setReplaceSelectedText(data.checked)}
          label="Replace selected text"
          disabled={isDisabled}
        />
      </div>

      <Button
        appearance="primary"
        size="large"
        className={styles.goButton}
        onClick={handleGo}
        disabled={isDisabled || (sourceText.trim().length === 0 && customPrompt.trim().length === 0)}
        icon={<span role="img" aria-hidden="true">➔</span>}
        iconPosition="after"
      >
        Go
      </Button>

      {/* Generated Streaming Output & Controls */}
      <StreamingText text={output} streaming={isStreaming} />

      {error !== null ? (
        <Text className={styles.error} role="alert">
          {error}
        </Text>
      ) : null}
      {stopped ? (
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
          disabled={isRegenerateDisabled}
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

