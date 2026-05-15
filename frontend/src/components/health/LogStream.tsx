import { useMemo, useState } from "react";
import { Pause, Play, Trash2 } from "lucide-react";
import type { LogRecord } from "@/api/platformHealth";

type Props = {
  records: LogRecord[];
  paused: boolean;
  onTogglePause: () => void;
  onClear: () => void;
};

const LEVEL_TONE: Record<string, string> = {
  DEBUG: "text-muted-foreground",
  INFO: "text-slate-700",
  SUCCESS: "text-emerald-700",
  WARNING: "text-amber-700",
  ERROR: "text-red-700",
  CRITICAL: "text-red-800 font-bold",
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
  const [levelFilter, setLevelFilter] = useState("ALL");
  const [moduleFilter, setModuleFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");

  const filtered = useMemo(() => {
    const threshold = LEVEL_ORDER[levelFilter] ?? 0;
    return records.filter((r) => {
      if (threshold && (LEVEL_ORDER[r.level] ?? 0) < threshold) return false;
      if (moduleFilter && !r.module.includes(moduleFilter)) return false;
      if (searchFilter && !r.message.includes(searchFilter)) return false;
      return true;
    });
  }, [records, levelFilter, moduleFilter, searchFilter]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h2 className="text-lg font-semibold">
          Log{" "}
          <span className="text-xs text-muted-foreground">
            ({filtered.length} / {records.length})
          </span>
        </h2>
        <div className="flex items-center gap-2 text-xs">
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="rounded border bg-background px-2 py-1"
          >
            <option value="ALL">Tutti i livelli</option>
            <option value="DEBUG">DEBUG+</option>
            <option value="INFO">INFO+</option>
            <option value="WARNING">WARNING+</option>
            <option value="ERROR">ERROR+</option>
          </select>
          <input
            type="text"
            placeholder="Modulo"
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="rounded border bg-background px-2 py-1 w-32"
          />
          <input
            type="text"
            placeholder="Cerca testo"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            className="rounded border bg-background px-2 py-1 w-40"
          />
          <button
            type="button"
            onClick={onTogglePause}
            className="rounded border px-2 py-1 hover:bg-muted"
            title={paused ? "Riprendi" : "Pausa"}
          >
            {paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
          </button>
          <button
            type="button"
            onClick={onClear}
            className="rounded border px-2 py-1 hover:bg-muted"
            title="Pulisci buffer locale"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>

      <div className="rounded border bg-background max-h-[400px] overflow-auto font-mono text-xs">
        {filtered.length === 0 && (
          <div className="p-3 text-muted-foreground italic">
            Nessun log corrisponde ai filtri.
          </div>
        )}
        {filtered.slice(-500).map((r, i) => (
          <div
            key={`${r.ts}-${i}`}
            className="flex gap-2 px-2 py-0.5 hover:bg-muted/40"
          >
            <span className="text-muted-foreground shrink-0 w-20">
              {new Date(r.ts * 1000).toLocaleTimeString()}
            </span>
            <span
              className={`shrink-0 w-16 font-semibold ${
                LEVEL_TONE[r.level] ?? ""
              }`}
            >
              {r.level}
            </span>
            <span className="text-muted-foreground shrink-0 w-32 truncate">
              [{r.module}]
            </span>
            <span className="flex-1 break-all">{r.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
