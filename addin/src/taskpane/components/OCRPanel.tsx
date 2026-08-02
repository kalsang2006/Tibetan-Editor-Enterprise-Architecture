import * as React from 'react';
import { Button, Textarea, Text, MessageBar, MessageBarBody, Spinner, makeStyles, tokens } from '@fluentui/react-components';

import { getMonlamApiKey, MONLAM_BASE_URL } from '../config';

const MONLAM_OCR_ENDPOINT = `${MONLAM_BASE_URL}/api/v1/ocr/single-page`;

const useStyles = makeStyles({
  root: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalM,
  },
  fileInput: {
    marginVertical: tokens.spacingVerticalS,
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

export interface OCRPanelProps {
  onInsertText?: (text: string) => void;
}

export function OCRPanel({ onInsertText }: OCRPanelProps): JSX.Element {
  const styles = useStyles();
  const [loading, setLoading] = React.useState(false);
  const [extractedText, setExtractedText] = React.useState('');
  const [fileName, setFileName] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setFileName(file.name);
    setLoading(true);
    setError(null);
    setExtractedText('');

    try {
      const apiKey = await getMonlamApiKey();
      if (!apiKey) {
        setTimeout(() => {
          setExtractedText('བོད་ཀྱི་སྐད་ཡིག་ནི་འཛམ་གླིང་འདིའི་སྟེང་གི་སྐད་ཡིག་རྙིང་ཤོས་ཤིག་ཡིན། (Demo OCR Extracted Text)');
          setLoading(false);
        }, 1000);
        return;
      }
      const formData = new FormData();
      formData.append('file', file);
      formData.append('lang_hint', 'bo');

      const response = await fetch(MONLAM_OCR_ENDPOINT, {
        method: 'POST',
        headers: {
          'X-API-Key': apiKey,
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Monlam OCR API returned error status ${response.status}`);
      }

      const data = await response.json();
      const text =
        data?.extracted_text ||
        data?.text ||
        data?.ocr_text ||
        data?.response ||
        data?.output ||
        (typeof data === 'string' ? data : '');

      if (!text || !text.trim()) {
        setError('No text found in the uploaded image.');
      } else {
        setExtractedText(text);
      }
    } catch (err) {
      console.warn('[Monlam OCR] Extraction failed:', err);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.root}>
      <Text weight="semibold" size={400}>
        🖼️ Monlam Optical Character Recognition (OCR)
      </Text>

      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      ) : null}

      <input
        type="file"
        accept="image/*"
        onChange={(e) => void handleFileUpload(e)}
        className={styles.fileInput}
        aria-label="Upload image for OCR"
      />

      {loading ? (
        <Spinner size="medium" label={`Extracting Tibetan text from ${fileName}...`} />
      ) : null}

      <Textarea
        className={styles.textarea}
        value={extractedText}
        onChange={(_e, data) => setExtractedText(data.value)}
        placeholder="Extracted Tibetan text from image will appear here..."
        aria-label="Extracted OCR text"
        rows={6}
      />

      {onInsertText && extractedText ? (
        <div className={styles.controls}>
          <Button appearance="primary" onClick={() => onInsertText(extractedText)}>
            Insert into Document
          </Button>
        </div>
      ) : null}
    </div>
  );
}
