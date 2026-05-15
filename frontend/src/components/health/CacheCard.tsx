import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Database, Layers } from "lucide-react";
import type { PlatformHealth } from "@/api/platformHealth";

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

function CacheSection({
  title,
  l1,
  l2,
  oldestAgeS,
}: {
  title: string;
  l1: number;
  l2: number;
  oldestAgeS: number | null;
}) {
  const coverage = l2 > 0 ? Math.min(100, (l1 / l2) * 100) : 0;
  return (
    <div className="space-y-1.5 py-2.5 px-3 border-b last:border-b-0">
      <div className="flex items-center justify-between">
        <span className="text-[11.5px] font-medium">{title}</span>
        <span className="text-[10.5px] text-muted-foreground tabular-nums">
          {l1} L1 · {l2} L2
        </span>
      </div>
      {l2 > 0 && (
        <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
          <div
            className="h-full bg-sky-500 transition-all"
            style={{ width: `${coverage}%` }}
            title={`L1 covers ${coverage.toFixed(0)}% of L2`}
          />
        </div>
      )}
      <div className="flex items-center justify-between text-[10px] text-muted-foreground tabular-nums">
        <span>Oldest entry</span>
        <span className="font-mono">{fmtAge(oldestAgeS)}</span>
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
          <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
            <Layers className="h-4 w-4" />
            Cache &amp; Database
          </CardTitle>
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {totalL1}/{totalL2}
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-0 text-xs">
        <CacheSection
          title="Fundamentals"
          l1={cache.fundamentals.l1_entries}
          l2={cache.fundamentals.l2_entries}
          oldestAgeS={cache.fundamentals.oldest_age_s}
        />
        <CacheSection
          title="News"
          l1={cache.news.l1_entries}
          l2={cache.news.l2_entries}
          oldestAgeS={cache.news.oldest_age_s}
        />
        <div className="py-2.5 px-3 bg-muted/10">
          <div className="flex items-center justify-between">
            <span className="text-[11.5px] font-medium inline-flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5" />
              app.db
            </span>
            <span className="text-[11px] font-mono tabular-nums">
              {fmtSize(cache.db.size_mb)}
            </span>
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            SQLite WAL · backup automatici settimanali
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
