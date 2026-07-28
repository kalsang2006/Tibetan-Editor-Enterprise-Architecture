/**
 * The bar above the review list: counts, batch apply, undo and redo.
 *
 * The batch button states its own scope in its label. "Apply 12 safe fixes" is
 * a promise the user can check against the list; "Apply all" is one they cannot,
 * and this batch deliberately excludes every critical suggestion.
 */

import * as React from 'react';
import {
  Badge,
  Button,
  Text,
  Toolbar,
  Tooltip,
  makeStyles,
  tokens,
} from '@fluentui/react-components';

import { AUTO_APPLY_CONFIDENCE } from '../hooks/useSuggestionEngine';

const useStyles = makeStyles({
  bar: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalS,
    rowGap: tokens.spacingVerticalXS,
    flexWrap: 'wrap',
    paddingBottom: tokens.spacingVerticalS,
  },
  counts: {
    display: 'flex',
    alignItems: 'center',
    columnGap: tokens.spacingHorizontalXS,
    marginInlineEnd: 'auto',
  },
});

export interface BatchActionBarProps {
  total: number;
  criticalCount: number;
  autoApplicableCount: number;
  canUndo: boolean;
  canRedo: boolean;
  busy: boolean;
  onApplyBatch: () => void;
  onUndo: () => void;
  onRedo: () => void;
}

function BatchActionBarComponent({
  total,
  criticalCount,
  autoApplicableCount,
  canUndo,
  canRedo,
  busy,
  onApplyBatch,
  onUndo,
  onRedo,
}: BatchActionBarProps): JSX.Element {
  const styles = useStyles();
  const batchLabel =
    autoApplicableCount === 0
      ? 'No safe fixes'
      : `Apply ${autoApplicableCount} safe ${
          autoApplicableCount === 1 ? 'fix' : 'fixes'
        }`;

  return (
    <Toolbar className={styles.bar} aria-label="Suggestion actions">
      <span className={styles.counts}>
        <Text weight="semibold">{total}</Text>
        <Text size={200}>{total === 1 ? 'suggestion' : 'suggestions'}</Text>
        {criticalCount > 0 ? (
          <Badge appearance="filled" color="danger" size="small">
            {criticalCount} critical
          </Badge>
        ) : null}
      </span>

      <Tooltip
        relationship="description"
        content={
          `Applies suggestions that are not critical and at least ` +
          `${AUTO_APPLY_CONFIDENCE.toFixed(2)} confident. Reversible as one step.`
        }
      >
        <Button
          appearance="primary"
          onClick={onApplyBatch}
          disabled={busy || autoApplicableCount === 0}
        >
          {batchLabel}
        </Button>
      </Tooltip>

      <Button onClick={onUndo} disabled={busy || !canUndo} title="Ctrl+Z">
        Undo
      </Button>
      <Button onClick={onRedo} disabled={busy || !canRedo} title="Ctrl+Y">
        Redo
      </Button>
    </Toolbar>
  );
}

export const BatchActionBar = React.memo(BatchActionBarComponent);

BatchActionBar.displayName = 'BatchActionBar';
