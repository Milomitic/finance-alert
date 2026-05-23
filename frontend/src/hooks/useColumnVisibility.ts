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
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);
  const isVisible = useCallback((id: string) => !hidden.has(id), [hidden]);
  return { columns, isVisible, toggle, hidden };
}
