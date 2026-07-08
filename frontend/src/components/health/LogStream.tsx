import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, Trash2, AlertTriangle, AlertCircle, Info, Bug, Check, Copy, Filter, X } from "lucide-react";
import type { LogRecord } from "@/api/platformHealth";

type Props = {
  records: LogRecord[];
  paused: boolean;
  onTogglePause: () => void;
  onClear: () => void;
  /** When set, the list is additionally filtered to this data source (a record
   * passes if any of `tokens` is a substring of its module or message) and the
   * level threshold is lifted so its errors/warnings/info all show. `tokens`
   * are explicit per-source match strings from the backend (e.g. yfinance →
   * ["yfinance","yahoo"]) so coverage isn't limited to the bare source name. */
  sourceFilter?: { label: string; tokens: string[] } | null;
  onClearSourceFilter?: () => void;
};

const LEVEL_TONE: Record<string, string> = {
  DEBUG: "text-slate-500 dark:text-slate-400",
  INFO: "text-sky-700 dark:text-sky-300",
  SUCCESS: "text-emerald-700 dark:text-emerald-300",
  WARNING: "text-amber-700 dark:text-amber-300",
  ERROR: "text-red-700 dark:text-red-300",
  CRITICAL: "text-red-800 dark:text-red-300 font-bold",
};

const LEVEL_BG: Record<string, string> = {
  WARNING: "bg-amber-50 dark:bg-amber-950/30 border-l-amber-500",
  ERROR: "bg-red-50 dark:bg-red-950/30 border-l-red-500",
  CRITICAL: "bg-red-100 dark:bg-red-950/50 border-l-red-700 dark:border-l-red-500",
};

const LEVEL_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  DEBUG: Bug,
  INFO: Info,
  SUCCESS: Info,
  WARNING: AlertTriangle,
  ERROR: AlertCircle,
  CRITICAL: AlertCircle,
};

const LEVEL_ORDER: Record<string, number> = {
  DEBUG: 10, INFO: 20, SUCCESS: 25, WARNING: 30, ERROR: 40, CRITICAL: 50,
};

/** Una riga di log in forma testuale — per la copia negli appunti. */
function fmtRecord(r: LogRecord): string {
  return `${new Date(r.ts * 1000).toLocaleTimeString()} ${r.level} ${r.module} ${r.message}`;
}

export default function LogStream({
  records,
  paused,
  onTogglePause,
  onClear,
  sourceFilter,
  onClearSourceFilter,
}: Props) {
  // Default filter: hide noisy INFO from the live view (per user request).
  // The full buffer is still available via the dropdown.
  const [levelFilter, setLevelFilter] = useState("WARNING");
  const [moduleFilter, setModuleFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");

  // Drilling into a source should surface ALL of its levels (an HTTP 403 may be
  // logged at INFO), so applying a source filter switches the level dropdown to
  // "ALL" — and resets to the WARNING+ default when cleared. This keeps the
  // dropdown HONEST: it reflects what's actually shown instead of silently
  // overriding the threshold while still displaying "WARNING+". The level then
  // applies normally (intersected with the source), so re-picking WARNING+
  // narrows a source view to just its warnings.
  useEffect(() => {
    setLevelFilter(sourceFilter ? "ALL" : "WARNING");
  }, [sourceFilter]);

  // Pause = freeze the visible buffer so the tail stops jumping while you read.
  // Snapshot the records ONLY when `paused` toggles (not on every incoming
  // record), so the underlying SSE buffer keeps filling in the background and
  // we instantly catch up on resume. The header's "in buffer" count stays live
  // off `records`, so it's clear the stream is still receiving while paused.
  const [frozen, setFrozen] = useState<LogRecord[] | null>(null);
  useEffect(() => {
    setFrozen(paused ? records : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused]);
  const viewRecords = paused ? (frozen ?? records) : records;

  const filtered = useMemo(() => {
    const threshold = LEVEL_ORDER[levelFilter] ?? 0;
    // Case-insensitive matching on BOTH text filters: log modules are
    // lowercase snake_case but the operator types "Marketaux"/"HTTP" —
    // a case-sensitive match silently returned nothing.
    const modNeedle = moduleFilter.toLowerCase();
    const searchNeedle = searchFilter.toLowerCase();
    const srcTokens = sourceFilter
      ? sourceFilter.tokens.map((t) => t.toLowerCase()).filter(Boolean)
      : null;
    const pass = viewRecords.filter((r) => {
      if (threshold && (LEVEL_ORDER[r.level] ?? 0) < threshold) return false;
      if (modNeedle && !r.module.toLowerCase().includes(modNeedle)) return false;
      if (searchNeedle && !r.message.toLowerCase().includes(searchNeedle)) return false;
      if (srcTokens && srcTokens.length) {
        const mod = r.module.toLowerCase();
        const msg = r.message.toLowerCase();
        const hit = srcTokens.some((t) => mod.includes(t) || msg.includes(t));
        if (!hit) return false;
      }
      return true;
    });
    // Newest-first: most recent record at the top of the visible list.
    // We slice BEFORE reversing so we keep the latest 500 (not the oldest).
    return pass.slice(-500).reverse();
  }, [viewRecords, levelFilter, moduleFilter, searchFilter, sourceFilter]);

  // "Copia visibili": clipboard con le righe correntemente filtrate
  // (nell'ordine cronologico originale, non newest-first) + feedback ✓.
  const [copiedAll, setCopiedAll] = useState(false);
  const copyResetRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (copyResetRef.current) clearTimeout(copyResetRef.current);
  }, []);
  const copyVisible = async () => {
    try {
      const text = [...filtered].reverse().map(fmtRecord).join("\n");
      await navigator.clipboard.writeText(text);
      setCopiedAll(true);
      if (copyResetRef.current) clearTimeout(copyResetRef.current);
      copyResetRef.current = setTimeout(() => setCopiedAll(false), 1500);
    } catch {
      // Clipboard negato (permessi/contesto non sicuro): nessun feedback.
    }
  };

  // Counts per level — used in the chip row so the operator can see at a
  // glance "how much red is in the buffer" without scrolling.
  const counts = useMemo(() => {
    const c: Record<string, number> = { WARNING: 0, ERROR: 0, CRITICAL: 0 };
    for (const r of records) c[r.level] = (c[r.level] ?? 0) + 1;
    return c;
  }, [records]);

  return (
    <section className="space-y-3 rounded-lg border bg-card shadow-sm">
      <header className="flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b flex-wrap">
        <div className="space-y-1.5">
          <h2 className="text-lg font-semibold tracking-tight">
            Log live
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {filtered.length} visibili · {records.length} in buffer
            </span>
          </h2>
          <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
            {(counts.ERROR ?? 0) + (counts.CRITICAL ?? 0) > 0 && (
              /* Chip cliccabile: porta la soglia a ERROR+ così gli errori
                 contati sono subito quelli visibili — senza cercare il
                 dropdown. */
              <button
                type="button"
                onClick={() => setLevelFilter("ERROR")}
                className="inline-flex items-center gap-1 text-red-700 dark:text-red-400 hover:underline underline-offset-2 cursor-pointer"
                title="Mostra solo gli errori (imposta il filtro livello a ERROR+)"
              >
                <AlertCircle className="h-3.5 w-3.5" />
                {(counts.ERROR ?? 0) + (counts.CRITICAL ?? 0)} errori
              </button>
            )}
            {counts.WARNING > 0 && (
              <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                <AlertTriangle className="h-3.5 w-3.5" />
                {counts.WARNING} warning
              </span>
            )}
            {paused && (
              <span className="text-amber-700 dark:text-amber-400">⏸ Stream in pausa</span>
            )}
          </div>
          {sourceFilter && (
            <button
              type="button"
              onClick={onClearSourceFilter}
              className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 dark:border-sky-800/60 bg-sky-50 dark:bg-sky-950/40 px-2.5 py-1 text-xs font-medium text-sky-700 dark:text-sky-300 hover:bg-sky-100 dark:hover:bg-sky-900/50 transition-colors"
              title="Rimuovi il filtro per fonte"
            >
              <Filter className="h-3.5 w-3.5" />
              Fonte: <span className="font-semibold">{sourceFilter.label}</span>
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        {/* flex-wrap: su mobile i controlli scendono su più righe invece di
            sbordare orizzontalmente. */}
        <div className="flex items-center gap-2 text-sm flex-wrap">
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="rounded-md border bg-background px-2.5 py-1.5 font-medium"
            title="Soglia minima del livello"
          >
            <option value="ALL">Tutti i livelli</option>
            <option value="DEBUG">DEBUG+</option>
            <option value="INFO">INFO+</option>
            <option value="WARNING">WARNING+ (default)</option>
            <option value="ERROR">ERROR+</option>
          </select>
          <input
            type="text"
            placeholder="Modulo"
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="rounded-md border bg-background px-2.5 py-1.5 w-32"
          />
          <input
            type="text"
            placeholder="Cerca testo…"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            className="rounded-md border bg-background px-2.5 py-1.5 w-52"
          />
          <button
            type="button"
            onClick={copyVisible}
            disabled={filtered.length === 0}
            className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title={`Copia negli appunti le ${filtered.length} righe visibili`}
          >
            {copiedAll ? (
              <>
                <Check className="h-4 w-4 text-emerald-600" />
                <span className="text-xs">Copiato</span>
              </>
            ) : (
              <>
                <Copy className="h-4 w-4" />
                <span className="text-xs">Copia visibili</span>
              </>
            )}
          </button>
          <button
            type="button"
            onClick={onTogglePause}
            className="rounded-md border px-2.5 py-1.5 hover:bg-muted transition-colors"
            title={paused ? "Riprendi" : "Pausa"}
          >
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
          </button>
          <button
            type="button"
            onClick={onClear}
            className="rounded-md border px-2.5 py-1.5 hover:bg-muted transition-colors"
            title="Pulisci buffer locale"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </header>

      <div className="max-h-[480px] overflow-auto font-mono text-[12.5px] leading-relaxed">
        {filtered.length === 0 && (
          <div className="px-5 py-8 text-center text-muted-foreground italic text-sm">
            Nessun log corrisponde ai filtri.
          </div>
        )}
        {filtered.map((r, i) => {
          const Icon = LEVEL_ICON[r.level];
          const bgClass = LEVEL_BG[r.level] ?? "";
          const borderClass = bgClass ? "border-l-4" : "border-l-4 border-l-transparent";
          return (
            <div
              key={`${r.ts}-${i}`}
              className={`group flex items-start gap-3 px-5 py-1.5 ${borderClass} ${bgClass} hover:bg-muted/40 transition-colors`}
            >
              <span className="text-muted-foreground shrink-0 w-[80px] tabular-nums">
                {new Date(r.ts * 1000).toLocaleTimeString()}
              </span>
              <span
                className={`shrink-0 w-[100px] font-semibold inline-flex items-center gap-1 ${
                  LEVEL_TONE[r.level] ?? ""
                }`}
              >
                {Icon && <Icon className="h-3.5 w-3.5 shrink-0" />}
                {r.level}
              </span>
              {/* Colonna modulo nascosta sotto sm: su mobile 208px di
                  snake_case rubavano tutto lo spazio al messaggio (che
                  resta ispezionabile via title). */}
              <span
                className="text-muted-foreground shrink-0 w-52 truncate font-normal hidden sm:block"
                title={r.module}
              >
                {r.module}
              </span>
              <span className="flex-1 break-all" title={r.module}>{r.message}</span>
              {/* Copia riga — visibile solo al passaggio del mouse. */}
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(fmtRecord(r)).catch(() => {});
                }}
                className="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:text-foreground transition-opacity"
                title="Copia questa riga"
                aria-label="Copia questa riga di log"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
