import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/* Phone rendering for the app's financial tables.
 *
 * Every one of them is the same shape underneath: one IDENTITY per row
 * (logo + ticker + name) plus N numeric METRICS. That shape survives a
 * 9-column table on a desktop and collapses on a phone, where the user ends
 * up scrolling sideways to read a single row — the metrics scroll out of
 * view exactly when they want to compare them against the name.
 *
 * So below `sm` the same rows render as cards: identity on top, metrics as
 * labelled pairs underneath. Nothing is scrolled sideways and nothing is
 * truncated.
 *
 * DELIBERATELY NOT a full table abstraction. Callers keep their existing
 * `<table>` for `sm` and up untouched — this only supplies the phone view —
 * so adopting it cannot regress the desktop layout that already works. The
 * column definitions are shared between the two, so the two views can't
 * drift apart.
 */

export interface MetricColumn<T> {
  key: string;
  /** Short label — doubles as the table header and the card's field label. */
  label: string;
  cell: (row: T) => ReactNode;
  /** Drop from the phone card. For detail nobody consults on a phone; keeping
   *  every column would just rebuild the wall of numbers in a taller shape. */
  desktopOnly?: boolean;
}

export function MetricCardList<T>({
  rows,
  columns,
  rowKey,
  identity,
  /** Optional single value pinned next to the identity (typically the score
   *  the list is sorted by) — it is what the eye looks for first. */
  headline,
  className,
}: {
  rows: T[];
  columns: MetricColumn<T>[];
  rowKey: (row: T) => string;
  identity: (row: T) => ReactNode;
  headline?: (row: T) => ReactNode;
  className?: string;
}) {
  const shown = columns.filter((c) => !c.desktopOnly);
  return (
    <div className={cn("space-y-2", className)}>
      {rows.map((row) => (
        <div
          key={rowKey(row)}
          className="rounded-lg border bg-card p-3 active:bg-muted/40 transition-colors"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">{identity(row)}</div>
            {headline && (
              <div className="shrink-0 text-right tabular-nums">{headline(row)}</div>
            )}
          </div>
          <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5 border-t pt-2.5">
            {shown.map((col) => (
              <div key={col.key} className="flex items-baseline justify-between gap-2">
                <dt className="text-[11px] uppercase tracking-wider text-muted-foreground truncate">
                  {col.label}
                </dt>
                <dd className="text-sm tabular-nums shrink-0">{col.cell(row)}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
