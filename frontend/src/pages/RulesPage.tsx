import { Plus } from "lucide-react";
import { useState } from "react";

import type { Rule } from "@/api/types";
import { RuleEditorDialog } from "@/components/rules/RuleEditorDialog";
import { RulesTable } from "@/components/rules/RulesTable";
import { Button } from "@/components/ui/button";
import { useGlobalRules } from "@/hooks/useRules";

export default function RulesPage() {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Rule | null>(null);
  const rules = useGlobalRules();

  function handleNew() {
    setEditing(null);
    setOpen(true);
  }

  function handleEdit(rule: Rule) {
    setEditing(rule);
    setOpen(true);
  }

  return (
    <div className="flex flex-col gap-4 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Regole alert</h2>
          <p className="text-sm text-muted-foreground">
            Componi condizioni AND/OR e visualizza in anteprima i match su uno stock.
          </p>
        </div>
        <Button onClick={handleNew}>
          <Plus className="h-4 w-4 mr-2" /> Nuova regola
        </Button>
      </div>
      {rules.isLoading ? (
        <div className="text-sm text-muted-foreground">Caricamento…</div>
      ) : rules.error ? (
        <div className="text-sm text-red-600">
          Errore: {rules.error instanceof Error ? rules.error.message : "sconosciuto"}
        </div>
      ) : (
        <RulesTable rules={rules.data ?? []} onEdit={handleEdit} />
      )}
      <RuleEditorDialog open={open} onOpenChange={setOpen} rule={editing} />
    </div>
  );
}
