/**
 * User Interface Panel for Tibetan Plagiarism Detection in Microsoft Word Task Pane.
 */

import * as React from 'react';
import {
  Button,
  Card,
  CardHeader,
  Spinner,
  Text,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import type { PlagiarismCheckResult, PlagiarismMatch } from '../types/ipc';
import type { PlagiarismStatus } from '../hooks/usePlagiarism';

const useStyles = makeStyles({
  container: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalM,
  },
  headerBox: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: tokens.colorNeutralBackground2,
    padding: tokens.spacingVerticalM,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${tokens.colorNeutralStroke1}`,
  },
  scoreGauge: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  scoreNumber: {
    fontSize: tokens.fontSizeHero800,
    fontWeight: tokens.fontWeightBold,
    color: tokens.colorPaletteGreenForeground1,
  },
  scoreWarning: {
    fontSize: tokens.fontSizeHero800,
    fontWeight: tokens.fontWeightBold,
    color: tokens.colorPaletteRedForeground1,
  },
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: tokens.spacingHorizontalS,
  },
  metricCard: {
    padding: tokens.spacingVerticalS,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    backgroundColor: tokens.colorNeutralBackground1,
    borderRadius: tokens.borderRadiusSmall,
    border: `1px solid ${tokens.colorNeutralStroke1}`,
  },
  matchList: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
  },
  matchCard: {
    padding: tokens.spacingVerticalS,
    cursor: 'pointer',
    borderLeft: `4px solid ${tokens.colorPaletteYellowBorder2}`,
    transition: 'background-color 0.2s',
  },
  actionsRow: {
    display: 'flex',
    gap: tokens.spacingHorizontalS,
  },
  excerptPreview: {
    fontFamily: 'Segoe UI, Tibetan Machine Uni, sans-serif',
    backgroundColor: tokens.colorNeutralBackground3,
    padding: tokens.spacingVerticalXXS,
    borderRadius: tokens.borderRadiusSmall,
    marginTop: tokens.spacingVerticalXXS,
  },
});

export interface PlagiarismPanelProps {
  onCheck: () => Promise<void>;
  onClearHighlights: () => Promise<void>;
  onHighlightMatch?: (match: PlagiarismMatch) => Promise<void>;
  onInsertCitation?: (citationText: string) => Promise<void>;
  result: PlagiarismCheckResult | null;
  status: PlagiarismStatus;
  error: string | null;
  documentText: string;
}

export const PlagiarismPanel: React.FC<PlagiarismPanelProps> = ({
  onCheck,
  onClearHighlights,
  onHighlightMatch,
  onInsertCitation,
  result,
  status,
  error,
  documentText,
}) => {
  const styles = useStyles();
  const [, setHighlighted] = React.useState(false);

  const handleCheck = async () => {
    setHighlighted(false);
    await onCheck();
  };

  const handleClear = async () => {
    await onClearHighlights();
    setHighlighted(false);
  };

  const handleCardClick = async (match: PlagiarismMatch) => {
    if (onHighlightMatch) {
      await onHighlightMatch(match);
      setHighlighted(true);
    }
  };

  const handleCitationClick = async (e: React.MouseEvent, match: PlagiarismMatch) => {
    e.stopPropagation();
    if (onInsertCitation) {
      const manuscript = formatManuscriptTitle(match);
      const citationText = `[Citation] ${manuscript}, Similarity: ${(match.similarity * 100).toFixed(1)}%.`;
      await onInsertCitation(citationText);
    }
  };

  const formatManuscriptTitle = (m: PlagiarismMatch): string => {
    if (m.collection && m.filename) {
      return `${m.collection} (${m.filename})`;
    }
    if (m.collection) {
      return m.collection;
    }
    if (m.filename) {
      return `Manuscript ${m.filename}`;
    }
    const cleanId = m.document_id.split('#')[0];
    return `Manuscript ${cleanId ? cleanId.slice(0, 8) : 'Reference'}`;
  };

  const getExcerpt = (match: PlagiarismMatch): string => {
    if (!match.source_span || !documentText) return '';
    const { char_start, char_end } = match.source_span;
    return documentText.slice(char_start, char_end);
  };

  return (
    <div className={styles.container}>
      <div className={styles.actionsRow}>
        <Button
          appearance="primary"
          onClick={handleCheck}
          disabled={status === 'loading'}
        >
          {status === 'loading' ? 'Checking...' : 'Check Plagiarism'}
        </Button>
        {result && result.matches.length > 0 && (
          <Button appearance="outline" onClick={handleClear}>
            Clear Highlights
          </Button>
        )}
      </div>

      {status === 'loading' && (
        <Spinner label="Running Winnowing plagiarism check over document..." />
      )}

      {status === 'error' && error && (
        <Text style={{ color: tokens.colorPaletteRedForeground1 }}>
          Plagiarism Check Failed: {error}
        </Text>
      )}

      {status === 'ready' && result && (
        <>
          <div className={styles.headerBox}>
            <div className={styles.scoreGauge}>
              <Text
                className={
                  result.originality_score >= 80
                    ? styles.scoreNumber
                    : styles.scoreWarning
                }
              >
                {result.originality_score}%
              </Text>
              <Text size={200}>Originality Score</Text>
            </div>
            <div>
              <Text weight="semibold">
                {result.matches.length === 0
                  ? 'Clean Document'
                  : `${result.matches.length} Match(es) Found`}
              </Text>
            </div>
          </div>

          <div className={styles.metricsGrid}>
            <div className={styles.metricCard}>
              <Text weight="bold">{result.query_fingerprint_count}</Text>
              <Text size={100}>Fingerprints</Text>
            </div>
            <div className={styles.metricCard}>
              <Text weight="bold">{result.total_corpus_documents}</Text>
              <Text size={100}>Corpus Docs</Text>
            </div>
            <div className={styles.metricCard}>
              <Text weight="bold">{result.matches.length}</Text>
              <Text size={100}>Total Matches</Text>
            </div>
            <div className={styles.metricCard}>
              <Text weight="bold">{result.elapsed_ms.toFixed(1)} ms</Text>
              <Text size={100}>Latency</Text>
            </div>
          </div>

          <div className={styles.matchList}>
            <Text weight="semibold">Corpus Matches:</Text>

            {result.matches.length === 0 ? (
              <Text size={200} style={{ color: tokens.colorNeutralForeground3 }}>
                No plagiarism or duplicate passages detected against the reference corpus.
              </Text>
            ) : (
              result.matches.map((m, idx) => {
                const excerpt = getExcerpt(m);
                const title = formatManuscriptTitle(m);
                return (
                  <Card
                    key={`${m.document_id}-${idx}`}
                    className={styles.matchCard}
                    onClick={() => handleCardClick(m)}
                  >
                    <CardHeader
                      header={
                        <Text weight="bold" size={300}>
                          {title}
                        </Text>
                      }
                      description={
                        <Text size={200}>
                          Similarity: {(m.similarity * 100).toFixed(1)}% | Coverage: {(m.coverage * 100).toFixed(1)}%
                        </Text>
                      }
                    />
                    {excerpt && (
                      <div className={styles.excerptPreview} style={{ fontSize: '15px', lineHeight: '1.6' }}>
                        <Text italic style={{ fontSize: '15px' }}>
                          {'\u201C'}
                          {excerpt}
                          {'\u201D'}
                        </Text>
                      </div>
                    )}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '6px' }}>
                      <Text size={100} style={{ color: tokens.colorNeutralForeground4 }}>
                        Click to highlight passage in Word
                      </Text>
                      {onInsertCitation && (
                        <Button
                          size="small"
                          appearance="subtle"
                          onClick={(e) => handleCitationClick(e, m)}
                        >
                          Citation
                        </Button>
                      )}
                    </div>
                  </Card>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
};
