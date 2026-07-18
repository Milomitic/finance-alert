import type { Position } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Portfolio-level rollup over tracked positions (F1). Everything is derived
 * client-side from the same list the tables already render — no new endpoint.
 *
 * Honesty caveat: Position carries no currency, and `_abs` figures come back in
 * each name's native currency. Summing them mixes currencies without FX
 * conversion, so the absolute totals are "native units" and labelled as such.
 * The % figures are cost-weighted (Σ pnl / Σ cost), which is dimensionless and
 * the least-wrong blended-return view. Notional-only positions (no size, so no
 * `_abs`) are excluded from the money totals and counted in the caveat.
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
    ? "text-emerald-600 dark:text-emerald-400"
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

export function PortfolioSummary({
  open,
  closed,
}: {
  open: Position[];
  closed: Position[];
}) {
  if (open.length === 0 && closed.length === 0) return null;

  const openSized = open.filter((p) => p.size != null && p.unrealized_abs != null);
  const openPnl = sum(openSized.map((p) => p.unrealized_abs));
  const openCost = sum(openSized.map((p) => p.entry_price * (p.size as number)));
  const openPct = openCost > 0 ? (openPnl / openCost) * 100 : null;
  const exposure = sum(
    openSized.map((p) => (p.last_price ?? p.entry_price) * (p.size as number)),
  );

  const closedSized = closed.filter((p) => p.realized_abs != null);
  const realizedPnl = sum(closedSized.map((p) => p.realized_abs));
  const wins = closed.filter((p) => (p.realized_pct ?? 0) > 0).length;
  const winRate = closed.length > 0 ? (wins / closed.length) * 100 : null;

  const totalPnl = openPnl + realizedPnl;
  const notionalOnly =
    open.filter((p) => p.size == null).length +
    closed.filter((p) => p.size == null).length;

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatTile
            label="P&L totale"
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
            sub={winRate != null ? `win rate ${Math.round(winRate)}%` : "—"}
          />
          <StatTile
            label="Esposizione aperta"
            value={nfMoneyPlain.format(exposure)}
            sub="valore di mercato"
          />
        </div>
        <p className="text-[11px] text-muted-foreground">
          Somme in valuta nativa, senza conversione FX.
          {notionalOnly > 0 &&
            ` ${notionalOnly} posizion${notionalOnly === 1 ? "e" : "i"} notional (senza size) escluse dai totali.`}
        </p>
      </CardContent>
    </Card>
  );
}
