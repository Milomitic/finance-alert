import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { RecentScan } from "@/api/platformHealth";

type Props = { scans: RecentScan[] };

const STATUS_TONE: Record<string, string> = {
  success: "text-emerald-700",
  ok: "text-emerald-700",
  running: "text-blue-700",
  failed: "text-red-700",
  error: "text-red-700",
};

function fmtDuration(s: number | null): string {
  if (s == null) return "—";
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export default function ScansCard({ scans }: Props) {
  const last = scans[0];
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">
          Scan recenti{" "}
          <span className="text-xs text-muted-foreground">
            ({scans.length})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs space-y-2">
        {!last && (
          <div className="text-muted-foreground italic">
            Nessuno scan ancora
          </div>
        )}
        {last && (
          <div className="border-b pb-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold">Ultimo:</span>
              <span className={STATUS_TONE[last.status] ?? "text-muted-foreground"}>
                {last.status}
              </span>
            </div>
            <div className="text-muted-foreground">
              {fmtDuration(last.duration_s)} ·{" "}
              {last.alerts_count != null
                ? `${last.alerts_count} alert`
                : `${last.progress_done ?? 0}/${last.progress_total ?? 0}`}
            </div>
            {last.error_message && (
              <div className="text-red-700 truncate" title={last.error_message}>
                {last.error_message}
              </div>
            )}
          </div>
        )}
        <div className="space-y-1">
          {scans.slice(1).map((s) => (
            <div
              key={s.id}
              className="flex justify-between text-muted-foreground"
            >
              <span>#{s.id}</span>
              <span className={STATUS_TONE[s.status] ?? ""}>
                {s.status} · {fmtDuration(s.duration_s)}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
