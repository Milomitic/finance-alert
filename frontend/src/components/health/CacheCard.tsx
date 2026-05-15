import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { PlatformHealth } from "@/api/platformHealth";

type Props = { cache: PlatformHealth["cache"] };

function fmtAge(s: number | null): string {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}g`;
}

export default function CacheCard({ cache }: Props) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Cache &amp; DB</CardTitle>
      </CardHeader>
      <CardContent className="text-xs space-y-2">
        <div>
          <div className="font-semibold">Fundamentals</div>
          <div className="flex justify-between text-muted-foreground">
            <span>L1 / L2</span>
            <span className="font-mono">
              {cache.fundamentals.l1_entries} / {cache.fundamentals.l2_entries}
            </span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span>Oldest</span>
            <span className="font-mono">
              {fmtAge(cache.fundamentals.oldest_age_s)}
            </span>
          </div>
        </div>
        <div className="border-t pt-2">
          <div className="font-semibold">News</div>
          <div className="flex justify-between text-muted-foreground">
            <span>L1 / L2</span>
            <span className="font-mono">
              {cache.news.l1_entries} / {cache.news.l2_entries}
            </span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span>Oldest</span>
            <span className="font-mono">{fmtAge(cache.news.oldest_age_s)}</span>
          </div>
        </div>
        <div className="border-t pt-2">
          <div className="font-semibold">Database</div>
          <div className="flex justify-between text-muted-foreground">
            <span>app.db</span>
            <span className="font-mono">{cache.db.size_mb} MB</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
