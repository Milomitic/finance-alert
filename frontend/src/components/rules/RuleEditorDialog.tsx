import { useState } from "react";

import type { Rule, RuleExpressionNode } from "@/api/types";
import { ExpressionPreview } from "@/components/rules/ExpressionPreview";
import { ExpressionTree } from "@/components/rules/ExpressionTree";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useCreateRule, useUpdateRule } from "@/hooks/useRules";

const DEFAULT_EXPRESSION: RuleExpressionNode = {
  op: "and",
  children: [
    { op: "atomic", kind: "rsi_oversold", params: { period: 14, threshold: 30 } },
  ],
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rule: Rule | null;
}

export function RuleEditorDialog({ open, onOpenChange, rule }: Props) {
  const isEdit = rule !== null;
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [expression, setExpression] = useState<RuleExpressionNode>(
    rule?.expression ?? DEFAULT_EXPRESSION,
  );
  const createMut = useCreateRule();
  const updateMut = useUpdateRule();
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setError(null);
    try {
      if (isEdit && rule) {
        await updateMut.mutateAsync({
          id: rule.id,
          payload: { enabled, expression },
        });
      } else {
        await createMut.mutateAsync({
          watchlist_id: null,
          kind: "composite",
          params: {},
          enabled,
          expression,
        });
      }
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore salvataggio");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Modifica regola" : "Nuova regola"}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Checkbox
              id="rule-enabled"
              checked={enabled}
              onCheckedChange={(c) => setEnabled(!!c)}
            />
            <Label htmlFor="rule-enabled" className="text-sm">Attiva</Label>
          </div>
          <div>
            <Label className="text-sm font-semibold">Condizioni</Label>
            <div className="mt-2">
              <ExpressionTree
                node={expression}
                rootNode={expression}
                depth={1}
                onChange={setExpression}
              />
            </div>
          </div>
          <ExpressionPreview expression={expression} />
          {error && <div className="text-sm text-red-600">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Annulla
          </Button>
          <Button onClick={handleSave} disabled={createMut.isPending || updateMut.isPending}>
            Salva
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
