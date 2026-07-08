import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { CandlestickChart, Database, Layers } from "lucide-react";
import type { PlatformHealth, CacheKindStat } from "@/api/platformHealth";

type Props = { cache: PlatformHealth["cache"] };

function fmtAge(s: number | null): string {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}g`;
}

function fmtSize(mb: number): string {
  if (mb < 1) return `${(mb * 1024).toFixed(0)} KB`;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

/** One freshness row for a cache tier. "ultimo aggiornamento" (newest) is the
 * headline freshness figure — when the most recent fetch landed; "più vecchio"
 * (oldest) is the staleness tail. */
function TierRow({
  tier,
  subtitle,
  newestAgeS,
  oldestAgeS,
}: {
  tier: "L1" | "L2";
  subtitle: string;
  newestAgeS: number | null;
  oldestAgeS: number | null;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 tabular-nums">
      <span className="text-[11px] text-muted-foreground inline-flex items-baseline gap-1.5">
        <span className="font-semibold text-foreground/80">{tier}</span>
        <span className="text-[10px]">{subtitle}</span>
      </span>
      <span className="text-[11px] text-muted-foreground inline-flex items-baseline gap-1.5">
        <span>
          agg.{" "}
          <span className="font-mono text-foreground/90">{fmtAge(newestAgeS)}</span> fa
        </span>
        <span className="text-[10px] opacity-70">
          · meno fresco <span className="font-mono">{fmtAge(oldestAgeS)}</span>
        </span>
      </span>
    </div>
  );
}

function CacheSection({ title, k }: { title: string; k: CacheKindStat }) {
  const coverage = k.l2_entries > 0 ? Math.min(100, (k.l1_entries / k.l2_entries) * 100) : 0;
  return (
    <div className="space-y-2 py-3 px-4 border-b last:border-b-0">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{title}</span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {k.l1_entries} L1 · {k.l2_entries} L2
        </span>
      </div>
      {k.l2_entries > 0 && (
        <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
          <div
            className="h-full bg-sky-500 transition-all"
            style={{ width: `${coverage}%` }}
            title={`L1 copre ${coverage.toFixed(0)}% di L2`}
          />
        </div>
      )}
      <div className="space-y-1 pt-0.5">
        <TierRow
          tier="L1"
          subtitle="in memoria"
          newestAgeS={k.newest_age_s}
          oldestAgeS={k.oldest_age_s}
        />
        <TierRow
          tier="L2"
          subtitle="persistente"
          newestAgeS={k.l2_newest_age_s}
          oldestAgeS={k.l2_oldest_age_s}
        />
      </div>
    </div>
  );
}

export default function CacheCard({ cache }: Props) {
  const totalL1 = cache.fundamentals.l1_entries + cache.news.l1_entries;
  const totalL2 = cache.fundamentals.l2_entries + cache.news.l2_entries;
  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="pb-3 border-b bg-muted/20">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base font-semibold flex items-center gap-1.5">
            <Layers className="h-4 w-4" />
            Cache &amp; Database
          </CardTitle>
          <span className="text-[11px] text-muted-foreground tabular-nums">
            {totalL1}/{totalL2}
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-0 text-sm">
        <CacheSection title="Fundamentals" k={cache.fundamentals} />
        <CacheSection title="News" k={cache.news} />
        {/* Riga "Dati" (SAL-2): freschezza dell'OHLCV memorizzato — la data
            dell'ultima barra è ciò che gli scan leggono davvero, quindi è il
            segnale "i dati sono aggiornati?" più diretto della pagina. */}
        {cache.ohlcv && (
          <div className="py-3 px-4 border-b">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium inline-flex items-center gap-1.5">
                <CandlestickChart className="h-4 w-4" />
                Dati
              </span>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                {cache.ohlcv.max_date != null ? (
                  <>
                    OHLCV aggiornati al{" "}
                    <span className="font-mono text-foreground/90">{cache.ohlcv.max_date}</span>
                    {" · "}
                    <span className="font-mono text-foreground/90">{cache.ohlcv.stocks_at_max}</span>
                    {" titoli"}
                  </>
                ) : (
                  <span className="italic">nessun dato OHLCV</span>
                )}
              </span>
            </div>
          </div>
        )}
        <div className="py-3 px-4 bg-muted/10">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium inline-flex items-center gap-1.5">
              <Database className="h-4 w-4" />
              app.db
            </span>
            <span className="text-[12.5px] font-mono tabular-nums">
              {fmtSize(cache.db.size_mb)}
            </span>
          </div>
          <div className="text-[11px] text-muted-foreground mt-1">
            SQLite WAL · backup automatici settimanali
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
