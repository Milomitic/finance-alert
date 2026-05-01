import { useEffect, useState } from "react";

import type { Rule, RuleKind } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  useCreateRule,
  useDeleteRule,
  useGlobalRules,
  useRulesForWatchlist,
  useUpdateRule,
} from "@/hooks/useRules";

const KIND_LABEL: Record<RuleKind, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

const KIND_DEFAULT_DESCRIPTION: Record<RuleKind, string> = {
  rsi_oversold: "default: RSI(14) < 30",
  rsi_overbought: "default: RSI(14) > 70",
  golden_cross: "default: SMA(50) attraversa SMA(200) verso l'alto",
  death_cross: "default: SMA(50) attraversa SMA(200) verso il basso",
};

const ALL_KINDS: RuleKind[] = [
  "rsi_oversold",
  "rsi_overbought",
  "golden_cross",
  "death_cross",
];

type OverrideMode = "global" | "disabled" | "custom";

interface Props {
  watchlistId: number;
}

export function RulesOverrideEditor({ watchlistId }: Props) {
  const globals = useGlobalRules();
  const overrides = useRulesForWatchlist(watchlistId);
  const create = useCreateRule();
  const update = useUpdateRule();
  const del = useDeleteRule();

  const overrideByKind = new Map<RuleKind, Rule>();
  for (const r of overrides.data ?? []) overrideByKind.set(r.kind, r);

  const modeFor = (kind: RuleKind): OverrideMode => {
    const o = overrideByKind.get(kind);
    if (!o) return "global";
    if (!o.enabled) return "disabled";
    return "custom";
  };

  const setMode = async (kind: RuleKind, mode: OverrideMode) => {
    const existing = overrideByKind.get(kind);
    if (mode === "global") {
      if (existing) await del.mutateAsync(existing.id);
      return;
    }
    if (mode === "disabled") {
      if (existing) {
        await update.mutateAsync({ id: existing.id, payload: { enabled: false } });
      } else {
        await create.mutateAsync({
          watchlist_id: watchlistId,
          kind,
          params: {},
          enabled: false,
        });
      }
      return;
    }
    // custom: create with global params copied as starting point
    const globalParams = globals.data?.find((g) => g.kind === kind)?.params ?? {};
    if (existing) {
      await update.mutateAsync({
        id: existing.id,
        payload: { enabled: true, params: globalParams },
      });
    } else {
      await create.mutateAsync({
        watchlist_id: watchlistId,
        kind,
        params: globalParams,
        enabled: true,
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Override regole</CardTitle>
        <CardDescription>
          Le 4 regole globali sono attive sull'intero catalogo. Qui puoi
          disabilitarle o personalizzarle solo per gli stock di questa watchlist.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {ALL_KINDS.map((kind) => {
          const mode = modeFor(kind);
          return (
            <div key={kind} className="border rounded p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <Label className="text-base">{KIND_LABEL[kind]}</Label>
                  <p className="text-xs text-muted-foreground mt-1">
                    {KIND_DEFAULT_DESCRIPTION[kind]}
                  </p>
                </div>
                <div className="flex gap-1">
                  {(["global", "disabled", "custom"] as OverrideMode[]).map((m) => (
                    <Button
                      key={m}
                      size="sm"
                      variant={mode === m ? "default" : "outline"}
                      onClick={() => setMode(kind, m)}
                    >
                      {m === "global"
                        ? "Default"
                        : m === "disabled"
                          ? "Disabilita"
                          : "Custom"}
                    </Button>
                  ))}
                </div>
              </div>
              {mode === "custom" && overrideByKind.get(kind) && (
                <div className="mt-3 text-xs">
                  <Label>Parametri (JSON):</Label>
                  <CustomParamsEditor
                    rule={overrideByKind.get(kind)!}
                  />
                </div>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function CustomParamsEditor({ rule }: { rule: Rule }) {
  const update = useUpdateRule();
  const [json, setJson] = useState(JSON.stringify(rule.params, null, 2));
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setJson(JSON.stringify(rule.params, null, 2));
  }, [rule.params]);

  const save = async () => {
    try {
      const parsed = JSON.parse(json);
      setErr(null);
      await update.mutateAsync({ id: rule.id, payload: { params: parsed } });
    } catch (e) {
      setErr("JSON non valido");
    }
  };

  return (
    <div className="mt-2">
      <textarea
        className="w-full border rounded p-2 font-mono text-xs"
        rows={4}
        value={json}
        onChange={(e) => setJson(e.target.value)}
      />
      {err && <p className="text-destructive text-xs mt-1">{err}</p>}
      <Button size="sm" className="mt-2" onClick={save}>
        Salva params
      </Button>
    </div>
  );
}
