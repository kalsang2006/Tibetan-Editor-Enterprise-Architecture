/**
 * The task pane: suggestion review above, the local assistant below.
 *
 * This is the composition root. Every collaborator that touches the outside
 * world — the document, the daemon, the clock — arrives as a prop, which is what
 * lets the whole pane be mounted in a test with no Office host present.
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
  Tab,
  TabList,
  Text,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import { AIPanel } from './components/AIPanel';
import { BatchActionBar } from './components/BatchActionBar';
import { SuggestionGroup } from './components/SuggestionGroup';
import { useAIAssistant } from './hooks/useAIAssistant';
import type { AnalysisStatus } from './hooks/useDocumentAnalysis';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useOfficeTheme } from './hooks/useOfficeTheme';
import { useSuggestionEngine } from './hooks/useSuggestionEngine';
import { useUndoStack } from './hooks/useUndoStack';
import type { StreamTransport } from './services/IpcBridge';
import {
  applyOperations,
  insertAfterSelection,
  replaceSelection,
} from './services/WordDocument';
import type { Suggestion } from './types/ipc';

const useStyles = makeStyles({
  root: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalM,
    width: '100%',
    height: '100%',
    overflowY: 'auto',
    boxSizing: 'border-box',
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
  /** How an AI request becomes a token stream. */
  transport: StreamTransport;
  /** The IPC session, once established. */
  sessionId?: string | null;
  /** How operations reach the document. Injected for tests. */
  apply?: typeof applyOperations;
  /** How the assistant's output reaches the document. Injected for tests. */
  document?: {
    replaceSelection: (text: string) => Promise<void>;
    insertAfterSelection: (text: string) => Promise<void>;
  };
  /**
   * Whether `transport` is backed by a confirmed-reachable daemon. Omit
   * entirely for a transport that needs no such banner, e.g. in a test that
   * injects its own -- the banner only renders once a status is actually
   * supplied, so existing callers that never pass it see no change.
   */
  daemonStatus?: 'checking' | 'connected' | 'unavailable';
  /** The origin `daemonStatus` describes, shown in the banner's message. */
  daemonBaseUrl?: string;
  /** Re-run the daemon health check. Shown as the banner's action. */
  onRetryDaemonConnection?: () => void;
  /**
   * Where the current document analysis stands. Omit entirely for a caller
   * that supplies suggestions some other way and needs no status bar -- e.g.
   * an existing test that passes a fixed `suggestions` array -- the same
   * opt-in shape `daemonStatus` already uses.
   */
  analysisStatus?: AnalysisStatus;
  /** Set when `analysisStatus` is `'error'` or `'unavailable'`. */
  analysisError?: string | null;
  /** Re-read the document and re-run analysis. Shown as a toolbar button. */
  onRefreshAnalysis?: () => void;
  /** Whether the host reports a network connection. Omit to show no banner. */
  isOnline?: boolean;
}

type PaneTab = 'review' | 'assistant';

export function App({
  suggestions,
  sourceText,
  transport,
  sessionId = null,
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
  const assistant = useAIAssistant({ transport, sessionId });

  const write = documentApi ?? {
    replaceSelection,
    insertAfterSelection,
  };

  const applyOne = React.useCallback(
    async (suggestion: Suggestion) => {
      const command = await engine.applyOne(suggestion);
      if (command !== null) {
        undo.pushCommand(command);
        engine.dismiss(suggestion.id);
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
    const suggestion = engine.ordered.find((item) => item.id === selectedId);
    if (suggestion !== undefined) {
      void applyOne(suggestion);
    }
  }, [engine.ordered, selectedId, applyOne]);

  useKeyboardShortcuts({
    onUndo: () => void undo.executeUndo(),
    onRedo: () => void undo.executeRedo(),
    onCommit: commitSelected,
    onStop: assistant.stopGeneration,
  });

  const criticalCount = React.useMemo(
    () => engine.ordered.filter((item) => item.severity === 'critical').length,
    [engine.ordered],
  );

  const busy = undo.isBusy || engine.isApplying;

  const handleInsertSample = React.useCallback(async () => {
    const sampleText = "བོད་ཀྱི་སྐད་ཡིག་སྐོར་ལ་སློབ་སྦྱོང་བྱས་ནི་ཧ་བཅང་གལ་ཆེན་ཡིན། དེང་རབས་འདིར་མི་མང་པོས་བོད་ཡིག་ལ་དགའ་སྤྲོ་ཆེན་ཕོ་ཡོད་ནའང་། སློབ་སྦྱོང་བྱས་ཆེད་དུས་ཚོད་བཅང་པོ་མེད། ཡིན་ནའང་ང་ཚོ་ཤེས་ཡོན་མེད་ན་མུན་ནག་ནང་འགྲོ་བ་དང་འདྲ་སྟེ། མི་མང་པོས་ཡིག་ཆ་ཀློ་ཅིང་ཤེས་རིག་བཟང་སྤྱོད་བོང་བརྩོན་བྱེད་ཀྱི་ཡོད། དེ་བས་ང་ཚོས་ནམ་ཡང་སློབ་སྦྱོང་ལ་འབད་དགོས་པ་དང་། བོད་ཡིག་གི་མཛེས་སྡུག་རྟོགས་དགོས། མདོར་ན་སྐད་ཡིག་ནི་མི་ཚེའི་མཛེས་རྒྱན་ཡིན་པས། ང་ཚོས་དེ་ཉར་ཚགས་བྱེད་དགོས།";
    try {
      if (documentApi?.replaceSelection) {
        await documentApi.replaceSelection(sampleText);
      } else {
        await replaceSelection(sampleText);
      }
      onRefreshAnalysis?.();
    } catch {
      // Ignored outside active Word host
    }
  }, [documentApi, onRefreshAnalysis]);

  return (
    <FluentProvider theme={theme} className={styles.root}>
      <header className={styles.header}>
        <Text weight="semibold" size={400}>
          TEEA
        </Text>
        <span 
          className={`${styles.statusDot} ${daemonStatus === 'connected' ? styles.statusConnected : styles.statusDisconnected}`} 
          aria-label={daemonStatus === 'connected' ? "Daemon connected" : "Daemon disconnected"}
          title={daemonStatus === 'connected' ? "Daemon connected" : "Daemon disconnected"}
        />
        <Button
          appearance="subtle"
          size="small"
          onClick={handleInsertSample}
          title="Insert Tibetan Demo Sample Paragraph"
        >
          Demo Sample
        </Button>
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

      <TabList
        selectedValue={tab}
        onTabSelect={(_event, data) => setTab(data.value as PaneTab)}
      >
        <Tab value="review">Suggestions</Tab>
        <Tab value="assistant">Assistant</Tab>
      </TabList>

      {tab === 'review' ? (
        <>
          {onRefreshAnalysis !== undefined ? (
            <div className={styles.analysisBar}>
              <Button
                appearance="secondary"
                size="small"
                onClick={onRefreshAnalysis}
                disabled={analysisStatus === 'loading'}
              >
                Refresh analysis
              </Button>
              {analysisStatus === 'loading' ? (
                <Spinner size="tiny" label="AI checking Tibetan spelling..." />
              ) : null}
            </div>
          ) : null}

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
                  onApply={(suggestion) => void applyOne(suggestion)}
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
      ) : (
        <AIPanel
          assistant={assistant}
          sourceText={sourceText}
          onReplaceSelection={write.replaceSelection}
          onInsertBelow={write.insertAfterSelection}
        />
      )}
    </FluentProvider>
  );
}
