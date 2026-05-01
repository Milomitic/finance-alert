import { useState } from "react";
import { X } from "lucide-react";

import type { RuleKind } from "@/api/types";
import type { AlertListParams } from "@/api/alerts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Props {
  value: AlertListParams;
  onChange: (next: AlertListParams) => void;
}

const RULE_KIND_OPTIONS: { value: RuleKind | "__all__"; label: string }[] = [
  { value: "__all__", label: "Tutte le regole" },
  { value: "rsi_oversold", label: "RSI Oversold" },
  { value: "rsi_overbought", label: "RSI Overbought" },
  { value: "golden_cross", label: "Golden Cross" },
  { value: "death_cross", label: "Death Cross" },
];

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "active", label: "Tutti (esclusi archiviati)" },
  { value: "unread", label: "Solo non letti" },
  { value: "read", label: "Solo letti" },
  { value: "archived", label: "Solo archiviati" },
];

function statusToParams(status: string): Pick<AlertListParams, "read" | "archived"> {
  switch (status) {
    case "unread":
      return { read: false, archived: false };
    case "read":
      return { read: true, archived: false };
    case "archived":
      return { archived: true };
    default:
      return { archived: false };
  }
}

export function AlertFilters({ value, onChange }: Props) {
  const [tickerInput, setTickerInput] = useState(value.ticker ?? "");
  const [status, setStatus] = useState<string>("active");

  const reset = () => {
    setTickerInput("");
    setStatus("active");
    onChange({ archived: false });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end p-4 border rounded bg-card">
      <div>
        <Label htmlFor="filter-ticker">Ticker</Label>
        <Input
          id="filter-ticker"
          placeholder="es. AAPL"
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value)}
          onBlur={() => onChange({ ...value, ticker: tickerInput || undefined })}
        />
      </div>
      <div>
        <Label>Regola</Label>
        <Select
          value={value.rule_kind ?? "__all__"}
          onValueChange={(v) =>
            onChange({
              ...value,
              rule_kind: v === "__all__" ? undefined : (v as RuleKind),
            })
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Tutte" />
          </SelectTrigger>
          <SelectContent>
            {RULE_KIND_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label>Stato</Label>
        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(v);
            onChange({ ...value, ...statusToParams(v) });
          }}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Button variant="outline" onClick={reset}>
        <X className="h-4 w-4 mr-2" /> Reset
      </Button>
    </div>
  );
}
