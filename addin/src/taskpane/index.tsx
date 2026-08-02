/**
 * Task pane entry point.
 *
 * Nothing renders until `Office.onReady` resolves: the host injects `Office` and
 * `Word` asynchronously, and a component that touched `Office.context` before
 * that would see `undefined` on a cold start and show the user a blank pane.
 *
 * Two independent daemon bridges are wired up here:
 * {@link useDocumentAnalysis} drives the Suggestions tab against
 * `teea.transport.analysis_server`'s `/api/analysis/run`, and
 * {@link useDaemonTransport} drives the Assistant tab against an AI bridge
 * that -- per ADR-019 -- has no concrete inference engine behind it yet and so
 * degrades to its own "not reachable" state. Both fail independently: a
 * daemon that serves analysis but has no model loaded shows suggestions and a
 * quiet assistant tab, not a single all-or-nothing error.
 */

import * as React from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { useDaemonTransport } from './hooks/useDaemonTransport';
import { useDocumentAnalysis } from './hooks/useDocumentAnalysis';
import { useOnlineStatus } from './hooks/useOnlineStatus';
import { DaemonFaultError } from './services/IpcBridge';
import { isLargeDocument, readDocumentText, readSelectionText } from './services/WordDocument';

/** How long to wait, after a selection change settles, before re-reading it. */
const SELECTION_DEBOUNCE_MS = 300;

/**
 * Read the text the assistant should act on.
 *
 * The selection when there is one; otherwise the document. The document read
 * goes through the slicing path above {@link isLargeDocument}'s threshold, which
 * is why the length is checked before the text is used rather than after.
 */
export async function readSourceText(): Promise<string> {
  const selection = await readSelectionText();
  if (selection.trim().length > 0) {
    return selection;
  }
  const document = await readDocumentText();
  if (isLargeDocument(document.length)) {
    // A book-length document is the background pipeline's job (SRS 3.2), not the
    // interactive path's. The assistant gets the opening context, and the pane
    // says so rather than silently truncating.
    return document.slice(0, 5000);
  }
  return document;
}

/**
 * Read the text the Suggestions tab analyzes: always the whole document.
 *
 * Unlike {@link readSourceText}, a selection never narrows this -- a grammar
 * checker that stopped covering the rest of the document the moment the user
 * clicked into one paragraph would silently hide suggestions elsewhere in it.
 */
export async function readAnalysisText(): Promise<string> {
  // Always read the full document, ignore any selection.
  return readDocumentText();
}

/**
 * Register a handler for Word's selection-changed event, Office.js-callback
 * style, and return an unsubscribe function.
 *
 * Guarded the same way every other host call here is: some hosts (the test
 * harness, older builds) do not expose `addHandlerAsync` at all.
 */
function onSelectionChanged(handler: () => void): () => void {
  const office = globalThis.Office as unknown as
    | {
        context?: {
          document?: {
            addHandlerAsync?: (
              eventType: unknown,
              callback: () => void,
              options: unknown,
              done?: (result: unknown) => void,
            ) => void;
            removeHandlerAsync?: (
              eventType: unknown,
              options: unknown,
              done?: (result: unknown) => void,
            ) => void;
          };
        };
        EventType?: { DocumentSelectionChanged?: unknown };
      }
    | undefined;
  const document = office?.context?.document;
  const eventType = office?.EventType?.DocumentSelectionChanged;
  if (document?.addHandlerAsync === undefined || eventType === undefined) {
    return () => undefined;
  }
  document.addHandlerAsync(eventType, handler, {});
  return () => {
    document.removeHandlerAsync?.(eventType, {});
  };
}

function Bootstrap(): JSX.Element {
  const [sourceText, setSourceText] = React.useState('');
  const isOnline = useOnlineStatus();
  const daemon = useDaemonTransport();
  const analysis = useDocumentAnalysis({ getText: readAnalysisText });

  React.useEffect(() => {
    let cancelled = false;
    const load = (): void => {
      readSourceText()
        .then((text) => {
          if (!cancelled) {
            setSourceText(text);
          }
        })
        .catch((error: unknown) => {
          if (!cancelled && !(error instanceof DaemonFaultError)) {
            setSourceText('');
          }
        });
      analysis.refresh();
    };

    load();

    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = onSelectionChanged(() => {
      // Debounced: Word can fire this event repeatedly while a selection is
      // still being dragged, and re-reading on every intermediate frame would
      // queue far more Word.run calls than the assistant tab ever needs.
      if (timer !== undefined) {
        clearTimeout(timer);
      }
      timer = setTimeout(load, SELECTION_DEBOUNCE_MS);
    });

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
      unsubscribe();
    };
  }, []);

  return (
    <App
      suggestions={analysis.suggestions}
      sourceText={sourceText}
      daemonStatus={daemon.status}
      daemonBaseUrl={daemon.baseUrl}
      onRetryDaemonConnection={daemon.retry}
      analysisStatus={analysis.status}
      analysisError={analysis.error}
      onRefreshAnalysis={analysis.refresh}
      isOnline={isOnline}
    />
  );
}

const container = document.getElementById('container');
if (container !== null) {
  Office.onReady(() => {
    createRoot(container).render(
      <React.StrictMode>
        <Bootstrap />
      </React.StrictMode>,
    );
  });
}
