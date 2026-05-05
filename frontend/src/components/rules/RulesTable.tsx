import { Pencil, Trash2 } from "lucide-react";

import type { Rule, RuleExpressionNode } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useDeleteRule, useUpdateRule } from "@/hooks/useRules";

function describeExpression(expr: RuleExpressionNode | null | undefined, kind: string): string {
  if (expr === null || expr === undefined) return kind;
  if (expr.op === "atomic") return expr.kind ?? kind;
  const children = expr.children ?? [];
  return `${expr.op.toUpperCase()} (${children.length} cond.)`;
}

interface Props {
  rules: Rule[];
  onEdit: (rule: Rule) => void;
}

export function RulesTable({ rules, onEdit }: Props) {
  const updateMut = useUpdateRule();
  const deleteMut = useDeleteRule();

  if (rules.length === 0) {
    return (
      <div className="text-sm text-muted-foreground p-6 text-center border rounded-md">
        Nessuna regola configurata. Clicca "+ Nuova regola" per crearne una.
      </div>
    );
  }

  // Compact density (`text-sm` rows, `py-1.5`) so the table fits in the
  // ~260px viewport the AlertsPage RulesPanel grants — the previous
  // `text-base` + `py-2.5` made each row ~48px which left only 4 rules
  // visible before scroll. The narrower 480px sidebar slot also benefits
  // from tighter horizontal padding.
  return (
    <div className="rounded-md border max-h-[260px] overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="bg-muted/60 text-xs sticky top-0 z-10">
          <tr>
            <th className="px-2 py-1.5 text-left font-semibold w-8">On</th>
            <th className="px-2 py-1.5 text-left font-semibold">Tipo</th>
            <th className="px-2 py-1.5 text-left font-semibold">Condizioni</th>
            <th className="px-2 py-1.5 text-right font-semibold w-20">Azioni</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id} className="border-t hover:bg-muted/30 transition-colors">
              <td className="px-2 py-1.5">
                <Checkbox
                  checked={r.enabled}
                  onCheckedChange={(c) =>
                    updateMut.mutate({ id: r.id, payload: { enabled: !!c } })
                  }
                />
              </td>
              <td className="px-2 py-1.5 font-medium truncate">{r.kind}</td>
              <td className="px-2 py-1.5 text-xs text-muted-foreground truncate">
                {describeExpression(r.expression, r.kind)}
              </td>
              <td className="px-2 py-1.5 text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  onClick={() => onEdit(r)}
                  title="Modifica"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  onClick={() => {
                    if (confirm("Eliminare questa regola?")) {
                      deleteMut.mutate(r.id);
                    }
                  }}
                  title="Elimina"
                >
                  <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
