import { Plus, Sliders } from "lucide-react";
import { useState } from "react";

import type { Rule } from "@/api/types";
import { RuleEditorDialog } from "@/components/rules/RuleEditorDialog";
import { RulesTable } from "@/components/rules/RulesTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useGlobalRules } from "@/hooks/useRules";

/* ─── RulesPanel — inline rules manager (right of filters on AlertsPage) ─── */
/* Was: a full standalone /rules page. Now: an embeddable panel that lives
 * in the right column of AlertsPage, replacing the previous "scan status"
 * surface (which moved to the dashboard).
 *
 * Why merge:
 *   - Rules and alerts are tightly coupled: you create a rule → it produces
 *     alerts → you tweak the rule based on what fires.
 *   - Avoids a route round-trip every time the user wants to adjust a
 *     threshold and watch the result.
 *   - The page-level title shrunk to a SectionTitle since the surrounding
 *     AlertsPage header (h2 "Alerts") still anchors the screen.
 */

export function RulesPanel() {
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
    <Card className="overflow-hidden">
      <CardContent className="p-3 space-y-3">
        <SectionTitle
          icon={Sliders}
          label="Regole alert"
          right={
            <Button size="sm" onClick={handleNew} className="h-7 px-2 text-xs">
              <Plus className="h-3.5 w-3.5 mr-1" />
              Nuova
            </Button>
          }
        />
        {rules.isLoading ? (
          <div className="text-sm text-muted-foreground py-4">Caricamento…</div>
        ) : rules.error ? (
          <div className="text-sm text-rose-600 py-4">
            Errore:{" "}
            {rules.error instanceof Error ? rules.error.message : "sconosciuto"}
          </div>
        ) : (
          <RulesTable rules={rules.data ?? []} onEdit={handleEdit} />
        )}
        <RuleEditorDialog open={open} onOpenChange={setOpen} rule={editing} />
      </CardContent>
    </Card>
  );
}
