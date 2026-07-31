import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { FluentProvider, webLightTheme } from '@fluentui/react-components';
import { PlagiarismPanel } from '../src/taskpane/components/PlagiarismPanel';

describe('PlagiarismPanel', () => {
  void React;
  it('renders check button and triggers onCheck', () => {
    const onCheck = jest.fn().mockResolvedValue(undefined);
    const onClear = jest.fn().mockResolvedValue(undefined);

    render(
      <FluentProvider theme={webLightTheme}>
        <PlagiarismPanel
          onCheck={onCheck}
          onClearHighlights={onClear}
          result={null}
          status="idle"
          error={null}
          documentText=""
        />
      </FluentProvider>,
    );

    const btn = screen.getByText('Check Plagiarism');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onCheck).toHaveBeenCalledTimes(1);
  });

  it('renders clean document state when 100% original', () => {
    const onCheck = jest.fn().mockResolvedValue(undefined);
    const onClear = jest.fn().mockResolvedValue(undefined);

    render(
      <FluentProvider theme={webLightTheme}>
        <PlagiarismPanel
          onCheck={onCheck}
          onClearHighlights={onClear}
          result={{
            originality_score: 100,
            matches: [],
            query_fingerprint_count: 5,
            total_corpus_documents: 10,
            elapsed_ms: 1.2,
          }}
          status="ready"
          error={null}
          documentText="some text"
        />
      </FluentProvider>,
    );

    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('✨ Clean Document')).toBeInTheDocument();
  });

  it('renders matches list when plagiarism detected', () => {
    const onCheck = jest.fn().mockResolvedValue(undefined);
    const onClear = jest.fn().mockResolvedValue(undefined);
    const onHighlight = jest.fn().mockResolvedValue(undefined);

    render(
      <FluentProvider theme={webLightTheme}>
        <PlagiarismPanel
          onCheck={onCheck}
          onClearHighlights={onClear}
          onHighlightMatch={onHighlight}
          result={{
            originality_score: 75.0,
            matches: [
              {
                document_id: 'corpus_doc_1',
                similarity: 0.25,
                coverage: 0.5,
                overlap_count: 5,
                query_fingerprint_count: 20,
                doc_fingerprint_count: 10,
                source_span: { char_start: 0, char_end: 9, byte_start: 0, byte_end: 27 },
              },
            ],
            query_fingerprint_count: 20,
            total_corpus_documents: 5,
            elapsed_ms: 2.1,
          }}
          status="ready"
          error={null}
          documentText="copied text snippet"
        />
      </FluentProvider>,
    );

    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('⚠️ 1 Match(es) Found')).toBeInTheDocument();
    expect(screen.getByText('📖 Manuscript corpus_d')).toBeInTheDocument();

    const card = screen.getByText('📖 Manuscript corpus_d');
    fireEvent.click(card);
    expect(onHighlight).toHaveBeenCalledTimes(1);
  });
});
