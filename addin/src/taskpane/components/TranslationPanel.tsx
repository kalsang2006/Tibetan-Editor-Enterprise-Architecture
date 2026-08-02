/**
 * AI Translation Panel backed by Monlam AI Studio LLM Chat Endpoint.
 */

import * as React from 'react';
import {
  Button,
  Dropdown,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  Text,
  Textarea,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import { useCloudAI } from '../hooks/useCloudAI';

const TRANSLATION_DIRECTIONS = [
  { value: 'bo_en', label: 'Tibetan ➔ English' },
  { value: 'en_bo', label: 'English ➔ Tibetan' },
  { value: 'bo_zh', label: 'Tibetan ➔ Chinese' },
  { value: 'zh_bo', label: 'Chinese ➔ Tibetan' },
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
  controlsRow: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
    flexWrap: 'wrap',
  },
  textarea: {
    width: '100%',
    minHeight: '120px',
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
  actions: {
    display: 'flex',
    columnGap: tokens.spacingHorizontalS,
    rowGap: tokens.spacingVerticalXS,
    flexWrap: 'wrap',
  },
});

export interface TranslationPanelProps {
  sourceText: string;
  onReplaceSelection: (text: string) => void | Promise<void>;
  onInsertBelow: (text: string) => void | Promise<void>;
  isOnline?: boolean | undefined;
}

export function TranslationPanel({
  sourceText,
  onReplaceSelection,
  onInsertBelow,
  isOnline,
}: TranslationPanelProps): JSX.Element {
  const styles = useStyles();
  const [direction, setDirection] = React.useState('bo_en');
  const [inputText, setInputText] = React.useState(sourceText);
  const [copied, setCopied] = React.useState(false);

  const cloudAI = useCloudAI();

  React.useEffect(() => {
    if (sourceText) setInputText(sourceText);
  }, [sourceText]);

  const activeOutput = cloudAI.output;
  const isTranslating = cloudAI.isLoading || cloudAI.isStreaming;
  const hasOutput = activeOutput.length > 0;
  const isDisabled = isOnline === false || isTranslating;

  const handleTranslate = React.useCallback(() => {
    const textToTranslate = inputText || sourceText;
    if (!textToTranslate.trim()) return;

    const directionObj = TRANSLATION_DIRECTIONS.find((d) => d.value === direction);
    const targetLabel = directionObj ? directionObj.label : 'English';

    const systemPrompt = `You are a professional Tibetan-English-Chinese translator. Translate the given text accurately following the direction: ${targetLabel}. Respond only with the translated text without preamble.`;

    void cloudAI.generate(textToTranslate, systemPrompt);
  }, [cloudAI, direction, inputText, sourceText]);

  const copy = React.useCallback(async () => {
    try {
      await globalThis.navigator?.clipboard?.writeText(activeOutput);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }, [activeOutput]);

  return (
    <section className={styles.panel} aria-label="AI Translation">
      <div className={styles.headerGroup}>
        <Text className={styles.title}>🌐 Monlam AI Translation</Text>
        <Text className={styles.subtitle}>
          Translate Tibetan document text or custom text into English, Chinese, and other languages via Monlam AI.
        </Text>
      </div>

      {isOnline === false ? (
        <MessageBar intent="warning">
          <MessageBarBody>
            Translation requires an active internet connection to connect to Monlam Cloud AI.
          </MessageBarBody>
        </MessageBar>
      ) : null}

      {cloudAI.error ? (
        <MessageBar intent="error">
          <MessageBarBody>{cloudAI.error}</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.controlsRow}>
        <Dropdown
          aria-label="Translation Direction"
          value={TRANSLATION_DIRECTIONS.find((d) => d.value === direction)?.label ?? ''}
          selectedOptions={[direction]}
          onOptionSelect={(_e, data) => setDirection(data.optionValue ?? 'bo_en')}
          disabled={isDisabled}
        >
          {TRANSLATION_DIRECTIONS.map((d) => (
            <Option key={d.value} value={d.value}>
              {d.label}
            </Option>
          ))}
        </Dropdown>

        <Button
          appearance="primary"
          onClick={handleTranslate}
          disabled={isDisabled || !(inputText || sourceText).trim()}
        >
          Translate
        </Button>
        {isTranslating ? <Spinner size="tiny" label="Translating…" /> : null}
      </div>

      <Textarea
        className={styles.textarea}
        value={inputText}
        onChange={(_e, data) => setInputText(data.value)}
        placeholder="Enter or select Tibetan text to translate..."
        rows={4}
        disabled={isDisabled}
      />

      <div
        className={styles.output}
        role="region"
        aria-label="Translation output"
        aria-live="polite"
        aria-busy={isTranslating}
      >
        {activeOutput.length === 0 ? (
          <Text style={{ color: tokens.colorNeutralForeground3 }}>
            {isTranslating ? 'Translating…' : 'Translation result will appear here.'}
          </Text>
        ) : (
          activeOutput
        )}
      </div>

      {copied ? <Text size={200}>Copied to clipboard.</Text> : null}

      <div className={styles.actions}>
        <Button onClick={() => void onReplaceSelection(activeOutput)} disabled={!hasOutput || isTranslating}>
          Replace selection
        </Button>
        <Button onClick={() => void onInsertBelow(activeOutput)} disabled={!hasOutput || isTranslating}>
          Insert below
        </Button>
        <Button onClick={() => void copy()} disabled={!hasOutput}>
          Copy
        </Button>
      </div>
    </section>
  );
}
