import { useState } from "react";

import type { RuleExpressionNode } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRulePreview } from "@/hooks/useRules";

interface Props {
  expression: RuleExpressionNode;
}

export function ExpressionPreview({ expression }: Props) {
  const [ticker, setTicker] = useState("AAPL");
  const preview = useRulePreview();

  function handleTest() {
    preview.mutate({ ticker: ticker.trim().toUpperCase(), expression });
  }

  return (
    <div className="flex flex-col gap-2 p-3 border rounded-md bg-muted/20">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Anteprima su ticker:</span>
        <Input
          className="h-7 w-24 text-sm"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
        />
        <Button size="sm" className="h-7" onClick={handleTest} disabled={preview.isPending}>
          {preview.isPending ? "Test…" : "Test"}
        </Button>
      </div>
      {preview.error && (
        <div className="text-xs text-red-600">
          {preview.error instanceof Error ? preview.error.message : "Errore"}
        </div>
      )}
      {preview.data && (
        <div className="text-xs">
          <div className="font-semibold">
            Risultato: {preview.data.matched ? "✓ Scatta" : "✗ Non scatta"}
          </div>
          <pre className="mt-1 p-2 bg-background border rounded text-[10px] overflow-auto max-h-40">
            {JSON.stringify(preview.data.snapshot, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
