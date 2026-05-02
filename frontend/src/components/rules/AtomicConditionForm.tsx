import type { RuleExpressionAtomic } from "@/api/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRuleCatalog } from "@/hooks/useRules";

interface Props {
  value: RuleExpressionAtomic;
  onChange: (next: RuleExpressionAtomic) => void;
}

export function AtomicConditionForm({ value, onChange }: Props) {
  const catalog = useRuleCatalog();

  if (catalog.isLoading || !catalog.data) {
    return <div className="text-xs text-muted-foreground">Caricamento catalog…</div>;
  }

  const entry = catalog.data.find((c) => c.kind === value.kind);

  function handleKindChange(newKind: string) {
    const newEntry = catalog.data?.find((c) => c.kind === newKind);
    onChange({
      op: "atomic",
      kind: newKind,
      params: { ...(newEntry?.default_params ?? {}) },
    });
  }

  function handleParamChange(paramKey: string, raw: string) {
    const numeric = Number(raw);
    const next: unknown =
      Number.isFinite(numeric) && raw.trim() !== "" ? numeric : raw;
    onChange({
      op: "atomic",
      kind: value.kind,
      params: { ...value.params, [paramKey]: next },
    });
  }

  return (
    <div className="flex flex-col gap-2 p-3 border rounded-md bg-muted/30">
      <div className="flex items-center gap-2">
        <Label className="text-xs w-20">Condizione</Label>
        <Select value={value.kind} onValueChange={handleKindChange}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {catalog.data.map((c) => (
              <SelectItem key={c.kind} value={c.kind}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {entry && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(entry.default_params).map(([k, defVal]) => (
            <div key={k} className="flex items-center gap-1">
              <Label className="text-[11px] text-muted-foreground">{k}</Label>
              <Input
                className="h-7 text-xs w-24"
                value={String(value.params[k] ?? defVal)}
                onChange={(e) => handleParamChange(k, e.target.value)}
              />
            </div>
          ))}
        </div>
      )}
      {entry?.description && (
        <div className="text-[11px] text-muted-foreground">{entry.description}</div>
      )}
    </div>
  );
}
