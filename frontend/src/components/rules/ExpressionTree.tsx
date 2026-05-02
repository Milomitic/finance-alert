import { Plus, X } from "lucide-react";

import type {
  RuleExpressionAtomic,
  RuleExpressionComposite,
  RuleExpressionNode,
} from "@/api/types";
import { AtomicConditionForm } from "@/components/rules/AtomicConditionForm";
import { Button } from "@/components/ui/button";

const MAX_DEPTH = 5;
const MAX_ATOMIC = 8;

function countAtomic(node: RuleExpressionNode): number {
  if (node.op === "atomic") return 1;
  return node.children.reduce((sum, c) => sum + countAtomic(c), 0);
}

function defaultAtomic(): RuleExpressionAtomic {
  return { op: "atomic", kind: "rsi_oversold", params: { period: 14, threshold: 30 } };
}

interface Props {
  node: RuleExpressionNode;
  rootNode: RuleExpressionNode;
  depth: number;
  onChange: (next: RuleExpressionNode) => void;
  onRemove?: () => void;
}

export function ExpressionTree({ node, rootNode, depth, onChange, onRemove }: Props) {
  const totalAtomic = countAtomic(rootNode);
  const canAddChild = depth < MAX_DEPTH && totalAtomic < MAX_ATOMIC;

  if (node.op === "atomic") {
    return (
      <div className="relative flex items-start gap-1">
        <div className="flex-1">
          <AtomicConditionForm value={node} onChange={(next) => onChange(next)} />
        </div>
        {onRemove && (
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0 mt-3" onClick={onRemove}>
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    );
  }

  const composite = node as RuleExpressionComposite;

  function updateChild(idx: number, child: RuleExpressionNode) {
    const next = { ...composite, children: [...composite.children] };
    next.children[idx] = child;
    onChange(next);
  }

  function removeChild(idx: number) {
    const next = { ...composite, children: composite.children.filter((_, i) => i !== idx) };
    if (next.children.length === 0) {
      onChange(defaultAtomic());
      return;
    }
    onChange(next);
  }

  function addAtomicChild() {
    const next = { ...composite, children: [...composite.children, defaultAtomic()] };
    onChange(next);
  }

  function addCompositeChild(op: "and" | "or") {
    const next = {
      ...composite,
      children: [
        ...composite.children,
        { op, children: [defaultAtomic()] } as RuleExpressionComposite,
      ],
    };
    onChange(next);
  }

  function flipOp() {
    onChange({ ...composite, op: composite.op === "and" ? "or" : "and" });
  }

  return (
    <div className="border-l-2 border-primary/40 pl-3 py-2 relative">
      <div className="flex items-center gap-2 mb-2">
        <Button variant="outline" size="sm" className="h-6 text-xs px-2" onClick={flipOp}>
          {composite.op.toUpperCase()}
        </Button>
        {onRemove && (
          <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={onRemove}>
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {composite.children.map((child, idx) => (
          <ExpressionTree
            key={idx}
            node={child}
            rootNode={rootNode}
            depth={depth + 1}
            onChange={(next) => updateChild(idx, next)}
            onRemove={() => removeChild(idx)}
          />
        ))}
      </div>
      <div className="flex gap-2 mt-2">
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={addAtomicChild}
          disabled={!canAddChild}
        >
          <Plus className="h-3 w-3 mr-1" /> Condizione
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => addCompositeChild("and")}
          disabled={!canAddChild}
        >
          <Plus className="h-3 w-3 mr-1" /> AND
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => addCompositeChild("or")}
          disabled={!canAddChild}
        >
          <Plus className="h-3 w-3 mr-1" /> OR
        </Button>
      </div>
    </div>
  );
}
