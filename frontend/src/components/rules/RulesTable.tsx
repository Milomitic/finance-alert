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

  // Same sizing pass as AlertsTable: text-base for primary cells, text-sm
  // for header + condition meta. py-2.5 instead of py-2 gives the larger
  // text room to breathe without the rows feeling cramped.
  return (
    <table className="w-full text-base border rounded-md">
      <thead className="bg-muted/50 text-sm">
        <tr>
          <th className="px-3 py-2.5 text-left font-medium">Stato</th>
          <th className="px-3 py-2.5 text-left font-medium">Tipo</th>
          <th className="px-3 py-2.5 text-left font-medium">Condizioni</th>
          <th className="px-3 py-2.5 text-right font-medium">Azioni</th>
        </tr>
      </thead>
      <tbody>
        {rules.map((r) => (
          <tr key={r.id} className="border-t">
            <td className="px-3 py-2.5">
              <Checkbox
                checked={r.enabled}
                onCheckedChange={(c) =>
                  updateMut.mutate({ id: r.id, payload: { enabled: !!c } })
                }
              />
            </td>
            <td className="px-3 py-2.5 font-medium">{r.kind}</td>
            <td className="px-3 py-2.5 text-sm text-muted-foreground">
              {describeExpression(r.expression, r.kind)}
            </td>
            <td className="px-3 py-2.5 text-right">
              <Button variant="ghost" size="sm" onClick={() => onEdit(r)}>
                <Pencil className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (confirm("Eliminare questa regola?")) {
                    deleteMut.mutate(r.id);
                  }
                }}
              >
                <Trash2 className="h-4 w-4 text-red-600" />
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
