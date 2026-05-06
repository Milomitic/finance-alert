import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Loader2,
  RefreshCw,
  Settings as SettingsIcon,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  useCatalogStatus,
  useTriggerCatalogRefresh,
} from "@/hooks/useCatalogStatus";
import { useRulePerformance } from "@/hooks/useRulePerformance";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";

/* ─── SettingsPage — /settings route ────────────────────────────────────── *
 *
 * Admin / diagnostic surface. Two main panels:
 *   - Rule effectiveness (forward-return stats per rule.kind over
 *     1d / 5d / 20d windows).
 *   - Catalog refresh status (per-index last-run state + manual
 *     trigger).
 *
 * Was a placeholder ("Disponibile nelle prossime fasi") in the
 * sidebar for the entire 3A-3C lifetime; ships in Fase 3E.
 */
export default function SettingsPage() {
  return (
    <div className="space-y-5 max-w-6xl">
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-[10px] font-mono font-semibold uppercase tracking-[0.22em] text-muted-foreground">
          <SettingsIcon className="h-3 w-3" />
          <span>Amministrazione · diagnostica</span>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight leading-tight">
          Impostazioni
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Statistiche di efficacia delle regole alert e stato dei refresh
          catalogo per indice.
        </p>
      </header>

      <RulePerformancePanel />
      <CatalogRefreshPanel />
    </div>
  );
}

/* ─── Rule performance panel ────────────────────────────────────────────── */

function RulePerformancePanel() {
  const [days, setDays] = useState(90);
  const q = useRulePerformance(days);
  const items = q.data?.items ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={TrendingUp}
          label="Efficacia regole — forward return"
          right={
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Finestra:</span>
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="bg-background border rounded px-2 py-0.5 text-xs"
              >
                <option value={30}>30 giorni</option>
                <option value={90}>90 giorni</option>
                <option value={180}>180 giorni</option>
                <option value={365}>1 anno</option>
              </select>
            </div>
          }
          className="mb-3"
        />

        {q.isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground inline-flex items-center gap-2 justify-center w-full">
            <Loader2 className="h-4 w-4 animate-spin" />
            Calcolo statistiche…
          </div>
        ) : items.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            Nessun alert nel periodo — esegui uno scan per generare
            dati di efficacia.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="bg-muted/30 text-muted-foreground border-b">
                <tr className="text-base">
                  <th className="text-left px-3 py-2 font-semibold">Regola</th>
                  <th className="text-right px-3 py-2 font-semibold">N</th>
                  {[1, 5, 20].flatMap((w) => [
                    <th key={`m${w}`} className="text-right px-3 py-2 font-semibold">
                      Media {w}d
                    </th>,
                    <th key={`h${w}`} className="text-right px-3 py-2 font-semibold">
                      Hit {w}d
                    </th>,
                  ])}
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const meta = getAlertKindMeta(row.rule_kind);
                  const Icon = meta.icon;
                  return (
                    <tr
                      key={row.rule_kind}
                      className="border-b border-border/40 hover:bg-muted/30"
                    >
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center gap-2">
                          <Icon className="h-3.5 w-3.5 shrink-0" />
                          <span className="font-semibold">{meta.label}</span>
                          <span
                            className={cn(
                              "px-1.5 py-px rounded text-[10px] uppercase tracking-wider font-semibold",
                              row.tone === "bullish"
                                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
                                : row.tone === "bearish"
                                  ? "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200"
                                  : "bg-muted text-muted-foreground",
                            )}
                          >
                            {row.tone}
                          </span>
                        </span>
                      </td>
                      <td className="text-right px-3 py-2 font-bold">
                        {row.total_alerts}
                      </td>
                      {[1, 5, 20].flatMap((w) => {
                        const s = row.stats[String(w)];
                        return [
                          <td
                            key={`m${w}-${row.rule_kind}`}
                            className={cn(
                              "text-right px-3 py-2 font-semibold",
                              s?.mean_pct == null
                                ? "text-muted-foreground"
                                : s.mean_pct > 0
                                  ? "text-emerald-700 dark:text-emerald-400"
                                  : s.mean_pct < 0
                                    ? "text-rose-700 dark:text-rose-400"
                                    : "",
                            )}
                            title={
                              s?.median_pct != null
                                ? `Mediana ${s.median_pct.toFixed(2)}%`
                                : undefined
                            }
                          >
                            {s?.mean_pct == null
                              ? "—"
                              : `${s.mean_pct >= 0 ? "+" : ""}${s.mean_pct.toFixed(2)}%`}
                          </td>,
                          <td
                            key={`h${w}-${row.rule_kind}`}
                            className={cn(
                              "text-right px-3 py-2 font-semibold",
                              s?.hit_rate == null
                                ? "text-muted-foreground"
                                : s.hit_rate >= 0.55
                                  ? "text-emerald-700 dark:text-emerald-400"
                                  : s.hit_rate >= 0.45
                                    ? ""
                                    : "text-rose-700 dark:text-rose-400",
                            )}
                            title={
                              s?.count != null
                                ? `${s.count} osservazioni`
                                : undefined
                            }
                          >
                            {s?.hit_rate == null
                              ? "—"
                              : `${(s.hit_rate * 100).toFixed(0)}%`}
                          </td>,
                        ];
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground italic">
              "Hit" = % di alert con direzione coerente con il tono della
              regola entro la finestra (bullish → ritorno positivo,
              bearish → negativo). Le regole neutre non hanno hit-rate.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ─── Catalog refresh panel ─────────────────────────────────────────────── */

function CatalogRefreshPanel() {
  const status = useCatalogStatus();
  const trigger = useTriggerCatalogRefresh();
  const indices = status.data?.indices ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Database}
          label="Stato refresh catalogo"
          right={
            <Button
              size="sm"
              variant="outline"
              disabled={trigger.isPending}
              onClick={() => trigger.mutate(null)}
            >
              <RefreshCw
                className={cn(
                  "h-3.5 w-3.5 mr-1",
                  trigger.isPending && "animate-spin",
                )}
              />
              Refresh tutti
            </Button>
          }
          className="mb-3"
        />

        {status.isLoading ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Caricamento…
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="bg-muted/30 text-muted-foreground border-b">
                <tr className="text-base">
                  <th className="text-left px-3 py-2 font-semibold">Indice</th>
                  <th className="text-left px-3 py-2 font-semibold">Stato</th>
                  <th className="text-right px-3 py-2 font-semibold">
                    Ultimo refresh
                  </th>
                  <th className="text-right px-3 py-2 font-semibold">+/-/=</th>
                  <th className="text-right px-3 py-2 font-semibold"></th>
                </tr>
              </thead>
              <tbody>
                {indices.map((idx) => {
                  const meta = getIndexMeta(idx.index_code);
                  const completed = idx.last_completed_at
                    ? new Date(idx.last_completed_at).toLocaleString("it-IT", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—";
                  return (
                    <tr
                      key={idx.index_code}
                      className="border-b border-border/40 hover:bg-muted/30"
                    >
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center gap-2">
                          {meta.countryCode && (
                            <img
                              src={`/flags/${meta.countryCode}.svg`}
                              alt={meta.country}
                              width={20}
                              height={14}
                              style={{ width: "20px", height: "14px", objectFit: "cover" }}
                              className="rounded-[1px] ring-1 ring-border/60 shrink-0"
                              aria-hidden
                            />
                          )}
                          <span className="font-semibold">{meta.displayCode}</span>
                          <span className="text-xs text-muted-foreground">
                            {meta.fullName}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {idx.last_status === "success" && (
                          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            success
                          </span>
                        )}
                        {idx.last_status === "failed" && (
                          <span
                            className="inline-flex items-center gap-1 text-rose-700 dark:text-rose-400"
                            title={idx.error_message ?? ""}
                          >
                            <AlertTriangle className="h-3.5 w-3.5" />
                            failed
                          </span>
                        )}
                        {idx.last_status === "in_progress" && (
                          <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            in corso
                          </span>
                        )}
                        {idx.last_status == null && (
                          <span className="text-muted-foreground">mai</span>
                        )}
                      </td>
                      <td className="text-right px-3 py-2 text-muted-foreground">
                        {completed}
                      </td>
                      <td className="text-right px-3 py-2">
                        {idx.stocks_added != null ? (
                          <span>
                            <span className="text-emerald-700 dark:text-emerald-400">
                              +{idx.stocks_added}
                            </span>
                            {" / "}
                            <span className="text-blue-700 dark:text-blue-400">
                              ~{idx.stocks_updated ?? 0}
                            </span>
                            {" / "}
                            <span className="text-rose-700 dark:text-rose-400">
                              -{idx.stocks_removed ?? 0}
                            </span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="text-right px-3 py-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={trigger.isPending}
                          onClick={() => trigger.mutate(idx.index_code)}
                          title={`Refresh ${meta.displayCode}`}
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground italic">
              I refresh leggono Wikipedia per aggiornare i constituent
              di ciascun indice. "+/~/-": aggiunti / aggiornati /
              rimossi vs il run precedente.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
