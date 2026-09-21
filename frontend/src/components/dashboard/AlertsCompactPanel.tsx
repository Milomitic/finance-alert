import { Bell } from "lucide-react";

import type { Alert, TopStock } from "@/api/types";
import { ConfluenceRows } from "@/components/dashboard/ConfluenceCard";
import { RecentAlertsFeed } from "@/components/dashboard/RecentAlertsFeed";
import { TopStocksTable } from "@/components/dashboard/TopStocksTable";
import { Card, CardContent } from "@/components/ui/card";
import { HintLabel } from "@/components/ui/info-hint";
import { SectionTitle } from "@/components/ui/section-title";
import { PROBABILITA_TOOLTIP } from "@/lib/alertMeta";

interface Props {
  topStocks: TopStock[];
  recentAlerts: Alert[];
  alertsLast24h: number;
  alertsPrev24h: number;
}

const COLUMNS: { key: string; label: string; nota?: string }[] = [
  { key: "confluence", label: "Top confluenze" },
  { key: "top", label: "Top stocks" },
  /* ⚠️ La `nota` raccoglie le spiegazioni che stavano nell'intestazione della
     tabella Feed, tolta su richiesta dell'utente. Non sono state cancellate ma
     SPOSTATE: quella sulla Probabilita' dice che e' un tasso di base per
     rilevatore, identico per ogni segnale dello stesso tipo, ed e' la parte
     onesta di quel numero. */
  {
    key: "feed",
    label: "Feed",
    nota:
      "Colonne: titolo, natura del segnale, regola che è scattata, Forza del pattern (0-100), " +
      `Probabilità, prezzo e data. ${PROBABILITA_TOOLTIP}`,
  },
];

/* ⚠️ Il bordo di ciascuna colonna, per larghezza. Non `divide-x`: sotto
   `row-full` il Feed va a capo su una riga sua, e `divide-x` gli metterebbe
   un bordo SINISTRO contro la cornice e nessun bordo sopra. Letterali, perche'
   il purger di Tailwind legge solo stringhe intere. */
const COLONNA: Record<string, string> = {
  confluence: "",
  top: "border-t border-border/40 sm:border-t-0 sm:border-l",
  feed: "border-t border-border/40 sm:col-span-2 row-full:col-span-1 row-full:border-t-0 row-full:border-l",
};

/**
 * Was: a 3-tab card (Top stocks / Feed / Per indice), then 3 side-by-side
 * columns. 2026-05: absorbed the former standalone "Top confluenze" card as
 * a FOURTH column on the left. 2026-09-21: «Per indice» removed (user
 * request) to give the other three room — the per-index view lives in the
 * breadth table further down the page. Each column is a flex-col with a
 * fixed header and a scrollable body so the card height stays predictable.
 */
export function AlertsCompactPanel({
  topStocks,
  recentAlerts,
  alertsLast24h,
}: Props) {
  return (
    <Card className="lg:h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        {/* Header — title + 24h badge + "Vedi tutti" link. */}
        <div className="shrink-0 flex items-center gap-3 border-b px-3 bg-muted/30 py-2">
          <SectionTitle
            icon={Bell}
            label="Segnali"
            right={
              <span
                className="text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200 px-2 py-0.5 rounded-full font-semibold whitespace-nowrap"
                title="Nuovi segnali rilevati nelle ultime 24 ore"
              >
                {alertsLast24h} nuovi segnali · 24h
              </span>
            }
          />
          <a
            href="/alerts"
            className="ml-auto text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
          >
            Vedi tutti →
          </a>
        </div>

        {/* Three-column grid — one per former tab. Each column is a
            flex-col with a fixed header and a scrollable body so the
            card height stays predictable (matches Top Picks beside it)
            even when Feed has many items. */}
        {/* Column count steps up with width: 1 (phone) → 2 (sm tablet) →
            4 (lg desktop). Going straight from 1→4 at md crammed four
            fixed-px-celled tables into ~180px each on tablets; the 2-up
            intermediate keeps each readable until there's room for all
            four. The fixed-height + divide-x behavior aligns to lg (where
            the 4-col row lives) so the card grows naturally below that. */}
        {/* Three across only at row-full (1750px). At lg a 4-way split gave
            each column 231px and the confluence identity resolved to 0px;
            the Feed row (identity + natura + regola + Forza) needs ~500px,
            which a three-way split reaches at row-full — the same width two
            columns get at 1280. Below it Top confluenze and Top stocks share
            a row and the Feed takes the full width underneath. */}
        <div className="flex-1 min-h-0 grid grid-cols-1 sm:grid-cols-2 row-full:grid-cols-3">
          {COLUMNS.map((col) => (
            <div key={col.key} className={`flex flex-col min-h-0 min-w-0 ${COLONNA[col.key] ?? ""}`}>
              <div className="flex shrink-0 items-center gap-1 border-b bg-muted/40 px-3 py-1.5 text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
                {col.nota ? <HintLabel text={col.nota}>{col.label}</HintLabel> : col.label}
              </div>
              {/* Mobile/tablet: natural flow capped at 55vh so a long Feed
                  doesn't run away — the page scrolls. lg+: fixed-height
                  pane with its own scroll (keeps the 4 columns aligned
                  to the card height). */}
              <div className="max-h-[55vh] overflow-y-auto lg:max-h-none lg:flex-1 lg:min-h-0">
                {col.key === "confluence" && <ConfluenceRows />}
                {col.key === "top" && <TopStocksTable data={topStocks} />}
                {col.key === "feed" && <RecentAlertsFeed alerts={recentAlerts} />}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
