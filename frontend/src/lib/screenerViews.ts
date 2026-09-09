/** A saved screener view: the filters, the sort and the visible columns.
 *
 * The screener already persisted these THREE things separately and none of
 * them together. Filter presets lived under `screenerFilterPresets`, column
 * visibility under `colvis:screener`, and the sort only in the URL — so
 * re-opening a saved preset restored the filters and silently left whatever
 * sort and columns happened to be in place. A view is the whole
 * configuration, which is what "riprendi il lavoro" actually means.
 *
 * ⚠️ **The stored format has TWO shapes and both must keep working.** The
 * presets a user already has in their browser are bare `FiltersState` objects
 * with no version marker. Rewriting the key would silently discard them, and
 * localStorage has no undo. `parseStored` accepts either and returns the same
 * type, so the migration happens on read and nobody has to run anything.
 *
 * A view is deliberately NOT put in the URL. The URL already carries filters
 * and sort for sharing a specific search; a view is a personal, named
 * environment, and the two answer different questions.
 */

export type SortDirection = "asc" | "desc";

export interface ScreenerView<TFilters> {
  filters: TFilters;
  sortBy: string;
  sortDir: SortDirection;
  /** Column ids the user has HIDDEN. Stored as the hidden set rather than the
   *  visible one so a column added to the table later shows up by default,
   *  the same convention `useColumnVisibility` already uses. Inverting it
   *  would make every new column invisible in every old view. */
  hiddenColumns: string[];
}

/** Marker for the shape that carries sort and columns. Absent means v1. */
const VERSION = 2;

interface StoredV2 {
  v: number;
  filters: unknown;
  sortBy?: unknown;
  sortDir?: unknown;
  hiddenColumns?: unknown;
}

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function asStringArray(x: unknown): string[] {
  return Array.isArray(x) ? x.filter((v): v is string => typeof v === "string") : [];
}

function asDirection(x: unknown, fallback: SortDirection): SortDirection {
  return x === "asc" || x === "desc" ? x : fallback;
}

/** Read one stored entry, whichever shape it is on disk.
 *
 * `defaults` supplies the sort a v1 preset never recorded. It must be the
 * table's default rather than the CURRENT sort: applying an old preset should
 * put the table in a known state, not silently keep whatever the user had.
 */
export function parseStored<TFilters>(
  raw: unknown,
  defaults: { sortBy: string; sortDir: SortDirection },
  normalizeFilters: (filters: unknown) => TFilters,
): ScreenerView<TFilters> | null {
  if (!isRecord(raw)) return null;

  // v2 announces itself. Anything else is treated as the old bare-filters
  // shape, which is the only other thing this key has ever held.
  if (typeof raw.v === "number") {
    const v2 = raw as unknown as StoredV2;
    return {
      filters: normalizeFilters(v2.filters),
      sortBy: typeof v2.sortBy === "string" ? v2.sortBy : defaults.sortBy,
      sortDir: asDirection(v2.sortDir, defaults.sortDir),
      hiddenColumns: asStringArray(v2.hiddenColumns),
    };
  }

  return {
    filters: normalizeFilters(raw),
    sortBy: defaults.sortBy,
    sortDir: defaults.sortDir,
    hiddenColumns: [],
  };
}

export function toStored<TFilters>(view: ScreenerView<TFilters>): StoredV2 {
  return {
    v: VERSION,
    filters: view.filters as unknown,
    sortBy: view.sortBy,
    sortDir: view.sortDir,
    hiddenColumns: [...view.hiddenColumns].sort(),
  };
}

/** Every stored entry under the key, keyed by name, skipping unreadable ones.
 *
 * One corrupt entry must not cost the whole menu: a user with ten saved views
 * and one bad record should lose the record, not the feature. */
export function parseAll<TFilters>(
  blob: unknown,
  defaults: { sortBy: string; sortDir: SortDirection },
  normalizeFilters: (filters: unknown) => TFilters,
): Record<string, ScreenerView<TFilters>> {
  if (!isRecord(blob)) return {};
  const out: Record<string, ScreenerView<TFilters>> = {};
  for (const [name, value] of Object.entries(blob)) {
    const parsed = parseStored(value, defaults, normalizeFilters);
    if (parsed) out[name] = parsed;
  }
  return out;
}
