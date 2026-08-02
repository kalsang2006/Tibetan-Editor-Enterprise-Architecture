import * as React from 'react';
import { Button, Textarea, Text, MessageBar, MessageBarBody, Spinner, makeStyles, tokens } from '@fluentui/react-components';

import { MONLAM_API_KEY, MONLAM_BASE_URL } from '../config';

const MONLAM_STT_ENDPOINT = `${MONLAM_BASE_URL}/api/v1/speech-to-text/`;

const useStyles = makeStyles({
  root: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalM,
  },
  controls: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
  },
  textarea: {
    width: '100%',
    minHeight: '150px',
  },
});

export interface SpeechToTextPanelProps {
  onInsertText?: (text: string) => void;
}

export function SpeechToTextPanel({ onInsertText }: SpeechToTextPanelProps): JSX.Element {
  const styles = useStyles();
  const [isListening, setIsListening] = React.useState(false);
  const [isUploading, setIsUploading] = React.useState(false);
  const [transcript, setTranscript] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  const mediaRecorderRef = React.useRef<MediaRecorder | null>(null);
  const audioChunksRef = React.useRef<Blob[]>([]);

  const sendAudioToMonlam = async (audioBlob: Blob) => {
    setIsUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'audio.wav');
      formData.append('language', 'bo');
      formData.append('task', 'transcribe');

      const response = await fetch(MONLAM_STT_ENDPOINT, {
        method: 'POST',
        headers: {
          'X-API-Key': MONLAM_API_KEY,
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Monlam STT API returned error status ${response.status}`);
      }

      const data = await response.json();
      const text = data?.text || data?.transcript || data?.response || data?.output || JSON.stringify(data);
      setTranscript((prev) => (prev ? `${prev}\n${text}` : text));
    } catch (err) {
      console.warn('[Monlam STT] Upload failed:', err);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsUploading(false);
    }
  };

  const toggleListening = React.useCallback(async () => {
    if (isListening) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        void sendAudioToMonlam(audioBlob);
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start();
      mediaRecorderRef.current = mediaRecorder;
      setIsListening(true);
    } catch (err) {
      console.warn('[SpeechToTextPanel] Microphone access error:', err);
      setError('Microphone access denied or not available.');
    }
  }, [isListening]);

  return (
    <div className={styles.root}>
      <Text weight="semibold" size={400}>
        🎙️ Monlam Speech-to-Text (STT)
      </Text>

      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.controls}>
        <Button
          appearance={isListening ? 'primary' : 'secondary'}
          onClick={() => void toggleListening()}
          disabled={isUploading}
        >
          {isListening ? 'Stop & Transcribe' : 'Start Microphone'}
        </Button>

        {isUploading ? <Spinner size="tiny" label="Transcribing audio..." /> : null}

        {onInsertText && transcript ? (
          <Button appearance="outline" onClick={() => onInsertText(transcript)}>
            Insert into Document
          </Button>
        ) : null}
      </div>

      <Textarea
        className={styles.textarea}
        value={transcript}
        onChange={(_e, data) => setTranscript(data.value)}
        placeholder="Transcribed Tibetan speech will appear here..."
        aria-label="Speech transcription output"
        rows={6}
      />
    </div>
  );
}
