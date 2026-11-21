import { AreaChart, CandlestickChart, Download, LineChart, Maximize2, X } from "lucide-react";
import { useState } from "react";

import type { ChartType } from "@/components/stock/PriceChart";
import { cn } from "@/lib/utils";
import { BENCHMARKS } from "@/lib/benchmarks";
import { Segmentato } from "@/components/ui/segmentato";
import { Button } from "@/components/ui/button";

interface Props {
  chartType: ChartType;
  onChartType: (t: ChartType) => void;
  benchmark: string;
  onBenchmark: (symbol: string) => void;
  compareTicker: string;
  onCompareTicker: (ticker: string) => void;
  onExport: () => void;
  /** Riporta il grafico alla finestra di partenza del timeframe corrente.
   *
   *  Nasce con la pan piu libera: prima il limite era sei barre oltre i dati e
   *  non ci si poteva perdere, adesso si spinge il prezzo quasi fuori schermo
   *  ed e giusto che si possa — ma senza una via di ritorno il gesto e a senso
   *  unico e l'unico rimedio era ricaricare la pagina. */
  onResetZoom: () => void;
}

const TYPES: { key: ChartType; label: string; Icon: typeof LineChart }[] = [
  { key: "candle", label: "Candele", Icon: CandlestickChart },
  { key: "line", label: "Linea", Icon: LineChart },
  { key: "area", label: "Area", Icon: AreaChart },
];

/** Chart render controls: candle / line / area style, a benchmark overlay
 *  picker, and PNG export. Segmented buttons match the RangeSelector's visual
 *  language. */
export function ChartOptionsToolbar({
  chartType, onChartType, benchmark, onBenchmark, compareTicker, onCompareTicker, onExport,
  onResetZoom,
}: Props) {
  // Local input state; commit the compare ticker on Enter / blur so we don't
  // fire a fetch on every keystroke.
  const [cmp, setCmp] = useState(compareTicker);
  /* Il campo e' controllato localmente e si allinea alla prop quando questa
   * cambia da fuori (per esempio da un link con un confronto gia' scelto).
   * In render e non in effect: da effect il campo mostrerebbe per un
   * fotogramma il valore precedente, e se l'utente stesse digitando in quel
   * momento il carattere appena battuto verrebbe sovrascritto. */
  const [cmpProp, setCmpProp] = useState(compareTicker);
  if (compareTicker !== cmpProp) {
    setCmpProp(compareTicker);
    setCmp(compareTicker);
  }
  const commit = () => onCompareTicker(cmp.trim().toUpperCase());

  return (
    <div className="inline-flex items-center gap-1.5">
      <Segmentato etichetta="Tipo di grafico" taglia="media" valore={chartType} onCambia={onChartType}
        voci={TYPES.map(({ key, label, Icon }) => ({ id: key, nome: label, titolo: label, label: <Icon className="h-4 w-4" aria-hidden /> }))} />
      <select
        value={benchmark}
        onChange={(e) => onBenchmark(e.target.value)}
        title="Confronta con un indice"
        aria-label="Benchmark"
        className={cn(
          "h-8 px-2 text-sm font-medium rounded-md border bg-muted/30 cursor-pointer",
          "transition-colors hover:text-foreground",
          benchmark ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {BENCHMARKS.map((b) => (
          <option key={b.symbol} value={b.symbol}>
            {b.label}
          </option>
        ))}
      </select>
      {/* Multi-ticker compare — type a ticker, commit on Enter/blur. */}
      <div className="relative inline-flex items-center">
        <input
          value={cmp}
          onChange={(e) => setCmp(e.target.value.toUpperCase())}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
          }}
          onBlur={commit}
          placeholder="vs ticker…"
          aria-label="Confronta con un titolo"
          title="Sovrapponi un altro titolo (ribasato)"
          className={cn(
            "h-8 w-24 px-2 text-sm rounded-md border bg-muted/30",
            compareTicker ? "pr-6 text-foreground" : "text-muted-foreground",
          )}
        />
        {compareTicker && (
          <button
            type="button"
            onClick={() => {
              setCmp("");
              onCompareTicker("");
            }}
            title="Rimuovi confronto"
            aria-label="Rimuovi confronto"
            className="absolute right-1 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      <Button
        type="button"
        onClick={onResetZoom}
        title="Reimposta zoom e posizione"
        aria-label="Reimposta zoom e posizione"
        variant="outline" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground"
      >
        <Maximize2 className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        onClick={onExport}
        title="Esporta PNG"
        aria-label="Esporta PNG"
        variant="outline" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground"
      >
        <Download className="h-4 w-4" />
      </Button>
    </div>
  );
}
