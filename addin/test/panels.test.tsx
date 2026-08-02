/**
 * Deep UI tests for every low-coverage panel component.
 *
 * Covers: OCRPanel, SpeechToTextPanel, TextToSpeechPanel,
 *         TranslationPanel, WordLookupPanel, SuggestionGroup
 */
import * as React from 'react';
import { FluentProvider, webLightTheme } from '@fluentui/react-components';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { OCRPanel } from '../src/taskpane/components/OCRPanel';
import { SpeechToTextPanel } from '../src/taskpane/components/SpeechToTextPanel';
import { TextToSpeechPanel } from '../src/taskpane/components/TextToSpeechPanel';
import { TranslationPanel } from '../src/taskpane/components/TranslationPanel';
import {
  WordLookupPanel,
  levenshteinDistance,
  getSpellingSuggestions,
  COMMON_TIBETAN_VOCABULARY,
} from '../src/taskpane/components/WordLookupPanel';
import { SuggestionGroup } from '../src/taskpane/components/SuggestionGroup';
import type { Suggestion } from '../src/taskpane/types/ipc';

// ── Helpers ──────────────────────────────────────────────────────────

function wrap(node: React.ReactNode): React.ReactElement {
  return <FluentProvider theme={webLightTheme}>{node}</FluentProvider>;
}

// Mock `useCloudAI` globally so TranslationPanel & WordLookupPanel render without hitting real cloud.
const mockGenerate = jest.fn().mockResolvedValue(undefined);
const mockStopGeneration = jest.fn();
const mockClear = jest.fn();
jest.mock('../src/taskpane/hooks/useCloudAI', () => ({
  useCloudAI: () => ({
    output: '',
    isLoading: false,
    isStreaming: false,
    error: null,
    generate: mockGenerate,
    stopGeneration: mockStopGeneration,
    clear: mockClear,
  }),
}));

// Mock `useMonlamDictionary` for WordLookupPanel
const mockSearch = jest.fn().mockResolvedValue(undefined);
jest.mock('../src/taskpane/hooks/useMonlamDictionary', () => ({
  useMonlamDictionary: () => ({
    entries: [],
    isLoading: false,
    error: null,
    search: mockSearch,
    clear: jest.fn(),
  }),
}));

// Mock `useMonlamTTS` for TextToSpeechPanel
const mockTTSGenerate = jest.fn().mockResolvedValue(undefined);
jest.mock('../src/taskpane/hooks/useMonlamTTS', () => ({
  useMonlamTTS: () => ({
    audioUrl: null,
    isLoading: false,
    error: null,
    generate: mockTTSGenerate,
    clear: jest.fn(),
  }),
}));

// The Monlam API key is resolved at runtime from config.json (never bundled).
jest.mock('../src/taskpane/config', () => ({
  getMonlamApiKey: jest.fn().mockResolvedValue('test-key'),
  MONLAM_BASE_URL: 'https://api-v1.monlamai.studio',
}));

// Mock fetch globally for OCR and STT
global.fetch = jest.fn().mockResolvedValue({
  ok: true,
  json: jest.fn().mockResolvedValue({ text: 'mock transcription' }),
}) as jest.Mock;

// ── OCRPanel ─────────────────────────────────────────────────────────

describe('OCRPanel', () => {
  it('renders with the title and file input', () => {
    render(wrap(<OCRPanel />));
    expect(screen.getByText(/Monlam Optical Character Recognition/)).toBeInTheDocument();
    expect(screen.getByLabelText('Upload image for OCR')).toBeInTheDocument();
  });

  it('shows a textarea for extracted text', () => {
    render(wrap(<OCRPanel />));
    expect(screen.getByLabelText('Extracted OCR text')).toBeInTheDocument();
  });

  it('does not show Insert button when no text is extracted', () => {
    const onInsert = jest.fn();
    render(wrap(<OCRPanel onInsertText={onInsert} />));
    expect(screen.queryByText('Insert into Document')).not.toBeInTheDocument();
  });

  it('uploads a file and processes it', async () => {
    const onInsert = jest.fn();
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ extracted_text: 'བཀྲ་ཤིས་བདེ་ལེགས' }),
    });

    render(wrap(<OCRPanel onInsertText={onInsert} />));
    const input = screen.getByLabelText('Upload image for OCR') as HTMLInputElement;
    const file = new File(['fake image content'], 'test.png', { type: 'image/png' });

    await act(async () => {
      await userEvent.upload(input, file);
    });

    await waitFor(() => {
      expect(screen.getByLabelText('Extracted OCR text')).toHaveValue('བཀྲ་ཤིས་བདེ་ལེགས');
    });
  });

  it('shows error on API failure', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    render(wrap(<OCRPanel />));
    const input = screen.getByLabelText('Upload image for OCR') as HTMLInputElement;
    const file = new File(['bad'], 'bad.png', { type: 'image/png' });

    await act(async () => {
      await userEvent.upload(input, file);
    });

    await waitFor(() => {
      expect(screen.getByText(/Monlam OCR API returned error status 500/)).toBeInTheDocument();
    });
  });
});

// ── SpeechToTextPanel ────────────────────────────────────────────────

describe('SpeechToTextPanel', () => {
  it('renders title and microphone button', () => {
    render(wrap(<SpeechToTextPanel />));
    expect(screen.getByText(/Monlam Speech-to-Text/)).toBeInTheDocument();
    expect(screen.getByText('Start Microphone')).toBeInTheDocument();
  });

  it('shows a textarea for transcription output', () => {
    render(wrap(<SpeechToTextPanel />));
    expect(screen.getByLabelText('Speech transcription output')).toBeInTheDocument();
  });

  it('does not show Insert button when no transcript', () => {
    const onInsert = jest.fn();
    render(wrap(<SpeechToTextPanel onInsertText={onInsert} />));
    expect(screen.queryByText('Insert into Document')).not.toBeInTheDocument();
  });

  it('shows error when microphone is denied', async () => {
    // Simulate denied getUserMedia
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: {
        getUserMedia: jest.fn().mockRejectedValue(new Error('Permission denied')),
      },
      configurable: true,
    });

    const user = userEvent.setup();
    render(wrap(<SpeechToTextPanel />));
    await user.click(screen.getByText('Start Microphone'));

    await waitFor(() => {
      expect(screen.getByText('Microphone access denied or not available.')).toBeInTheDocument();
    });
  });
});

// ── TextToSpeechPanel ────────────────────────────────────────────────

describe('TextToSpeechPanel', () => {
  it('renders with title, textarea, and voice grid', () => {
    render(wrap(<TextToSpeechPanel sourceText="བཀྲ་ཤིས" />));
    expect(screen.getByText('🔊 Monlam TTS')).toBeInTheDocument();
    expect(screen.getByLabelText('Text to read aloud')).toBeInTheDocument();
    expect(screen.getByText('Lhasa female')).toBeInTheDocument();
    expect(screen.getByText('Amdo male')).toBeInTheDocument();
    expect(screen.getByText('Kham female')).toBeInTheDocument();
  });

  it('shows character count', () => {
    render(wrap(<TextToSpeechPanel sourceText="བཀྲ་ཤིས" />));
    expect(screen.getByText(/characters$/)).toBeInTheDocument();
  });

  it('shows offline warning when isOnline is false', () => {
    render(wrap(<TextToSpeechPanel sourceText="test" isOnline={false} />));
    expect(
      screen.getByText(/Text-to-Speech requires an active internet connection/),
    ).toBeInTheDocument();
  });

  it('selects a voice when clicking a voice card', async () => {
    const user = userEvent.setup();
    render(wrap(<TextToSpeechPanel sourceText="བཀྲ་ཤིས" />));

    await user.click(screen.getByText('Amdo female'));
    // The card should now be active (we can verify it doesn't crash)
    expect(screen.getByText('Amdo female')).toBeInTheDocument();
  });

  it('calls generate when Generate Speech button is clicked', async () => {
    const user = userEvent.setup();
    render(wrap(<TextToSpeechPanel sourceText="བཀྲ་ཤིས" />));

    await user.click(screen.getByText('Generate Speech'));
    expect(mockTTSGenerate).toHaveBeenCalledWith('བཀྲ་ཤིས', 'lhasa_female');
  });

  it('disables Generate button when text is empty', () => {
    render(wrap(<TextToSpeechPanel sourceText="" />));
    expect(screen.getByText('Generate Speech')).toBeDisabled();
  });
});

// ── TranslationPanel ─────────────────────────────────────────────────

describe('TranslationPanel', () => {
  const baseProps = {
    sourceText: 'བཀྲ་ཤིས་བདེ་ལེགས',
    onReplaceSelection: jest.fn(),
    onInsertBelow: jest.fn(),
  };

  it('renders title and translation direction dropdown', () => {
    render(wrap(<TranslationPanel {...baseProps} />));
    expect(screen.getByText('🌐 Monlam AI Translation')).toBeInTheDocument();
    expect(screen.getByLabelText('Translation Direction')).toBeInTheDocument();
  });

  it('populates input with sourceText', () => {
    render(wrap(<TranslationPanel {...baseProps} />));
    const textarea = screen.getByPlaceholderText('Enter or select Tibetan text to translate...');
    expect(textarea).toHaveValue('བཀྲ་ཤིས་བདེ་ལེགས');
  });

  it('shows offline warning when isOnline is false', () => {
    render(wrap(<TranslationPanel {...baseProps} isOnline={false} />));
    expect(
      screen.getByText(/Translation requires an active internet connection/),
    ).toBeInTheDocument();
  });

  it('has Translate, Replace selection, Insert below, and Copy buttons', () => {
    render(wrap(<TranslationPanel {...baseProps} />));
    expect(screen.getByText('Translate')).toBeInTheDocument();
    expect(screen.getByText('Replace selection')).toBeInTheDocument();
    expect(screen.getByText('Insert below')).toBeInTheDocument();
    expect(screen.getByText('Copy')).toBeInTheDocument();
  });

  it('shows placeholder text in output area', () => {
    render(wrap(<TranslationPanel {...baseProps} />));
    expect(screen.getByText('Translation result will appear here.')).toBeInTheDocument();
  });

  it('calls cloudAI.generate when Translate is clicked', async () => {
    mockGenerate.mockClear();
    const user = userEvent.setup();
    render(wrap(<TranslationPanel {...baseProps} />));

    await user.click(screen.getByText('Translate'));
    expect(mockGenerate).toHaveBeenCalledTimes(1);
  });

  it('disables Replace and Insert when there is no output', () => {
    render(wrap(<TranslationPanel {...baseProps} />));
    expect(screen.getByText('Replace selection')).toBeDisabled();
    expect(screen.getByText('Insert below')).toBeDisabled();
  });
});

// ── WordLookupPanel ──────────────────────────────────────────────────

describe('WordLookupPanel', () => {
  it('renders the title and search input', () => {
    render(wrap(<WordLookupPanel />));
    expect(screen.getByText('📖 Monlam Word Lookup')).toBeInTheDocument();
    expect(screen.getByLabelText('Tibetan word search input')).toBeInTheDocument();
  });

  it('has a language pair selector', () => {
    render(wrap(<WordLookupPanel />));
    expect(screen.getByLabelText('Dictionary language pair selector')).toBeInTheDocument();
  });

  it('has an AI translation section', () => {
    render(wrap(<WordLookupPanel />));
    expect(screen.getByText('🤖 AI Word Translation')).toBeInTheDocument();
  });

  it('shows offline warning when isOnline is false', () => {
    render(wrap(<WordLookupPanel isOnline={false} />));
    expect(
      screen.getByText(/Word Lookup requires an internet connection/),
    ).toBeInTheDocument();
  });

  it('calls dictionary search when Search button is clicked', async () => {
    mockSearch.mockClear();
    const user = userEvent.setup();
    render(wrap(<WordLookupPanel />));

    const input = screen.getByLabelText('Tibetan word search input');
    await user.type(input, 'སློབ་སྦྱོང');
    await user.click(screen.getByText('Search'));

    expect(mockSearch).toHaveBeenCalledWith('སློབ་སྦྱོང', 'bo-en');
  });

  it('disables Search when query is empty', () => {
    render(wrap(<WordLookupPanel />));
    expect(screen.getByText('Search')).toBeDisabled();
  });

  it('calls AI translate when Translate with AI button is clicked', async () => {
    mockGenerate.mockClear();
    const user = userEvent.setup();
    render(wrap(<WordLookupPanel />));

    const input = screen.getByLabelText('Tibetan word search input');
    await user.type(input, 'སློབ');
    await user.click(screen.getByText('Translate with AI'));

    expect(mockGenerate).toHaveBeenCalledTimes(1);
  });
});

// ── Levenshtein & Spelling Suggestions (pure logic) ──────────────────

describe('levenshteinDistance', () => {
  it('returns 0 for identical strings', () => {
    expect(levenshteinDistance('hello', 'hello')).toBe(0);
  });

  it('returns length of other string when one is empty', () => {
    expect(levenshteinDistance('', 'abc')).toBe(3);
    expect(levenshteinDistance('abc', '')).toBe(3);
  });

  it('computes a simple edit distance', () => {
    expect(levenshteinDistance('kitten', 'sitting')).toBe(3);
  });
});

describe('getSpellingSuggestions', () => {
  it('returns empty for empty query', () => {
    expect(getSpellingSuggestions('')).toEqual([]);
  });

  it('returns empty for exact match (distance 0)', () => {
    // An exact match in the vocabulary has distance 0, which is filtered out
    const exact = COMMON_TIBETAN_VOCABULARY[0]!;
    expect(getSpellingSuggestions(exact)).toEqual([]);
  });

  it('limits results to the specified count', () => {
    expect(getSpellingSuggestions('སློབ', 1).length).toBeLessThanOrEqual(1);
  });
});

// ── SuggestionGroup ──────────────────────────────────────────────────

describe('SuggestionGroup', () => {
  function suggestion(overrides: Partial<Suggestion> = {}): Suggestion {
    return {
      id: 'sug-1',
      start: 0,
      length: 3,
      originalText: 'bad',
      suggestedText: 'good',
      category: 'Grammar',
      severity: 'warning',
      explanation: 'Grammar issue',
      ruleId: 'gram.001',
      confidence: 0.9,
      ...overrides,
    };
  }

  it('renders a group header with the category name', () => {
    render(
      wrap(
        <SuggestionGroup
          group={{ category: 'Grammar', suggestions: [suggestion()], criticalCount: 0 }}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
          virtualized={false}
          disabled={false}
        />,
      ),
    );
    expect(screen.getByText('Grammar')).toBeInTheDocument();
  });

  it('renders suggestion items inside the group', () => {
    render(
      wrap(
        <SuggestionGroup
          group={{ category: 'Grammar', suggestions: [suggestion()], criticalCount: 0 }}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
          virtualized={false}
          disabled={false}
        />,
      ),
    );
    expect(screen.getByLabelText('Current text')).toHaveTextContent('bad');
  });

  it('renders multiple suggestions', () => {
    render(
      wrap(
        <SuggestionGroup
          group={{
            category: 'Spelling',
            suggestions: [
              suggestion({ id: 'a', originalText: 'one' }),
              suggestion({ id: 'b', originalText: 'two' }),
            ],
            criticalCount: 0,
          }}
          onApply={jest.fn()}
          onDismiss={jest.fn()}
          virtualized={false}
          disabled={false}
        />,
      ),
    );
    expect(screen.getAllByRole('button', { name: 'Apply' }).length).toBe(2);
  });
});
