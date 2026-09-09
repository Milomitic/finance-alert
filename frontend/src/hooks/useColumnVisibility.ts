import { useCallback, useEffect, useState } from "react";

export interface ColumnDef { id: string; label: string; }

/** Per-table column show/hide, persisted in localStorage. `columns` is the
 *  full set of toggleable columns; hidden ids are stored under
 *  `colvis:<tableId>`. Returns helpers to query + toggle visibility. */
export function useColumnVisibility(tableId: string, columns: ColumnDef[]) {
  const key = `colvis:${tableId}`;
  const [hidden, setHidden] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(key);
      return new Set<string>(raw ? JSON.parse(raw) : []);
    } catch {
      return new Set();
    }
  });
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify([...hidden])); } catch { /* ignore */ }
  }, [key, hidden]);
  const toggle = useCallback((id: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      // if/else rather than a ternary-as-statement: both branches here are
      // called for their side effect, and in that shape a dropped `()` would
      // evaluate to a method reference and silently do nothing.
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const isVisible = useCallback((id: string) => !hidden.has(id), [hidden]);
  return { columns, isVisible, toggle, hidden };
}
