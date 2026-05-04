import {
  Activity,
  ArrowDownToLine,
  ArrowUpToLine,
  Bell,
  History,
  TrendingDown,
  TrendingUp,
  Waves,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  alerts: Alert[];
}

/* ─── Rule-kind metadata: label, icon, tone ─────────────────────────────── */
/* Each kind maps to a small visual identity so the user can scan a long
 * history and spot patterns at a glance — repeated RSI oversold = volatility,
 * frequent breakouts = strong momentum, etc. */

type Tone = "bullish" | "bearish" | "neutral" | "warning";

interface KindMeta {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  tone: Tone;
}

const KIND_META: Record<string, KindMeta> = {
  rsi_oversold: { label: "RSI Oversold", icon: ArrowDownToLine, tone: "bullish" },
  rsi_overbought: { label: "RSI Overbought", icon: ArrowUpToLine, tone: "bearish" },
  golden_cross: { label: "Golden Cross", icon: TrendingUp, tone: "bullish" },
  death_cross: { label: "Death Cross", icon: TrendingDown, tone: "bearish" },
  volume_spike: { label: "Volume Spike", icon: Activity, tone: "warning" },
  breakout: { label: "Breakout", icon: Zap, tone: "bullish" },
  macd_bullish_cross: { label: "MACD Bullish", icon: TrendingUp, tone: "bullish" },
  macd_bearish_cross: { label: "MACD Bearish", icon: TrendingDown, tone: "bearish" },
  bollinger_squeeze: { label: "BB Squeeze", icon: Waves, tone: "neutral" },
  bollinger_breakout: { label: "BB Breakout", icon: Zap, tone: "warning" },
};

const TONE_BG: Record<Tone, string> = {
  bullish: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300",
  bearish: "bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300",
  warning: "bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300",
  neutral: "bg-slate-100 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300",
};

const TONE_BORDER: Record<Tone, string> = {
  bullish: "border-l-emerald-400 dark:border-l-emerald-500",
  bearish: "border-l-rose-400 dark:border-l-rose-500",
  warning: "border-l-amber-400 dark:border-l-amber-500",
  neutral: "border-l-slate-300 dark:border-l-slate-600",
};

function getKindMeta(rule_kind: string | null): KindMeta {
  if (!rule_kind) {
    return { label: "Price alert", icon: Bell, tone: "neutral" };
  }
  return (
    KIND_META[rule_kind] ?? {
      label: rule_kind,
      icon: Bell,
      tone: "neutral",
    }
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime();
  const diffMin = (Date.now() - ts) / (1000 * 60);
  if (diffMin < 60) return `${Math.max(1, Math.round(diffMin))}m fa`;
  const diffH = diffMin / 60;
  if (diffH < 24) return `${Math.round(diffH)}h fa`;
  const diffD = diffH / 24;
  if (diffD < 30) return `${Math.round(diffD)}g fa`;
  const diffMo = diffD / 30;
  if (diffMo < 12) return `${Math.round(diffMo)}mes fa`;
  return `${Math.round(diffMo / 12)}a fa`;
}

/* ─── Aggregate stats (header strip) ────────────────────────────────────── */

interface AlertStats {
  total: number;
  unread: number;
  bullish: number;
  bearish: number;
  last30d: number;
}

function computeStats(alerts: Alert[]): AlertStats {
  const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
  let unread = 0;
  let bullish = 0;
  let bearish = 0;
  let last30d = 0;
  for (const a of alerts) {
    if (a.read_at == null) unread++;
    if (new Date(a.triggered_at).getTime() >= cutoff) last30d++;
    const tone = getKindMeta(a.rule_kind).tone;
    if (tone === "bullish") bullish++;
    else if (tone === "bearish") bearish++;
  }
  return { total: alerts.length, unread, bullish, bearish, last30d };
}

/* ─── Single-row visual ─────────────────────────────────────────────────── */

function AlertRow({ alert, onClick }: { alert: Alert; onClick: () => void }) {
  const meta = getKindMeta(alert.rule_kind);
  const Icon = meta.icon;
  const isUnread = alert.read_at == null;

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "w-full text-left rounded-md border-l-2 px-3 py-2 transition-colors",
          "hover:bg-accent/40 cursor-pointer",
          TONE_BORDER[meta.tone],
          isUnread && "bg-primary/5",
        )}
      >
        <div className="flex items-center gap-3 flex-wrap">
          {/* Kind chip with icon */}
          <span
            className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold shrink-0",
              TONE_BG[meta.tone],
            )}
          >
            <Icon className="h-3 w-3" />
            {meta.label}
          </span>

          {/* Trigger price */}
          <span className="text-sm tabular-nums font-semibold">
            ${alert.trigger_price.toFixed(2)}
          </span>

          {/* Unread dot */}
          {isUnread && (
            <span
              className="inline-block h-2 w-2 rounded-full bg-primary shrink-0"
              title="Non letto"
            />
          )}

          {/* Date — right-aligned, shows both relative and absolute */}
          <span className="ml-auto text-xs text-muted-foreground tabular-nums shrink-0 flex flex-col items-end">
            <span className="font-medium">{formatRelative(alert.triggered_at)}</span>
            <span className="opacity-70">{formatDate(alert.triggered_at)}</span>
          </span>
        </div>
      </button>
    </li>
  );
}

/* ─── Card root ─────────────────────────────────────────────────────────── */

export function StockAlertsHistoryCard({ alerts }: Props) {
  const [open, setOpen] = useState<Alert | null>(null);

  // Sort by triggered_at desc — backend should already order, but defensive.
  const sorted = useMemo(
    () =>
      [...alerts].sort(
        (a, b) =>
          new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime(),
      ),
    [alerts],
  );
  const stats = useMemo(() => computeStats(sorted), [sorted]);

  return (
    <>
      <Card>
        <CardContent className="p-4">
          {/* Header strip: title + aggregate stats (bull/bear/last30d/unread) */}
          <div className="flex items-center gap-3 flex-wrap mb-3">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Alert storici per questo ticker
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                ({stats.total})
              </span>
            </div>

            {stats.total > 0 && (
              <div className="ml-auto flex items-center gap-2 flex-wrap text-xs">
                {stats.last30d > 0 && (
                  <span
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/70"
                    title="Alert generati negli ultimi 30 giorni"
                  >
                    <span className="text-muted-foreground">30d:</span>
                    <span className="font-bold tabular-nums">{stats.last30d}</span>
                  </span>
                )}
                {stats.bullish > 0 && (
                  <span
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200"
                    title="Alert con tono bullish (RSI oversold, golden cross, breakout, ecc.)"
                  >
                    <TrendingUp className="h-3 w-3" />
                    <span className="font-bold tabular-nums">{stats.bullish}</span>
                  </span>
                )}
                {stats.bearish > 0 && (
                  <span
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-100 dark:bg-rose-900/40 text-rose-800 dark:text-rose-200"
                    title="Alert con tono bearish (RSI overbought, death cross, ecc.)"
                  >
                    <TrendingDown className="h-3 w-3" />
                    <span className="font-bold tabular-nums">{stats.bearish}</span>
                  </span>
                )}
                {stats.unread > 0 && (
                  <span
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-primary/10 text-primary"
                    title="Alert non ancora marcati come letti"
                  >
                    <Bell className="h-3 w-3" />
                    <span className="font-bold tabular-nums">{stats.unread}</span>
                  </span>
                )}
              </div>
            )}
          </div>

          {sorted.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-8">
              Nessun alert mai generato per questo ticker.
              <div className="text-xs mt-1 opacity-75">
                Quando una regola si attiva sui dati di questo titolo, l'alert
                comparirà qui in cima.
              </div>
            </div>
          ) : (
            // Cap at ~14 rows visible (≈ 60px each); scroll for the rest.
            // Full list is preserved (no slice/+N truncation) since this
            // is the canonical history view for the ticker.
            <ul className="space-y-1 max-h-[420px] overflow-y-auto pr-1 -mr-1">
              {sorted.map((a) => (
                <AlertRow key={a.id} alert={a} onClick={() => setOpen(a)} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={open} onClose={() => setOpen(null)} />
    </>
  );
}
