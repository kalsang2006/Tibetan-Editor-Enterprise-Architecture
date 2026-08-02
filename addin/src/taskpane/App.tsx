/**
 * The task pane: vertical sidebar navigation, offline-first NLP engine,
 * and hybrid online features (Assistant, STT, TTS, OCR, Translation, Word Lookup).
 */

import * as React from 'react';
import {
  Button,
  FluentProvider,
  MessageBar,
  MessageBarBody,
  Skeleton,
  SkeletonItem,
  Spinner,
  Switch,
  Text,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import { AIPanel } from './components/AIPanel';
import { BatchActionBar } from './components/BatchActionBar';
import { OCRPanel } from './components/OCRPanel';
import { PlagiarismPanel } from './components/PlagiarismPanel';
import { SpeechToTextPanel } from './components/SpeechToTextPanel';
import { SuggestionGroup } from './components/SuggestionGroup';
import { TextToSpeechPanel } from './components/TextToSpeechPanel';
import { TranslationPanel } from './components/TranslationPanel';
import { WordLookupPanel } from './components/WordLookupPanel';
import { useCloudAI } from './hooks/useCloudAI';
import type { AnalysisStatus } from './hooks/useDocumentAnalysis';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useOfficeTheme } from './hooks/useOfficeTheme';
import { usePlagiarism } from './hooks/usePlagiarism';
import { useSuggestionEngine } from './hooks/useSuggestionEngine';
import { useUndoStack } from './hooks/useUndoStack';
import {
  applyOperations,
  clearPlagiarismHighlights,
  highlightPlagiarismMatches,
  insertAfterSelection,
  insertFootnoteCitation,
  replaceSelection,
} from './services/WordDocument';
import type { PlagiarismMatch, Suggestion } from './types/ipc';

const useStyles = makeStyles({
  rootContainer: {
    position: 'relative',
    display: 'flex',
    flexDirection: 'row',
    width: '100%',
    height: '100vh',
    overflow: 'hidden',
    boxSizing: 'border-box',
  },

  loadingOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: '#1e1e1e',
    zIndex: 1000,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    rowGap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalL,
    textAlign: 'center',
  },

  sidebar: {
    width: '56px',
    minWidth: '56px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    rowGap: tokens.spacingVerticalS,
    paddingTop: tokens.spacingVerticalM,
    paddingBottom: tokens.spacingVerticalM,
    borderRight: `1px solid ${tokens.colorNeutralStroke2}`,
    backgroundColor: tokens.colorNeutralBackground2,
  },

  navButton: {
    width: '40px',
    height: '40px',
    minWidth: '40px',
    borderRadius: tokens.borderRadiusMedium,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    border: 'none',
    backgroundColor: 'transparent',
    color: tokens.colorNeutralForeground2,
    ':hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
      color: tokens.colorNeutralForeground1,
    },
  },

  activeNavButton: {
    backgroundColor: tokens.colorBrandBackground,
    color: tokens.colorNeutralForegroundOnBrand,
    ':hover': {
      backgroundColor: tokens.colorBrandBackgroundHover,
      color: tokens.colorNeutralForegroundOnBrand,
    },
  },

  contentArea: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalM,
    overflowY: 'auto',
  },

  header: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
  },

  statusDot: {
    width: '12px',
    height: '12px',
    borderRadius: '50%',
    display: 'inline-block',
  },
  statusConnected: { backgroundColor: tokens.colorPaletteGreenBackground3 },
  statusDisconnected: { backgroundColor: tokens.colorPaletteRedBackground3 },

  skeletonCard: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
    padding: tokens.spacingVerticalM,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusMedium,
  },

  spacer: {
    marginInlineStart: 'auto',
  },

  groups: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
  },

  empty: {
    padding: tokens.spacingVerticalXXL,
    textAlign: 'center',
    color: tokens.colorNeutralForeground3,
  },

  analysisBar: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
  },
});

export interface AppProps {
  /** The current analysis, already adapted to the pane's view model. */
  suggestions: readonly Suggestion[];
  /** The text the assistant acts on: the selection, or the whole document. */
  sourceText: string;
  /** How operations reach the document. Injected for tests. */
  apply?: typeof applyOperations;
  /** How the assistant's output reaches the document. Injected for tests. */
  document?: {
    replaceSelection: (text: string) => Promise<void>;
    insertAfterSelection: (text: string) => Promise<void>;
  };
  daemonStatus?: 'checking' | 'connected' | 'unavailable';
  daemonBaseUrl?: string;
  onRetryDaemonConnection?: () => void;
  analysisStatus?: AnalysisStatus;
  analysisError?: string | null;
  onRefreshAnalysis?: () => void;
  isOnline?: boolean;
}

type PaneTab =
  | 'review'
  | 'plagiarism'
  | 'assistant'
  | 'stt'
  | 'tts'
  | 'ocr'
  | 'translate'
  | 'wordLookup';

const NAV_ITEMS: Array<{ id: PaneTab; label: string; icon: React.ReactNode }> = [
  {
    id: 'review',
    label: 'Suggestions',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M9 10H15M9 14H15M12 21H7C5.89543 21 5 20.1046 5 19V5C5 3.89543 5.89543 3 7 3H12.5858C12.851 3 13.1054 3.10536 13.2929 3.29289L18.7071 8.70711C18.8946 8.89464 19 9.149 19 9.41421V14.2071" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M18 23V17M15 20H21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'plagiarism',
    label: 'Plagiarism',
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12.5 6.66667H12.5082" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="3.33333" y="3.33325" width="13.3333" height="13.3333" rx="3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M3.33333 12.5L6.66667 9.16663C7.44017 8.42232 8.39316 8.42232 9.16667 9.16663L13.3333 13.3333" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M11.6667 11.6667L12.5 10.8334C13.2735 10.0891 14.2265 10.0891 15 10.8334L16.6667 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'assistant',
    label: 'AI Assistant',
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M9.50011 1C4.80238 1 1.0001 4.80163 1.0001 9.50001C1.0001 10.9909 1.38894 12.4471 2.12732 13.7313L1.03214 17.1323C0.955746 17.3694 1.01852 17.6293 1.19465 17.8055C1.3691 17.9799 1.62837 18.045 1.8678 17.968L5.26879 16.8728C6.55307 17.6112 8.00921 18 9.50011 18C14.1978 18 18.0001 14.1984 18.0001 9.50001C18.0001 4.80228 14.1985 1 9.50011 1Z" fill="currentColor" />
      </svg>
    ),
  },
  {
    id: 'stt',
    label: 'Speech-to-Text',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2C10.34 2 9 3.34 9 5V11C9 12.66 10.34 14 12 14C13.66 14 15 12.66 15 11V5C15 3.34 13.66 2 12 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M19 10V11C19 14.87 15.87 18 12 18C8.13 18 5 14.87 5 11V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M12 18V22M8 22H16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'tts',
    label: 'Text-to-Speech',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M11 5L6 9H2V15H6L11 19V5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M15.54 8.46C16.4774 9.39764 17.004 10.6692 17.004 11.995C17.004 13.3208 16.4774 14.5924 15.54 15.53" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M19.07 4.93C20.9447 6.80528 21.9979 9.34836 21.9979 12C21.9979 14.6516 20.9447 17.1947 19.07 19.07" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'ocr',
    label: 'OCR',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" />
        <path d="M21 15L16 10L5 21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'translate',
    label: 'Translation',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
        <path d="M3.6 9H20.4M3.6 15H20.4" stroke="currentColor" strokeWidth="1.5" />
        <path d="M12 3C14.5 6.5 16 9.5 16 12C16 14.5 14.5 17.5 12 21C9.5 17.5 8 14.5 8 12C8 9.5 9.5 6.5 12 3Z" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    id: 'wordLookup',
    label: 'Word Lookup',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 19.5C4 18.837 4.26339 18.2011 4.73223 17.7322C5.20107 17.2634 5.83696 17 6.5 17H20V3H6.5C5.83696 3 5.20107 3.26339 4.73223 3.73223C4.26339 4.20107 4 4.83696 4 5.5V19.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M6.5 17C5.83696 17 5.20107 17.2634 4.73223 17.7322C4.26339 18.2011 4 18.837 4 19.5C4 20.163 4.26339 20.7989 4.73223 21.2678C5.20107 21.7366 5.83696 22 6.5 22H20V17H6.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

export function App({
  suggestions,
  sourceText,
  apply = applyOperations,
  document: documentApi,
  daemonStatus,
  daemonBaseUrl,
  onRetryDaemonConnection,
  analysisStatus,
  analysisError,
  onRefreshAnalysis,
  isOnline,
}: AppProps): JSX.Element {
  const styles = useStyles();
  const { name: themeName, theme, toggle } = useOfficeTheme();
  const [tab, setTab] = React.useState<PaneTab>('review');
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const undo = useUndoStack({ apply });
  const engine = useSuggestionEngine(suggestions, { apply });
  const cloudAI = useCloudAI();
  const plagiarism = usePlagiarism({
    getText: async () => sourceText,
    ...(daemonBaseUrl !== undefined ? { baseUrl: daemonBaseUrl } : {}),
  });

  const write = documentApi ?? {
    replaceSelection,
    insertAfterSelection,
  };

  const applyOne = React.useCallback(
    async (suggestionItem: Suggestion) => {
      const command = await engine.applyOne(suggestionItem);
      if (command !== null) {
        undo.pushCommand(command);
        engine.dismiss(suggestionItem.id);
      }
    },
    [engine, undo],
  );

  const applyBatch = React.useCallback(async () => {
    const command = await engine.applyBatch();
    if (command !== null) {
      undo.pushCommand(command);
      for (const id of command.suggestionIds) {
        engine.dismiss(id);
      }
    }
  }, [engine, undo]);

  const commitSelected = React.useCallback(() => {
    const suggestionItem = engine.ordered.find((item) => item.id === selectedId);
    if (suggestionItem !== undefined) {
      void applyOne(suggestionItem);
    }
  }, [engine.ordered, selectedId, applyOne]);

  useKeyboardShortcuts({
    onUndo: () => void undo.executeUndo(),
    onRedo: () => void undo.executeRedo(),
    onCommit: commitSelected,
    onStop: cloudAI.stopGeneration,
  });

  const criticalCount = React.useMemo(
    () => engine.ordered.filter((item) => item.severity === 'critical').length,
    [engine.ordered],
  );

  const busy = undo.isBusy || engine.isApplying;
  const isLoadingOverlayVisible = daemonStatus === 'checking' || analysisStatus === 'loading';

  const [loadingStep, setLoadingStep] = React.useState(0);

  React.useEffect(() => {
    if (!isLoadingOverlayVisible) {
      setLoadingStep(0);
      return;
    }
    const timer1 = setTimeout(() => setLoadingStep(1), 1200);
    const timer2 = setTimeout(() => setLoadingStep(2), 2500);
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  }, [isLoadingOverlayVisible]);

  const loadingSubtitles = [
    daemonStatus === 'checking'
      ? 'Handshaking with local daemon...'
      : 'Scanning your document...',
    'Loading spelling engine & Tibetan dictionary...',
    'Initializing TiBERT grammar parser & local model...',
  ];

  const renderOnlineFeature = (component: JSX.Element) => {
    if (isOnline === false) {
      return (
        <MessageBar intent="warning">
          <MessageBarBody>
            This feature requires an internet connection. Your offline Spelling & Grammar are still available in the first tab.
          </MessageBarBody>
        </MessageBar>
      );
    }
    return component;
  };

  return (
    <FluentProvider theme={theme} className={styles.rootContainer}>
      {/* Step 1: On The Way Loading Overlay */}
      {isLoadingOverlayVisible ? (
        <div className={styles.loadingOverlay}>
          <Spinner size="large" />
          <Text weight="bold" size={500} style={{ color: '#ffffff' }}>
            On The Way
          </Text>
          <Text size={300} style={{ color: '#cccccc' }}>
            {loadingSubtitles[loadingStep] || loadingSubtitles[0]}
          </Text>
        </div>
      ) : null}

      {/* Step 2: Vertical Sidebar Navigation with Custom SVG Icons */}
      <nav className={styles.sidebar} aria-label="Add-in navigation">
        {NAV_ITEMS.map((item) => {
          const isActive = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              title={item.label}
              aria-label={item.label}
              className={`${styles.navButton} ${isActive ? styles.activeNavButton : ''}`}
              onClick={() => setTab(item.id)}
            >
              {item.icon}
            </button>
          );
        })}
      </nav>

      {/* Content Area */}
      <main className={styles.contentArea}>
        <header className={styles.header}>
          <Text weight="semibold" size={400}>
            TEEA
          </Text>
          <span
            className={`${styles.statusDot} ${
              daemonStatus === 'connected' ? styles.statusConnected : styles.statusDisconnected
            }`}
            aria-label={daemonStatus === 'connected' ? 'Daemon connected' : 'Daemon disconnected'}
            title={daemonStatus === 'connected' ? 'Daemon connected' : 'Daemon disconnected'}
          />
          <Switch
            className={styles.spacer}
            checked={themeName === 'dark'}
            onChange={toggle}
            label="Dark"
          />
        </header>

        {isOnline === false ? (
          <MessageBar intent="info">
            <MessageBarBody>
              No network connection. TEEA analyzes and assists entirely on this
              machine, so this does not affect the suggestions below or the
              local assistant.
            </MessageBarBody>
          </MessageBar>
        ) : null}

        {daemonStatus !== undefined && daemonStatus !== 'connected' ? (
          <MessageBar intent={daemonStatus === 'checking' ? 'info' : 'warning'}>
            <MessageBarBody>
              {daemonStatus === 'checking'
                ? `Checking for the local daemon${daemonBaseUrl ? ` at ${daemonBaseUrl}` : ''}…`
                : `Local daemon not reachable${daemonBaseUrl ? ` at ${daemonBaseUrl}` : ''}. The assistant will not respond until it starts.`}
              {daemonStatus === 'unavailable' && onRetryDaemonConnection !== undefined ? (
                <Button
                  appearance="transparent"
                  size="small"
                  onClick={onRetryDaemonConnection}
                >
                  Retry connection
                </Button>
              ) : null}
            </MessageBarBody>
          </MessageBar>
        ) : null}

        {/* Tab Panel Views */}
        {tab === 'review' ? (
          <>
            <div className={styles.analysisBar}>
              {onRefreshAnalysis !== undefined ? (
                <Button
                  appearance="secondary"
                  size="small"
                  onClick={onRefreshAnalysis}
                  disabled={analysisStatus === 'loading'}
                >
                  Refresh analysis
                </Button>
              ) : null}
              {analysisStatus === 'loading' ? (
                <Spinner size="tiny" label="AI checking Tibetan spelling..." />
              ) : null}
            </div>

            {analysisStatus === 'unavailable' || analysisStatus === 'error' ? (
              <MessageBar intent={analysisStatus === 'unavailable' ? 'warning' : 'error'}>
                <MessageBarBody>
                  {analysisStatus === 'unavailable'
                    ? 'The local TEEA daemon is not reachable, so suggestions could ' +
                      'not be refreshed. Start the daemon and try again.'
                    : `Analysis failed${analysisError ? `: ${analysisError}` : '.'}`}
                </MessageBarBody>
              </MessageBar>
            ) : null}

            <BatchActionBar
              total={engine.total}
              criticalCount={criticalCount}
              autoApplicableCount={engine.autoApplicable.length}
              canUndo={undo.canUndo}
              canRedo={undo.canRedo}
              busy={busy}
              onApplyBatch={() => void applyBatch()}
              onUndo={() => void undo.executeUndo()}
              onRedo={() => void undo.executeRedo()}
            />
            {analysisStatus === 'loading' ? (
              <div className={styles.groups}>
                <Skeleton>
                  <div className={styles.skeletonCard}>
                    <SkeletonItem shape="rectangle" size={16} style={{ width: '40%' }} />
                    <SkeletonItem shape="rectangle" size={16} style={{ width: '80%' }} />
                    <SkeletonItem shape="rectangle" size={32} style={{ width: '60%' }} />
                  </div>
                </Skeleton>
                <Skeleton>
                  <div className={styles.skeletonCard}>
                    <SkeletonItem shape="rectangle" size={16} style={{ width: '30%' }} />
                    <SkeletonItem shape="rectangle" size={16} style={{ width: '90%' }} />
                    <SkeletonItem shape="rectangle" size={32} style={{ width: '50%' }} />
                  </div>
                </Skeleton>
                <Skeleton>
                  <div className={styles.skeletonCard}>
                    <SkeletonItem shape="rectangle" size={16} style={{ width: '50%' }} />
                    <SkeletonItem shape="rectangle" size={16} style={{ width: '70%' }} />
                    <SkeletonItem shape="rectangle" size={32} style={{ width: '40%' }} />
                  </div>
                </Skeleton>
              </div>
            ) : engine.groups.length === 0 ? (
              <div className={styles.empty}>
                <Text>No suggestions. The document reads clean.</Text>
              </div>
            ) : (
              <div className={styles.groups}>
                {engine.groups.map((group) => (
                  <SuggestionGroup
                    key={group.category}
                    group={group}
                    onApply={(suggestionItem) => void applyOne(suggestionItem)}
                    onDismiss={engine.dismiss}
                    virtualized={engine.needsVirtualization}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                    disabled={busy}
                  />
                ))}
              </div>
            )}
          </>
        ) : tab === 'plagiarism' ? (
          <PlagiarismPanel
            result={plagiarism.result}
            status={plagiarism.status}
            error={plagiarism.error}
            onCheck={plagiarism.check}
            onClearHighlights={async () => {
              if (plagiarism.result?.matches) {
                const ranges = plagiarism.result.matches
                  .filter((m) => m.source_span !== null)
                  .map((m) => {
                    const s = m.source_span!;
                    return {
                      start: s.char_start,
                      length: s.char_end - s.char_start,
                      originalText: sourceText.slice(s.char_start, s.char_end),
                    };
                  });
                await clearPlagiarismHighlights(ranges);
              }
            }}
            onHighlightMatch={async (m: PlagiarismMatch) => {
              if (m.source_span) {
                const s = m.source_span;
                await highlightPlagiarismMatches([
                  {
                    start: s.char_start,
                    length: s.char_end - s.char_start,
                    originalText: sourceText.slice(s.char_start, s.char_end),
                  },
                ]);
              }
            }}
            onInsertCitation={insertFootnoteCitation}
            documentText={sourceText}
          />
        ) : tab === 'assistant' ? (
          renderOnlineFeature(
            <AIPanel
              assistant={cloudAI}
              sourceText={sourceText}
              onReplaceSelection={write.replaceSelection}
              onInsertBelow={write.insertAfterSelection}
              isOnline={isOnline}
            />,
          )
        ) : tab === 'stt' ? (
          renderOnlineFeature(
            <SpeechToTextPanel onInsertText={write.insertAfterSelection} />,
          )
        ) : tab === 'tts' ? (
          renderOnlineFeature(
            <TextToSpeechPanel sourceText={sourceText} />,
          )
        ) : tab === 'ocr' ? (
          renderOnlineFeature(
            <OCRPanel onInsertText={write.insertAfterSelection} />,
          )
        ) : tab === 'translate' ? (
          renderOnlineFeature(
            <TranslationPanel
              sourceText={sourceText}
              onReplaceSelection={write.replaceSelection}
              onInsertBelow={write.insertAfterSelection}
            />,
          )
        ) : (
          renderOnlineFeature(
            <WordLookupPanel isOnline={isOnline} onInsertText={write.insertAfterSelection} />,
          )
        )}
      </main>
    </FluentProvider>
  );
}
