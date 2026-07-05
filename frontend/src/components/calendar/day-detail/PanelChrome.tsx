import { cn } from "@/lib/utils";

/* ─── Panel chrome — shared bits of the day-detail panel ────────────────── */
/* Extracted from DayDetailPanel.tsx (B4-11 split): the section header
 * used above both the macro and earnings blocks, and the count chip
 * shown in the panel header. Presentation-only, no state.
 */

/* ─── Section title ─────────────────────────────────────────────────────── */

export function SectionTitle({
  count,
  label,
  hint,
}: {
  count: number;
  label: string;
  hint: string;
}) {
  return (
    <div className="flex items-baseline justify-between">
      <div className="flex items-baseline gap-2">
        <span className="text-[14px] font-semibold uppercase tracking-[0.16em] text-foreground/80">
          {label}
        </span>
        <span className="rounded-full border bg-muted/40 px-1.5 py-0 text-[13px] font-mono tabular-nums text-muted-foreground">
          {count}
        </span>
      </div>
      <span className="text-[13px] uppercase tracking-wider text-muted-foreground/70">
        {hint}
      </span>
    </div>
  );
}

/* ─── Count chip (header) ───────────────────────────────────────────────── */

export function CountChip({
  count,
  label,
  tone,
}: {
  count: number;
  label: string;
  tone: "sector" | "macro";
}) {
  const dim = count === 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[13px] font-semibold uppercase tracking-wider",
        dim
          ? "border-border/60 text-muted-foreground/60"
          : tone === "sector"
            ? "border-sky-300/70 dark:border-sky-700/60 bg-sky-50 dark:bg-sky-950/40 text-sky-800 dark:text-sky-200"
            : "border-amber-300/70 dark:border-amber-700/60 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200",
      )}
    >
      <span className="tabular-nums">{count}</span>
      <span>{label}</span>
    </span>
  );
}
