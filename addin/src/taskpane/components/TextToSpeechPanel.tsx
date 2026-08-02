import * as React from 'react';
import {
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  Text,
  Textarea,
  Tooltip,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import { useMonlamTTS } from '../hooks/useMonlamTTS';

export interface VoiceOption {
  id: string;
  name: string;
  dialect: string;
  disabled?: boolean;
  disabledReason?: string;
}

const VOICES: VoiceOption[] = [
  { id: 'lhasa_female', name: 'Lhasa female', dialect: 'Lhasa (Central)' },
  { id: 'lhasa_male', name: 'Lhasa male', dialect: 'Lhasa (Central)' },
  { id: 'amdo_female', name: 'Amdo female', dialect: 'Amdo' },
  { id: 'amdo_male', name: 'Amdo male', dialect: 'Amdo' },
  { id: 'kham_female', name: 'Kham female', dialect: 'Kham' },
  { id: 'kham_male', name: 'Kham male', dialect: 'Kham' },
];

const useStyles = makeStyles({
  root: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalM,
    width: '100%',
    boxSizing: 'border-box',
  },
  title: {
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightBold,
    color: tokens.colorNeutralForeground1,
  },
  textarea: {
    width: '100%',
    minHeight: '120px',
  },
  charCount: {
    alignSelf: 'flex-end',
    fontSize: tokens.fontSizeBase100,
    color: tokens.colorNeutralForeground3,
    marginTop: tokens.spacingVerticalXXS,
  },
  voiceGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: tokens.spacingHorizontalS,
  },
  voiceCard: {
    display: 'flex',
    flexDirection: 'column',
    padding: tokens.spacingVerticalS,
    cursor: 'pointer',
    border: `1px solid ${tokens.colorNeutralStroke1}`,
    borderRadius: tokens.borderRadiusMedium,
    backgroundColor: tokens.colorNeutralBackground1,
    transitionProperty: 'all',
    transitionDuration: '200ms',
    ':hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
      border: `1px solid ${tokens.colorBrandBackground}`,
    },
  },
  activeVoiceCard: {
    border: `2px solid ${tokens.colorBrandBackground}`,
    backgroundColor: tokens.colorBrandBackground2,
  },
  disabledVoiceCard: {
    opacity: 0.5,
    cursor: 'not-allowed',
    ':hover': {
      backgroundColor: tokens.colorNeutralBackground1,
      border: `1px solid ${tokens.colorNeutralStroke1}`,
    },
  },
  voiceName: {
    fontWeight: tokens.fontWeightSemibold,
    fontSize: tokens.fontSizeBase300,
  },
  voiceDialect: {
    fontSize: tokens.fontSizeBase100,
    color: tokens.colorNeutralForeground3,
  },
  actionsRow: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
  },
  audioPlayer: {
    width: '100%',
    marginTop: tokens.spacingVerticalS,
  },
  outputGroup: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
    padding: tokens.spacingHorizontalM,
    backgroundColor: tokens.colorNeutralBackground2,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
});

export interface TextToSpeechPanelProps {
  sourceText: string;
  isOnline?: boolean;
}

export function TextToSpeechPanel({ sourceText, isOnline }: TextToSpeechPanelProps): JSX.Element {
  const styles = useStyles();
  const [text, setText] = React.useState(sourceText);
  const [selectedVoice, setSelectedVoice] = React.useState('lhasa_female');
  const [restrictedVoices, setRestrictedVoices] = React.useState<Record<string, string>>({});
  const { audioUrl, isLoading, error, generate } = useMonlamTTS();

  React.useEffect(() => {
    setText(sourceText);
  }, [sourceText]);

  const handleGenerate = React.useCallback(async () => {
    const textToGenerate = text || sourceText;
    if (!textToGenerate.trim()) return;

    try {
      await generate(textToGenerate, selectedVoice);
    } catch (err) {
      const errMsg = String(err);
      if (errMsg.includes('403') || errMsg.includes('401') || errMsg.includes('permission')) {
        setRestrictedVoices((prev) => ({
          ...prev,
          [selectedVoice]: 'API key lacks permissions for this voice.',
        }));
      }
    }
  }, [generate, text, sourceText, selectedVoice]);

  return (
    <div className={styles.root}>
      <Text className={styles.title}>🔊 Monlam TTS</Text>

      {isOnline === false ? (
        <MessageBar intent="warning">
          <MessageBarBody>
            Text-to-Speech requires an active internet connection to contact Monlam AI.
          </MessageBarBody>
        </MessageBar>
      ) : null}

      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <Textarea
          className={styles.textarea}
          value={text}
          onChange={(_e, data) => setText(data.value)}
          placeholder="Enter Tibetan text to read aloud..."
          aria-label="Text to read aloud"
          rows={4}
        />
        <span className={styles.charCount}>{(text || sourceText).length} characters</span>
      </div>

      <Text weight="semibold" size={300}>Select Voice & Dialect</Text>
      <div className={styles.voiceGrid}>
        {VOICES.map((voice) => {
          const isActive = selectedVoice === voice.id;
          const isRestricted = !!restrictedVoices[voice.id];
          const cardContent = (
            <div
              key={voice.id}
              className={`${styles.voiceCard} ${isActive ? styles.activeVoiceCard : ''} ${
                isRestricted ? styles.disabledVoiceCard : ''
              }`}
              onClick={() => {
                if (!isRestricted) {
                  setSelectedVoice(voice.id);
                }
              }}
              onKeyDown={(event) => {
                if (!isRestricted && (event.key === 'Enter' || event.key === ' ')) {
                  event.preventDefault();
                  setSelectedVoice(voice.id);
                }
              }}
              role="button"
              tabIndex={isRestricted ? -1 : 0}
              aria-disabled={isRestricted}
            >
              <Text className={styles.voiceName}>{voice.name}</Text>
              <Text className={styles.voiceDialect}>{voice.dialect}</Text>
            </div>
          );

          if (isRestricted) {
            return (
              <Tooltip key={voice.id} content={restrictedVoices[voice.id] || ''} relationship="label">
                {cardContent}
              </Tooltip>
            );
          }
          return cardContent;
        })}
      </div>

      <div className={styles.actionsRow}>
        <Button
          appearance="primary"
          onClick={() => void handleGenerate()}
          disabled={isLoading || isOnline === false || !(text || sourceText).trim() || !!restrictedVoices[selectedVoice]}
        >
          {isLoading ? 'Generating Speech…' : 'Generate Speech'}
        </Button>
        {isLoading ? <Spinner size="tiny" /> : null}
      </div>

      {error ? (
        <Text style={{ color: tokens.colorPaletteRedForeground1 }} role="alert">
          {error}
        </Text>
      ) : null}

      {audioUrl ? (
        <div className={styles.outputGroup}>
          <Text weight="semibold" size={300}>Generated Audio</Text>
          <audio key={audioUrl} controls className={styles.audioPlayer} src={audioUrl}>
            <track kind="captions" />
            Your browser does not support the audio element.
          </audio>
          <a href={audioUrl} download="monlam_speech.mp3" style={{ textDecoration: 'none' }}>
            <Button appearance="secondary">Download Audio</Button>
          </a>
        </div>
      ) : null}
    </div>
  );
}
