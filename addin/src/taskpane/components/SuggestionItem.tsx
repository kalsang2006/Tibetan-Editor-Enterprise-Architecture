/**
 * One reviewable suggestion card.
 *
 * `React.memo` with a shallow comparison: the pane re-renders on every document
 * change, and a suggestion object is replaced only when the analysis that
 * produced it is. Shallow identity is therefore exactly the right test, and a
 * deep comparison would cost more than the render it saves.
 */

import * as React from 'react';
import {
  Badge,
  Button,
  MessageBar,
  MessageBarBody,
  MessageBarTitle,
  ProgressBar,
  Text,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import type { Suggestion, SuggestionSeverity } from '../types/ipc';

/**
 * Severity to the Fluent `MessageBar` intent.
 *
 * The specification asked for `danger`; Fluent UI v9's `MessageBar` accepts
 * `info | success | warning | error`, so the critical case maps to `error`,
 * which is the same visual treatment under the name the library actually has.
 */
export const SEVERITY_INTENT: Record<
  SuggestionSeverity,
  'error' | 'warning' | 'info'
> = {
  critical: 'error',
  warning: 'warning',
  suggestion: 'info',
};

/** Severity to the words a screen reader announces. */
export const SEVERITY_LABEL: Record<SuggestionSeverity, string> = {
  critical: 'Critical',
  warning: 'Warning',
  suggestion: 'Suggestion',
};

const useStyles = makeStyles({
  card: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalXS,
  },
  texts: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalXXS,
  },
  original: {
    textDecorationLine: 'line-through',
    color: tokens.colorNeutralForeground3,
    wordBreak: 'break-word',
  },
  replacement: {
    fontWeight: tokens.fontWeightSemibold,
    wordBreak: 'break-word',
  },
  meta: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
  },
  confidence: {
    flexGrow: 1,
    minWidth: '80px',
  },
  actions: {
    display: 'flex',
    columnGap: tokens.spacingHorizontalS,
  },
});

export interface SuggestionItemProps {
  suggestion: Suggestion;
  onApply: (suggestion: Suggestion) => void;
  onDismiss: (id: string) => void;
  /** Whether this card is the keyboard commit target. */
  selected?: boolean;
  onSelect?: (id: string) => void;
  disabled?: boolean;
}

function SuggestionItemComponent({
  suggestion,
  onApply,
  onDismiss,
  selected = false,
  onSelect,
  disabled = false,
}: SuggestionItemProps): JSX.Element {
  const styles = useStyles();
  const percent = Math.round(suggestion.confidence * 100);

  const apply = React.useCallback(() => onApply(suggestion), [onApply, suggestion]);
  const dismiss = React.useCallback(
    () => onDismiss(suggestion.id),
    [onDismiss, suggestion.id],
  );
  const select = React.useCallback(
    () => onSelect?.(suggestion.id),
    [onSelect, suggestion.id],
  );

  return (
    <MessageBar
      intent={SEVERITY_INTENT[suggestion.severity]}
      onFocus={select}
      onClick={select}
      data-selected={selected ? 'true' : undefined}
      aria-current={selected ? 'true' : undefined}
    >
      <MessageBarBody className={styles.card}>
        <MessageBarTitle>
          {SEVERITY_LABEL[suggestion.severity]}: {suggestion.category}
        </MessageBarTitle>

        <div className={styles.texts}>
          <Text className={styles.original} aria-label="Current text">
            {suggestion.originalText}
          </Text>
          <Text className={styles.replacement} aria-label="Suggested text">
            {suggestion.suggestedText}
          </Text>
        </div>

        <Text size={200}>{suggestion.explanation}</Text>

        <div className={styles.meta}>
          <Badge appearance="tint" size="small">
            {suggestion.ruleId}
          </Badge>
          <div className={styles.confidence}>
            <ProgressBar
              value={suggestion.confidence}
              max={1}
              thickness="medium"
              aria-label={`Confidence ${suggestion.confidence.toFixed(2)}`}
            />
          </div>
          <Text size={200}>{suggestion.confidence.toFixed(2)}</Text>
          <Text size={100} aria-hidden="true">
            {percent}%
          </Text>
        </div>

        <div className={styles.actions}>
          <Button
            appearance="primary"
            size="small"
            onClick={apply}
            disabled={disabled}
          >
            Apply
          </Button>
          <Button appearance="subtle" size="small" onClick={dismiss}>
            Dismiss
          </Button>
        </div>
      </MessageBarBody>
    </MessageBar>
  );
}

/**
 * Shallow-compared card.
 *
 * Only the props that change what is drawn are compared. `onApply`, `onDismiss`
 * and `onSelect` are excluded deliberately: the parent memoizes them with
 * `useCallback`, and including them would reduce the memo to an identity check
 * on functions that are stable anyway.
 */
export const SuggestionItem = React.memo(
  SuggestionItemComponent,
  (previous, next) =>
    previous.suggestion === next.suggestion &&
    previous.selected === next.selected &&
    previous.disabled === next.disabled,
);

SuggestionItem.displayName = 'SuggestionItem';
