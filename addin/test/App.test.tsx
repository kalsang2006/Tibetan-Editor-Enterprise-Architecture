import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { App } from '../src/taskpane/App';
import { unavailableTransport } from '../src/taskpane/hooks/useDaemonTransport';

const baseProps = {
  suggestions: [],
  sourceText: '',
  transport: unavailableTransport,
};

describe('App', () => {
  it('renders no analysis controls when onRefreshAnalysis is omitted', () => {
    render(<App {...baseProps} />);

    expect(screen.queryByRole('button', { name: 'Refresh analysis' })).toBeNull();
  });

  it('shows a refresh button and runs the callback', async () => {
    const onRefreshAnalysis = jest.fn();
    const user = userEvent.setup();
    render(<App {...baseProps} onRefreshAnalysis={onRefreshAnalysis} />);

    await user.click(screen.getByRole('button', { name: 'Refresh analysis' }));

    expect(onRefreshAnalysis).toHaveBeenCalledTimes(1);
  });

  it('disables refresh while analysis is loading', () => {
    render(
      <App {...baseProps} onRefreshAnalysis={jest.fn()} analysisStatus="loading" />,
    );

    expect(screen.getByRole('button', { name: 'Refresh analysis' })).toBeDisabled();
  });

  it('reports an unavailable daemon distinctly from a handler failure', () => {
    const { rerender } = render(
      <App {...baseProps} onRefreshAnalysis={jest.fn()} analysisStatus="unavailable" />,
    );
    expect(screen.getByText(/daemon is not reachable/)).toBeInTheDocument();

    rerender(
      <App
        {...baseProps}
        onRefreshAnalysis={jest.fn()}
        analysisStatus="error"
        analysisError="boom"
      />,
    );
    expect(screen.getByText('Analysis failed: boom')).toBeInTheDocument();
  });

  it('shows no offline banner unless isOnline is explicitly false', () => {
    render(<App {...baseProps} />);
    expect(screen.queryByText(/No network connection/)).toBeNull();
  });

  it('shows a reassuring offline banner without alarming language', () => {
    render(<App {...baseProps} isOnline={false} />);
    expect(screen.getByText(/No network connection/)).toBeInTheDocument();
  });

  it('says nothing is wrong when the analysis is ready with an empty list', () => {
    render(<App {...baseProps} onRefreshAnalysis={jest.fn()} analysisStatus="ready" />);
    expect(screen.getByText('No suggestions. The document reads clean.')).toBeInTheDocument();
  });
});
