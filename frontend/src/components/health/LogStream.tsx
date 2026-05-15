import { useMemo, useState } from "react";
import { Pause, Play, Trash2, AlertTriangle, AlertCircle, Info, Bug } from "lucide-react";
import type { LogRecord } from "@/api/platformHealth";

type Props = {
  records: LogRecord[];
  paused: boolean;
  onTogglePause: () => void;
  onClear: () => void;
};

const LEVEL_TONE: Record<string, string> = {
  DEBUG: "text-slate-500",
  INFO: "text-sky-700",
  SUCCESS: "text-emerald-700",
  WARNING: "text-amber-700",
  ERROR: "text-red-700",
  CRITICAL: "text-red-800 font-bold",
};

const LEVEL_BG: Record<string, string> = {
  WARNING: "bg-amber-50 border-l-amber-500",
  ERROR: "bg-red-50 border-l-red-500",
  CRITICAL: "bg-red-100 border-l-red-700",
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

export default function LogStream({
  records,
  paused,
  onTogglePause,
  onClear,
}: Props) {
  // Default filter: hide noisy INFO from the live view (per user request).
  // The full buffer is still available via the dropdown.
  const [levelFilter, setLevelFilter] = useState("WARNING");
  const [moduleFilter, setModuleFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");

  const filtered = useMemo(() => {
    const threshold = LEVEL_ORDER[levelFilter] ?? 0;
    const pass = records.filter((r) => {
      if (threshold && (LEVEL_ORDER[r.level] ?? 0) < threshold) return false;
      if (moduleFilter && !r.module.includes(moduleFilter)) return false;
      if (searchFilter && !r.message.includes(searchFilter)) return false;
      return true;
    });
    // Newest-first: most recent record at the top of the visible list.
    // We slice BEFORE reversing so we keep the latest 500 (not the oldest).
    return pass.slice(-500).reverse();
  }, [records, levelFilter, moduleFilter, searchFilter]);

  // Counts per level — used in the chip row so the operator can see at a
  // glance "how much red is in the buffer" without scrolling.
  const counts = useMemo(() => {
    const c: Record<string, number> = { WARNING: 0, ERROR: 0, CRITICAL: 0 };
    for (const r of records) c[r.level] = (c[r.level] ?? 0) + 1;
    return c;
  }, [records]);

  return (
    <section className="space-y-3 rounded-lg border bg-card shadow-sm">
      <header className="flex items-start justify-between gap-3 px-4 pt-4 pb-2 border-b flex-wrap">
        <div className="space-y-1">
          <h2 className="text-base font-semibold tracking-tight">
            Log live
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {filtered.length} visibili · {records.length} in buffer
            </span>
          </h2>
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            {(counts.ERROR ?? 0) + (counts.CRITICAL ?? 0) > 0 && (
              <span className="inline-flex items-center gap-1 text-red-700">
                <AlertCircle className="h-3 w-3" />
                {(counts.ERROR ?? 0) + (counts.CRITICAL ?? 0)} errori
              </span>
            )}
            {counts.WARNING > 0 && (
              <span className="inline-flex items-center gap-1 text-amber-700">
                <AlertTriangle className="h-3 w-3" />
                {counts.WARNING} warning
              </span>
            )}
            {paused && (
              <span className="text-amber-700">⏸ Stream in pausa</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="rounded-md border bg-background px-2 py-1.5 font-medium"
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
            className="rounded-md border bg-background px-2 py-1.5 w-28"
          />
          <input
            type="text"
            placeholder="Cerca testo…"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            className="rounded-md border bg-background px-2 py-1.5 w-44"
          />
          <button
            type="button"
            onClick={onTogglePause}
            className="rounded-md border px-2 py-1.5 hover:bg-muted transition-colors"
            title={paused ? "Riprendi" : "Pausa"}
          >
            {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={onClear}
            className="rounded-md border px-2 py-1.5 hover:bg-muted transition-colors"
            title="Pulisci buffer locale"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      <div className="max-h-[420px] overflow-auto font-mono text-[11.5px] leading-relaxed">
        {filtered.length === 0 && (
          <div className="px-4 py-6 text-center text-muted-foreground italic">
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
              className={`flex items-start gap-3 px-4 py-1 ${borderClass} ${bgClass} hover:bg-muted/40 transition-colors`}
            >
              <span className="text-muted-foreground shrink-0 w-[72px] tabular-nums">
                {new Date(r.ts * 1000).toLocaleTimeString()}
              </span>
              <span
                className={`shrink-0 w-[90px] font-semibold inline-flex items-center gap-1 ${
                  LEVEL_TONE[r.level] ?? ""
                }`}
              >
                {Icon && <Icon className="h-3 w-3 shrink-0" />}
                {r.level}
              </span>
              <span className="text-muted-foreground shrink-0 w-44 truncate font-normal" title={r.module}>
                {r.module}
              </span>
              <span className="flex-1 break-all">{r.message}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
