/**
 * WordLookupPanel: Single word & phrase lookup component with Monlam Dictionary API
 * and AI-powered word translation.
 */

import * as React from 'react';
import {
  Button,
  Field,
  Input,
  Link,
  MessageBar,
  MessageBarBody,
  Select,
  Spinner,
  Text,
  Textarea,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import { useCloudAI } from '../hooks/useCloudAI';
import { useMonlamDictionary } from '../hooks/useMonlamDictionary';

/**
 * A small built-in vocabulary used for "Did you mean?" suggestions when the
 * dictionary returns no results. Deliberately small: enough common Tibetan
 * words to catch typos of the demo terms without pretending to be a lexicon.
 */
export const COMMON_TIBETAN_VOCABULARY: readonly string[] = [
  'བཀྲ་ཤིས་བདེ་ལེགས།',
  'སློབ་སྦྱོང',
  'སློབ་གྲྭ',
  'བོད་ཡིག',
  'ཁྱེད་རང',
  'དགའ་བ',
  'གླེང་མོལ',
  'དོན་དུ',
  'ཡིག་ཆ',
  'སློབ་མ',
];

/** Strip Tibetan punctuation (tsek and shad) before comparing spellings. */
function normalizeTibetanWord(word: string): string {
  return word.replace(/[་།]+/g, '');
}

/** Classic dynamic-programming Levenshtein distance, on Tibetan code points. */
export function levenshteinDistance(a: string, b: string): number {
  const s = normalizeTibetanWord(a);
  const t = normalizeTibetanWord(b);
  const m = s.length;
  const n = t.length;
  if (m === 0) return n;
  if (n === 0) return m;

  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  let curr = new Array<number>(n + 1).fill(0);

  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = s[i - 1] === t[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j]! + 1, curr[j - 1]! + 1, prev[j - 1]! + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[n]!;
}

/**
 * Rank the built-in vocabulary by Levenshtein distance from the query and
 * return the closest matches, capped at `limit`.
 */
export function getSpellingSuggestions(query: string, limit = 3): string[] {
  const q = query.trim();
  if (q.length === 0) return [];

  return COMMON_TIBETAN_VOCABULARY.map((word) => ({
    word,
    distance: levenshteinDistance(q, word),
  }))
    .filter((candidate) => candidate.distance > 0 && candidate.distance <= 3)
    .sort((x, y) => x.distance - y.distance)
    .slice(0, limit)
    .map((candidate) => candidate.word);
}

const useStyles = makeStyles({
  root: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalM,
  },
  searchRow: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
  },
  selectRow: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
  },
  card: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
    padding: tokens.spacingVerticalM,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusMedium,
    backgroundColor: tokens.colorNeutralBackground1,
  },
  posBadge: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: 'bold',
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground2,
    maxWidth: 'max-content',
  },
  aiSection: {
    marginTop: tokens.spacingVerticalM,
    paddingTop: tokens.spacingVerticalM,
    borderTop: `1px solid ${tokens.colorNeutralStroke2}`,
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
  },
  suggestionsRow: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    columnGap: tokens.spacingHorizontalS,
  },
});

export interface WordLookupPanelProps {
  onInsertText?: (text: string) => void;
  isOnline?: boolean | undefined;
}

export function WordLookupPanel({ onInsertText, isOnline }: WordLookupPanelProps): JSX.Element {
  const styles = useStyles();

  const [query, setQuery] = React.useState<string>('');
  const [pair, setPair] = React.useState<string>('bo-en');
  const [targetLang, setTargetLang] = React.useState<string>('English');
  const [hasSearched, setHasSearched] = React.useState<boolean>(false);
  const [suggestions, setSuggestions] = React.useState<string[]>([]);

  const dict = useMonlamDictionary();
  const ai = useCloudAI();

  const handleSearch = React.useCallback(async () => {
    if (!query.trim()) return;
    setHasSearched(true);
    setSuggestions([]);
    await dict.search(query, pair);
  }, [dict, query, pair]);

  const handleSuggestionClick = React.useCallback(
    (word: string) => {
      setQuery(word);
      setHasSearched(true);
      setSuggestions([]);
      void dict.search(word, pair);
    },
    [dict, pair],
  );

  // When a search completes with no definitions, offer spelling suggestions
  // computed locally against the built-in vocabulary.
  React.useEffect(() => {
    if (hasSearched && !dict.isLoading && dict.entries.length === 0) {
      setSuggestions(getSpellingSuggestions(query.trim()));
    } else {
      setSuggestions([]);
    }
  }, [hasSearched, dict.isLoading, dict.entries.length, query]);

  const handleAiTranslate = React.useCallback(async () => {
    if (!query.trim()) return;
    const prompt = `Translate the Tibetan word or phrase "${query.trim()}" into ${targetLang}. Output only the clear translation without preamble.`;
    const systemPrompt = `You are an expert Tibetan lexicographer and translator into ${targetLang}.`;
    await ai.generate(prompt, systemPrompt);
  }, [ai, query, targetLang]);

  return (
    <div className={styles.root}>
      <Text weight="semibold" size={400}>
        📖 Monlam Word Lookup
      </Text>

      {isOnline === false ? (
        <MessageBar intent="warning">
          <MessageBarBody>
            Word Lookup requires an internet connection to search the Monlam Dictionary API.
          </MessageBarBody>
        </MessageBar>
      ) : null}

      <Field label="Word or Phrase to Look Up">
        <div className={styles.searchRow}>
          <Input
            value={query}
            onChange={(_e, data) => {
              setQuery(data.value);
              setHasSearched(false);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleSearch();
            }}
            placeholder="Enter word (e.g. སློབ་སྦྱོང)..."
            disabled={isOnline === false || dict.isLoading}
            style={{ flex: 1 }}
            aria-label="Tibetan word search input"
          />
          <Button
            appearance="primary"
            onClick={() => void handleSearch()}
            disabled={isOnline === false || dict.isLoading || !query.trim()}
          >
            Search
          </Button>
        </div>
      </Field>

      <div className={styles.selectRow}>
        <Text size={300} weight="semibold">
          Dictionary Pair:
        </Text>
        <Select
          value={pair}
          onChange={(_e, data) => {
            setPair(data.value);
            setHasSearched(false);
          }}
          disabled={isOnline === false || dict.isLoading}
          aria-label="Dictionary language pair selector"
        >
          <option value="bo-en">Tibetan ➔ English (bo-en)</option>
          <option value="bo-bo">Tibetan ➔ Tibetan (bo-bo)</option>
          <option value="en-bo">English ➔ Tibetan (en-bo)</option>
          <option value="bo-zh">Tibetan ➔ Chinese (bo-zh)</option>
        </Select>
      </div>

      {dict.error ? (
        <MessageBar intent="warning">
          <MessageBarBody>{dict.error}</MessageBarBody>
        </MessageBar>
      ) : null}

      {!dict.isLoading && !dict.error && hasSearched && dict.entries.length === 0 ? (
        <>
          <MessageBar intent="info">
            <MessageBarBody>
              {suggestions.length > 0
                ? `Word not found. Did you mean one of these? (for "${query}")`
                : 'Word not found – please check the spelling.'}
            </MessageBarBody>
          </MessageBar>
          {suggestions.length > 0 ? (
            <div className={styles.suggestionsRow} aria-label="Spelling suggestions">
              <Text size={300} weight="semibold">
                Did you mean:
              </Text>
              {suggestions.map((word) => (
                <Link key={word} onClick={() => handleSuggestionClick(word)}>
                  {word}
                </Link>
              ))}
            </div>
          ) : null}
        </>
      ) : null}

      {dict.isLoading ? <Spinner size="medium" label="Searching Monlam Dictionary..." /> : null}

      {dict.entries.map((entry, index) => (
        <div key={index} className={styles.card}>
          <Text weight="bold" size={400}>
            {entry.word}
          </Text>

          {entry.pos ? <span className={styles.posBadge}>{entry.pos}</span> : null}

          {entry.definition ? (
            <Text size={300} style={{ whiteSpace: 'pre-wrap' }}>
              {entry.definition}
            </Text>
          ) : null}

          {entry.explanation ? (
            <Text size={200} style={{ color: tokens.colorNeutralForeground3 }}>
              Note: {entry.explanation}
            </Text>
          ) : null}

          {entry.examples && entry.examples.length > 0 ? (
            <div>
              <Text weight="semibold" size={200}>
                Examples:
              </Text>
              {entry.examples.map((ex, exIdx) => (
                <Text key={exIdx} size={200} block style={{ fontStyle: 'italic' }}>
                  • {ex}
                </Text>
              ))}
            </div>
          ) : null}

          {onInsertText && entry.definition ? (
            <Button
              appearance="outline"
              size="small"
              onClick={() => onInsertText(`${entry.word}: ${entry.definition}`)}
            >
              Insert Definition into Document
            </Button>
          ) : null}
        </div>
      ))}

      {/* AI Word Translation Section */}
      <div className={styles.aiSection}>
        <Text weight="semibold" size={300}>
          🤖 AI Word Translation
        </Text>

        <div className={styles.selectRow}>
          <Select
            value={targetLang}
            onChange={(_e, data) => setTargetLang(data.value)}
            disabled={isOnline === false || ai.isLoading}
            aria-label="AI translation target language selector"
          >
            <option value="English">English</option>
            <option value="Chinese">Chinese</option>
            <option value="Hindi">Hindi</option>
            <option value="French">French</option>
          </Select>

          <Button
            appearance="secondary"
            onClick={() => void handleAiTranslate()}
            disabled={isOnline === false || ai.isLoading || !query.trim()}
          >
            Translate with AI
          </Button>
        </div>

        {ai.isLoading ? <Spinner size="tiny" label="Generating AI translation..." /> : null}

        {ai.error ? (
          <MessageBar intent="error">
            <MessageBarBody>{ai.error}</MessageBarBody>
          </MessageBar>
        ) : null}

        {ai.output ? (
          <div className={styles.card}>
            <Text weight="semibold" size={200}>
              AI Translation ({targetLang}):
            </Text>
            <Textarea value={ai.output} readOnly rows={3} aria-label="AI translation output" />
            {onInsertText ? (
              <Button
                appearance="outline"
                size="small"
                onClick={() => onInsertText(ai.output)}
              >
                Insert Translation into Document
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
