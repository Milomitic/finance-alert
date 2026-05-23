import type { Playbook } from "@/lib/tradePlaybook";
import { cn } from "@/lib/utils";

function price(n: number): string {
  return n >= 1 ? n.toFixed(2) : n.toFixed(3);
}

function Cell({
  label, value, hint, tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "rose" | "emerald";
}) {
  const vcls =
    tone === "rose"
      ? "text-rose-600 dark:text-rose-400"
      : tone === "emerald"
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-foreground";
  return (
    <div className="rounded-md border border-border/60 px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold truncate" title={label}>
        {label}
      </div>
      <div className={cn("font-bold tabular-nums", vcls)}>{value}</div>
      {hint && <div className="text-[10px] text-muted-foreground tabular-nums">{hint}</div>}
    </div>
  );
}

/* Renders a rule-based trade playbook (action, entry/stop/targets, duration,
   risk + leverage). Descriptive, with a not-financial-advice disclaimer. */
export function PlaybookView({ playbook }: { playbook: Playbook }) {
  const p = playbook;
  const isLong = p.side === "long";
  const accent = isLong ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
  const chipCls = isLong
    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
    : "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300";
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold", chipCls)}>
          {p.action}
        </span>
        <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
          {p.conviction}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Cell label="Entry" value={`$${price(p.entry)}`} />
        <Cell label="Stop" value={`$${price(p.stop)}`} hint={`-${p.stopPct.toFixed(1)}%`} tone="rose" />
        {p.targets.map((t) => (
          <Cell key={t.label} label={`${t.label} - R:R ${t.rr.toFixed(1)}`} value={`$${price(t.price)}`} tone="emerald" />
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        <div className="rounded-md border border-border/60 px-2.5 py-1.5">
          <span className="text-muted-foreground">Durata attesa: </span>
          <span className="font-medium">{p.duration}</span>
        </div>
        <div className="rounded-md border border-border/60 px-2.5 py-1.5">
          <span className="text-muted-foreground">Rischio: </span>
          <span className="font-medium">{p.riskBudgetPct.toFixed(1)}% del capitale</span>
          <span className="text-muted-foreground"> - </span>
          <span className={cn("font-medium", accent)}>{p.leverageNote}</span>
        </div>
      </div>
      <div className="text-[10px] text-muted-foreground/70 italic">
        Stime educative su base tecnica, non un consiglio finanziario o di investimento.
      </div>
    </div>
  );
}
