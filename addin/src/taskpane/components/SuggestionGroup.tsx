/**
 * One category's worth of suggestions, collapsible.
 *
 * Above {@link VIRTUALIZATION_THRESHOLD} cards across the whole pane the rows
 * are windowed; below it they are rendered outright, because windowing a short
 * list costs a scroll container and gains nothing.
 */

import * as React from 'react';
import {
  Accordion,
  AccordionHeader,
  AccordionItem,
  AccordionPanel,
  Badge,
  Text,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import type { Suggestion } from '../types/ipc';
import type { SuggestionGroupModel } from '../hooks/useSuggestionEngine';
import { SuggestionItem } from './SuggestionItem';
import { VirtualizedList } from './VirtualizedList';

/** Row height used by the windowed list, in pixels. */
export const ROW_HEIGHT = 168;

/** Viewport height used by the windowed list, in pixels. */
export const WINDOW_HEIGHT = 520;

const useStyles = makeStyles({
  header: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
  },
  stack: {
    display: 'flex',
    flexDirection: 'column',
    rowGap: tokens.spacingVerticalS,
  },
});

export interface SuggestionGroupProps {
  group: SuggestionGroupModel;
  onApply: (suggestion: Suggestion) => void;
  onDismiss: (id: string) => void;
  virtualized: boolean;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  disabled?: boolean;
}

function SuggestionGroupComponent({
  group,
  onApply,
  onDismiss,
  virtualized,
  selectedId = null,
  onSelect,
  disabled = false,
}: SuggestionGroupProps): JSX.Element {
  const styles = useStyles();

  const renderRow = React.useCallback(
    (suggestion: Suggestion) => (
      <SuggestionItem
        suggestion={suggestion}
        onApply={onApply}
        onDismiss={onDismiss}
        selected={suggestion.id === selectedId}
        {...(onSelect === undefined ? {} : { onSelect })}
        disabled={disabled}
      />
    ),
    [onApply, onDismiss, selectedId, onSelect, disabled],
  );

  return (
    <Accordion collapsible defaultOpenItems={group.category}>
      <AccordionItem value={group.category}>
        <AccordionHeader>
          <span className={styles.header}>
            <Text weight="semibold">{group.category}</Text>
            <Badge appearance="filled" size="small">
              {group.suggestions.length}
            </Badge>
            {group.criticalCount > 0 ? (
              <Badge appearance="filled" color="danger" size="small">
                {group.criticalCount} critical
              </Badge>
            ) : null}
          </span>
        </AccordionHeader>
        <AccordionPanel>
          {virtualized ? (
            <VirtualizedList
              items={group.suggestions}
              itemHeight={ROW_HEIGHT}
              height={Math.min(
                WINDOW_HEIGHT,
                group.suggestions.length * ROW_HEIGHT,
              )}
              keyOf={(suggestion) => suggestion.id}
              label={`${group.category} suggestions`}
            >
              {renderRow}
            </VirtualizedList>
          ) : (
            <div
              className={styles.stack}
              role="list"
              aria-label={`${group.category} suggestions`}
            >
              {group.suggestions.map((suggestion) => (
                <div role="listitem" key={suggestion.id}>
                  {renderRow(suggestion)}
                </div>
              ))}
            </div>
          )}
        </AccordionPanel>
      </AccordionItem>
    </Accordion>
  );
}

export const SuggestionGroup = React.memo(
  SuggestionGroupComponent,
  (previous, next) =>
    previous.group === next.group &&
    previous.virtualized === next.virtualized &&
    previous.selectedId === next.selectedId &&
    previous.disabled === next.disabled,
);

SuggestionGroup.displayName = 'SuggestionGroup';
