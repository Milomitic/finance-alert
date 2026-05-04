import { ExternalLink, Newspaper } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { useStockNews } from "@/hooks/useStockNews";

interface Props {
  ticker: string;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "";
  try {
    const ts = new Date(iso).getTime();
    const diffH = (Date.now() - ts) / (1000 * 60 * 60);
    if (diffH < 1) return `${Math.round(diffH * 60)}m fa`;
    if (diffH < 24) return `${Math.round(diffH)}h fa`;
    return `${Math.round(diffH / 24)}g fa`;
  } catch { return ""; }
}

export function NewsCard({ ticker }: Props) {
  const q = useStockNews(ticker, 5);
  const items = q.data?.items ?? [];

  // Card sizes to content (no `h-full`) per the row-level `items-start`.
  // News list is short (5 items) so an internal scroll is unnecessary.
  return (
    <Card>
      <CardContent className="p-4 flex flex-col">
        <div className="flex items-center gap-2 mb-2 shrink-0">
          <Newspaper className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            News
          </span>
          <span className="ml-auto text-sm text-muted-foreground italic">
            Powered by yfinance
          </span>
        </div>
        <div>
          {q.isLoading ? (
            <div className="space-y-2">
              {[0,1,2].map((i) => <div key={i} className="h-4 bg-muted/40 animate-pulse rounded" />)}
            </div>
          ) : items.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-4">
              News non disponibili per questo ticker.
            </div>
          ) : (
            <ul className="space-y-2">
              {items.map((n) => (
                <li key={n.link} className="text-sm">
                  <a
                    href={n.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline flex items-start gap-1"
                  >
                    <span className="line-clamp-2">{n.title}</span>
                    <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground mt-0.5" />
                  </a>
                  <div className="text-sm text-muted-foreground mt-0.5">
                    {n.publisher}
                    {n.published_at && <> · {formatRelative(n.published_at)}</>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
