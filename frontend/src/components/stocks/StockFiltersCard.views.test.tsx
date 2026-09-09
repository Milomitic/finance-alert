import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EMPTY_FILTERS, StockFiltersCard } from "./StockFiltersCard";

/* A saved view is filters + sort + columns.
 *
 * The screener persisted all three and none of them together: presets held
 * filters, `colvis:screener` held columns, and the sort lived only in the URL.
 * Re-opening a preset therefore restored the filters and left whatever sort
 * and columns happened to be in place, which is not "riprendere il lavoro" —
 * it is restoring a third of it and looking like it worked.
 *
 * ⚠️ The load-bearing case is the FIRST describe below. Presets already in a
 * user's browser are bare filter objects with no version marker. Reading them
 * as unrecognised would delete saved work with no undo, and would look exactly
 * like a clean new feature.
 */

let mem: Map<string, string>;

beforeEach(() => {
  mem = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => mem.get(k) ?? null,
    setItem: (k: string, v: string) => void mem.set(k, v),
    removeItem: (k: string) => void mem.delete(k),
    clear: () => mem.clear(),
    key: (i: number) => [...mem.keys()][i] ?? null,
    get length() {
      return mem.size;
    },
  });
});

const DEFAULTS = { sortBy: "ticker", sortDir: "asc" as const };

function renderCard(overrides: Partial<Parameters<typeof StockFiltersCard>[0]> = {}) {
  const onApply = vi.fn();
  const user = userEvent.setup();
  render(
    <StockFiltersCard
      state={EMPTY_FILTERS}
      onChange={vi.fn()}
      filters={undefined}
      view={{
        sortBy: "score",
        sortDir: "desc",
        hiddenColumns: ["rsi", "volume"],
        defaults: DEFAULTS,
        onApply,
      }}
      {...overrides}
    />,
  );
  return { user, onApply };
}

const openMenu = async (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: /preset/i }));

describe("i preset gia nel browser non vengono persi", () => {
  it("mostra una vecchia voce salvata come solo filtri", async () => {
    mem.set("screenerFilterPresets", JSON.stringify({ "vecchio mio": { minScore: 60 } }));

    const { user } = renderCard();
    await openMenu(user);

    // Exact match: the row also carries an "Elimina preset vecchio mio"
    // button, so a loose pattern finds two and fails for the wrong reason.
    expect(screen.getByRole("button", { name: /^vecchio mio$/i })).toBeInTheDocument();
  });

  it("applicandola usa l'ordinamento PREDEFINITO, non quello corrente", async () => {
    // The card is currently on score/desc. An old preset never recorded a
    // sort, so it must land on the table default — otherwise the same preset
    // behaves differently depending on what the user did a moment earlier.
    mem.set("screenerFilterPresets", JSON.stringify({ vecchio: { minScore: 60 } }));

    const { user, onApply } = renderCard();
    await openMenu(user);
    await user.click(screen.getByRole("button", { name: /^vecchio$/i }));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0][0]).toMatchObject({
      sortBy: "ticker",
      sortDir: "asc",
      hiddenColumns: [],
    });
  });
});

describe("una vista salva l'intera configurazione", () => {
  it("registra ordinamento e colonne insieme ai filtri", async () => {
    const { user } = renderCard();
    await openMenu(user);

    await user.type(screen.getByRole("textbox", { name: /nome del preset/i }), "mia vista");
    await user.click(screen.getByRole("button", { name: /^salva$/i }));

    const stored = JSON.parse(mem.get("screenerFilterPresets") as string);
    expect(stored["mia vista"]).toMatchObject({
      v: 2,
      sortBy: "score",
      sortDir: "desc",
      hiddenColumns: ["rsi", "volume"],
    });
  });

  it("riapplicandola restituisce tutte e tre le parti", async () => {
    const { user, onApply } = renderCard();
    await openMenu(user);
    await user.type(screen.getByRole("textbox", { name: /nome del preset/i }), "completa");
    await user.click(screen.getByRole("button", { name: /^salva$/i }));

    await user.click(screen.getByRole("button", { name: /^completa$/i }));

    expect(onApply).toHaveBeenCalledTimes(1);
    const applied = onApply.mock.calls[0][0];
    expect(applied.sortBy).toBe("score");
    expect(applied.sortDir).toBe("desc");
    expect(applied.hiddenColumns).toEqual(["rsi", "volume"]);
    expect(applied.filters).toBeTruthy();
  });

  it("senza una tabella sotto, non finge di ripristinare un ordinamento", async () => {
    // The card is used where no table exists. Reporting a sort there would be
    // inventing one; the old filters-only path stays.
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <StockFiltersCard state={EMPTY_FILTERS} onChange={onChange} filters={undefined} />,
    );
    await openMenu(user);
    await user.type(screen.getByRole("textbox", { name: /nome del preset/i }), "senza tabella");
    await user.click(screen.getByRole("button", { name: /^salva$/i }));

    await user.click(screen.getByRole("button", { name: /^senza tabella$/i }));

    expect(onChange).toHaveBeenCalledTimes(1);
    // A FiltersState, not a view envelope.
    expect(onChange.mock.calls[0][0]).not.toHaveProperty("hiddenColumns");
  });
});
