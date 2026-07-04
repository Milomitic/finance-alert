import { Briefcase, Check, Loader2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useOpenPosition } from "@/hooks/usePositions";
import type { Playbook } from "@/lib/tradePlaybook";

interface Props {
  ticker: string;
  alertId: number;
  playbook: Playbook;
}

/** Accepts the Italian decimal comma too ("142,50"). Null = not a usable
 *  positive price. */
function parsePrice(s: string): number | null {
  const v = Number(s.replace(",", "."));
  return Number.isFinite(v) && v > 0 ? v : null;
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1 min-w-0">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
        {label}
      </span>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        inputMode="decimal"
        className="h-8 text-sm tabular-nums"
      />
    </label>
  );
}

/** "Traccia trade" — persists the playbook's entry/stop/target as a tracked
 *  position (B3-6). Collapsed to a single button under the PlaybookView;
 *  expands into a small inline form prefilled from the playbook. On save the
 *  position lands on the /positions page (live P&L + auto stop/target close). */
export function TrackTradeForm({ ticker, alertId, playbook }: Props) {
  const [open, setOpen] = useState(false);
  const [entry, setEntry] = useState(playbook.entry.toFixed(2));
  const [stop, setStop] = useState(playbook.stop.toFixed(2));
  const [target, setTarget] = useState(
    (playbook.targets[0]?.price ?? playbook.entry).toFixed(2),
  );
  const [size, setSize] = useState("");
  const mut = useOpenPosition();

  if (mut.isSuccess) {
    return (
      <div className="mt-2 flex items-center gap-2 flex-wrap rounded-md border border-emerald-300/70 bg-emerald-50/60 dark:bg-emerald-950/20 px-3 py-2 text-sm">
        <Check className="h-4 w-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
        <span>Posizione aperta su {ticker}.</span>
        <Link
          to="/positions"
          className="font-medium underline underline-offset-2"
        >
          Vai alle posizioni
        </Link>
      </div>
    );
  }

  if (!open) {
    return (
      <Button
        size="sm"
        variant="outline"
        className="mt-2"
        onClick={() => setOpen(true)}
        title="Salva entry/stop/target del piano come posizione tracciata con P&L live"
      >
        <Briefcase className="h-3.5 w-3.5 mr-1.5" />
        Traccia trade
      </Button>
    );
  }

  const entryV = parsePrice(entry);
  const stopV = parsePrice(stop);
  const targetV = parsePrice(target);
  const sizeV = size.trim() === "" ? null : parsePrice(size);
  // Same coherence rule the backend enforces: stop/target relative order
  // must match the side, or the position would auto-close on the first tick.
  const orderOk =
    stopV != null && targetV != null &&
    (playbook.side === "long" ? stopV < targetV : stopV > targetV);
  const valid =
    entryV != null && orderOk && (size.trim() === "" || sizeV != null);

  const submit = () => {
    if (!valid || mut.isPending) return;
    mut.mutate({
      ticker,
      side: playbook.side,
      entry_price: entryV,
      stop_price: stopV,
      target_price: targetV,
      size: sizeV,
      alert_id: alertId,
    });
  };

  return (
    <div className="mt-2 rounded-md border border-border/60 p-3 space-y-2">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
        Traccia trade — {playbook.side === "long" ? "Long" : "Short"} su {ticker}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Field label="Entry" value={entry} onChange={setEntry} />
        <Field label="Stop" value={stop} onChange={setStop} />
        <Field label="Target" value={target} onChange={setTarget} />
        <Field
          label="Size (opz.)"
          value={size}
          onChange={setSize}
          placeholder="n° azioni"
        />
      </div>
      {!orderOk && stopV != null && targetV != null && (
        <div className="text-xs text-rose-600 dark:text-rose-400">
          {playbook.side === "long"
            ? "Per un long lo stop deve stare sotto il target."
            : "Per uno short lo stop deve stare sopra il target."}
        </div>
      )}
      {mut.isError && (
        <div className="text-xs text-rose-600 dark:text-rose-400">
          Errore nell'apertura della posizione: {(mut.error as Error).message}
        </div>
      )}
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={submit} disabled={!valid || mut.isPending}>
          {mut.isPending && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
          Apri posizione
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setOpen(false)}
          disabled={mut.isPending}
        >
          Annulla
        </Button>
        <span className="text-[10px] text-muted-foreground/70 italic ml-auto hidden sm:inline">
          Senza size il P&amp;L è solo in %.
        </span>
      </div>
    </div>
  );
}
