import { ChevronDown, Download } from "lucide-react";
import { useState } from "react";

import { stocks, type SearchParams } from "@/api/stocks";
import type { StockSearchItem } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";

/** Massimo di righe per l'export "tutti i filtrati". La richiesta parte
 *  con limit=999/offset=0; il service clampa a 500 righe per pagina,
 *  quindi con più di 500 risultati si continua a paginare (has_more)
 *  fino al tetto — l'universo è ~1000, i filtri tipici molto meno. */
const EXPORT_ALL_LIMIT = 999;

/** Le colonne esportabili nell'ordine della tabella. `id` allineato a
 *  SCREENER_COLS (visibilità condivisa); header CSV in ASCII stabile. */
type CsvValue = string | number | null | undefined;
const CSV_FIELDS: { id: string; header: string; value: (it: StockSearchItem) => CsvValue }[] = [
  { id: "exchange",       header: "exchange",        value: (it) => it.stock.exchange },
  { id: "settore",        header: "sector",          value: (it) => it.stock.sector },
  { id: "industry",       header: "industry",        value: (it) => it.stock.industry },
  { id: "prezzo",         header: "last_close",      value: (it) => it.metrics?.last_close },
  { id: "market_cap",     header: "market_cap",      value: (it) => it.stock.market_cap },
  { id: "delta_pct",      header: "change_pct",      value: (it) => it.metrics?.change_pct },
  { id: "rsi",            header: "rsi14",           value: (it) => it.metrics?.rsi14 },
  { id: "vol_ratio",      header: "vol_ratio",       value: (it) => it.metrics?.vol_ratio },
  { id: "volume",         header: "vol_today",       value: (it) => it.metrics?.vol_today },
  {
    id: "pct_from_high", header: "pct_from_52w_high",
    value: (it) => {
      const m = it.metrics;
      if (!m || m.last_close == null || m.high_252 == null || m.high_252 <= 0) return null;
      return (m.last_close / m.high_252 - 1) * 100;
    },
  },
  {
    id: "vs_ema200", header: "vs_ema200_pct",
    value: (it) => {
      const m = it.metrics;
      if (!m || m.last_close == null || m.ema200 == null || m.ema200 <= 0) return null;
      return (m.last_close / m.ema200 - 1) * 100;
    },
  },
  { id: "score",          header: "score_composite", value: (it) => it.score.composite },
  { id: "score",          header: "score_delta_7d",  value: (it) => it.score.composite_delta_7d },
  { id: "profitability",  header: "profitability",   value: (it) => it.score.profitability },
  { id: "sustainability", header: "sustainability",  value: (it) => it.score.sustainability },
  { id: "growth",         header: "growth",          value: (it) => it.score.growth },
  { id: "value",          header: "value",           value: (it) => it.score.value },
  { id: "sentiment",      header: "sentiment",       value: (it) => it.score.sentiment },
  { id: "tech_composite", header: "tech_composite",  value: (it) => it.technical.composite },
  { id: "tech_trend",     header: "tech_trend",      value: (it) => it.technical.trend },
  { id: "tech_momentum",  header: "tech_momentum",   value: (it) => it.technical.momentum },
  { id: "tech_structure", header: "tech_structure",  value: (it) => it.technical.structure },
  { id: "tech_volume",    header: "tech_volume",     value: (it) => it.technical.volume },
  { id: "tech_rel_strength", header: "tech_rel_strength", value: (it) => it.technical.rel_strength },
  { id: "risk",           header: "risk_tier",       value: (it) => it.score.risk_tier },
];

/** RFC-4180-ish quoting: quote when the value contains delimiter/quote/
 *  newline; double the inner quotes. Numbers stay RAW (punto decimale,
 *  nessuna formattazione it-IT) così Excel/pandas li leggono senza locale. */
function csvCell(v: CsvValue): string {
  if (v == null) return "";
  const s = typeof v === "number" ? String(v) : v;
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function buildCsv(items: StockSearchItem[], isVisible: (id: string) => boolean): string {
  // Ticker + name sono la colonna identità sempre-attiva della tabella;
  // le altre seguono la visibilità corrente delle colonne.
  const fields = CSV_FIELDS.filter((f) => isVisible(f.id));
  const header = ["ticker", "name", ...fields.map((f) => f.header)];
  const lines = [header.join(",")];
  for (const it of items) {
    lines.push(
      [
        csvCell(it.stock.ticker),
        csvCell(it.stock.name),
        ...fields.map((f) => csvCell(f.value(it))),
      ].join(","),
    );
  }
  return lines.join("\r\n");
}

function downloadCsv(csv: string, filename: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

interface Props {
  /** Righe della pagina corrente (per l'export "pagina corrente"). */
  items: StockSearchItem[];
  /** Stesso oggetto params della search corrente — l'export "tutti i
   *  filtrati" lo rilancia con limit alto e offset 0. */
  searchParams: SearchParams;
  /** Totale filtrato (per il label del bottone "tutti"). */
  total: number;
  isColumnVisible: (id: string) => boolean;
}

/** Toolbar "Esporta CSV": due varianti in un popover — la pagina corrente
 *  (dati già in memoria, zero rete) o TUTTI i risultati filtrati (ri-chiama
 *  la search con gli stessi filtri, limit=999/offset=0; il service clampa
 *  a 500 per richiesta quindi pagina finché serve). Valori RAW, niente
 *  formattazione it-IT. */
export function ExportCsvButton({ items, searchParams, total, isColumnVisible }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stamp = new Date().toISOString().slice(0, 10);

  const exportPage = () => {
    downloadCsv(buildCsv(items, isColumnVisible), `screener-pagina-${stamp}.csv`);
    setOpen(false);
  };

  const exportAll = async () => {
    setBusy(true);
    setError(null);
    try {
      // Il backend clampa limit a 500 per richiesta: pagina fino a
      // EXPORT_ALL_LIMIT righe (l'universo è ~1000, i filtri tipici meno).
      const all: StockSearchItem[] = [];
      let offset = 0;
      for (;;) {
        const page = await stocks.search({
          ...searchParams,
          limit: EXPORT_ALL_LIMIT,
          offset,
        });
        all.push(...page.items);
        if (!page.has_more || page.items.length === 0 || all.length >= EXPORT_ALL_LIMIT) break;
        offset += page.items.length;
      }
      downloadCsv(buildCsv(all.slice(0, EXPORT_ALL_LIMIT), isColumnVisible), `screener-filtrati-${stamp}.csv`);
      setOpen(false);
    } catch {
      setError("Export fallito — riprova.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5">
          <Download className="h-3.5 w-3.5" />
          Esporta CSV
          <ChevronDown className="h-3 w-3 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-1">
        <button
          type="button"
          onClick={exportPage}
          disabled={items.length === 0}
          className="w-full text-left px-2 py-1.5 text-sm rounded hover:bg-accent disabled:opacity-50"
        >
          Pagina corrente ({items.length} righe)
        </button>
        <button
          type="button"
          onClick={exportAll}
          disabled={busy || total === 0}
          className="w-full text-left px-2 py-1.5 text-sm rounded hover:bg-accent disabled:opacity-50"
        >
          {busy
            ? "Esportazione…"
            : `Tutti i filtrati (${Math.min(total, EXPORT_ALL_LIMIT).toLocaleString()} righe)`}
        </button>
        {error && (
          <div className="px-2 py-1 text-xs text-destructive">{error}</div>
        )}
      </PopoverContent>
    </Popover>
  );
}
