import type { Position } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Portfolio-level rollup over tracked positions (F1). Everything is derived
 * client-side from the same list the tables already render — no new endpoint.
 *
 * The backend converts each position's abs P&L + cost basis to USD (native
 * currency × the live FX rate), so the money totals here sum ACROSS currencies
 * in USD — no longer "native units, no FX". The % figures are cost-weighted
 * (Σ pnl / Σ cost) in USD, dimensionless. Notional-only positions (no size, so
 * no `_usd`) are excluded from the money totals and counted in the note.
 */
const nfMoney = new Intl.NumberFormat("it-IT", {
  maximumFractionDigits: 0,
  signDisplay: "exceptZero",
});
const nfMoneyPlain = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 });
const nfPct = new Intl.NumberFormat("it-IT", {
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});

function pnlClass(v: number | null): string {
  if (v == null || v === 0) return "text-muted-foreground";
  return v > 0
    ? "text-emerald-800 dark:text-emerald-400"
    : "text-rose-600 dark:text-rose-400";
}

function sum(xs: (number | null | undefined)[]): number {
  return xs.reduce((a: number, x) => a + (x ?? 0), 0);
}

interface Tile {
  label: string;
  value: string;
  valueClass?: string;
  sub?: string;
}

function StatTile({ label, value, valueClass, sub }: Tile) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("text-2xl font-bold tabular-nums", valueClass)}>{value}</p>
      {sub && <p className="text-xs text-muted-foreground tabular-nums">{sub}</p>}
    </div>
  );
}

/** Percentuale minima di posizioni chiuse prima che un tasso sia un tasso.
 *  Stessa soglia gia' in uso in SetupsPage e DataHealthCard: sotto, il limite
 *  inferiore di Wilson al 95% e' cosi' basso che la percentuale non distingue
 *  una strategia buona da una mediocre. */
const MIN_WIN_RATE_N = 20;

/** Cosa scrivere sotto le posizioni chiuse.
 *
 *  Tre stati, non due. Nulla di chiuso non e' "0%": e' una domanda a cui
 *  ancora non e' stata data risposta. Sotto le 20 chiusure si mostra la
 *  FRAZIONE, che dice esattamente altrettanto senza pretendere di piu' — a
 *  1 su 1 il limite inferiore di Wilson sta intorno al 21%, quindi "100%" e'
 *  compatibile con una strategia che perde quattro volte su cinque. E questa
 *  e' la pagina dei soldi veri, il posto peggiore per un numero che afferma
 *  piu' di quanto sappia. Vincolato da PortfolioSummary.test.tsx. */
export function winRateLabel(wins: number, closed: number): string {
  if (closed <= 0) return "—";
  if (closed < MIN_WIN_RATE_N) return `${wins}/${closed} chiuse in utile`;
  return `win rate ${Math.round((wins / closed) * 100)}%`;
}

export function PortfolioSummary({
  open,
  closed,
}: {
  open: Position[];
  closed: Position[];
}) {
  if (open.length === 0 && closed.length === 0) return null;

  // All money in USD (backend-converted). Open exposure = cost + unrealized P&L.
  const openSized = open.filter((p) => p.size != null && p.unrealized_usd != null);
  const openPnl = sum(openSized.map((p) => p.unrealized_usd));
  const openCost = sum(openSized.map((p) => p.cost_usd));
  const openPct = openCost > 0 ? (openPnl / openCost) * 100 : null;
  const exposure = openCost + openPnl;

  const closedSized = closed.filter((p) => p.realized_usd != null);
  const realizedPnl = sum(closedSized.map((p) => p.realized_usd));
  const wins = closed.filter((p) => (p.realized_pct ?? 0) > 0).length;

  const totalPnl = openPnl + realizedPnl;
  const notionalOnly =
    open.filter((p) => p.size == null).length +
    closed.filter((p) => p.size == null).length;

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatTile
            label="P&L totale · USD"
            value={nfMoney.format(totalPnl)}
            valueClass={pnlClass(totalPnl)}
            sub="non realizzato + realizzato"
          />
          <StatTile
            label={`Aperte · ${open.length}`}
            value={nfMoney.format(openPnl)}
            valueClass={pnlClass(openPnl)}
            sub={openPct != null ? `${nfPct.format(openPct)} sul costo` : "—"}
          />
          <StatTile
            label={`Chiuse · ${closed.length}`}
            value={nfMoney.format(realizedPnl)}
            valueClass={pnlClass(realizedPnl)}
            sub={winRateLabel(wins, closed.length)}
          />
          <StatTile
            label="Esposizione aperta · USD"
            value={nfMoneyPlain.format(exposure)}
            sub="valore di mercato"
          />
        </div>
        <p className="text-[0.7059rem] text-muted-foreground">
          Somme convertite in USD ai cambi correnti.
          {notionalOnly > 0 &&
            ` ${notionalOnly} posizion${notionalOnly === 1 ? "e" : "i"} notional (senza size) escluse dai totali.`}
        </p>
      </CardContent>
    </Card>
  );
}
