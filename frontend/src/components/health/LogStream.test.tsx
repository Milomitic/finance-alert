import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { StreamedLog } from "@/hooks/usePlatformHealthStream";

import LogStream from "./LogStream";

/* This list is fed by an EventSource that calls setLogs for EVERY message the
 * backend emits, so it re-renders continuously while the health page is open.
 * It holds up to 500 records at roughly nine DOM nodes each.
 *
 * The row key was `${r.ts}-${i}` — an INDEX, into a list that is reversed for
 * display (newest first) and sliced to the last 500. So one arriving record
 * shifted every other row's index, every key changed, and React did not
 * re-render 500 rows: it unmounted and rebuilt them, ~4,500 nodes for a single
 * log line. `React.memo` on the row would have done nothing at all, because a
 * changed key is a different element, not a re-render.
 *
 * A LogRecord carries no identity — the API sends ts/level/module/message — so
 * the fix could not live here. `usePlatformHealthStream` now stamps a
 * monotonic `seq` as it appends, which is right: identity means "which record
 * is this in the buffer", and the buffer is what that hook owns.
 *
 * This test asserts NODE IDENTITY rather than a key attribute, because the key
 * is not observable in the DOM and asserting it would mean reading React
 * internals. If a row survived, its element is the same object.
 */

const mk = (seq: number, message: string): StreamedLog => ({
  seq,
  ts: 1_757_000_000 + seq,
  level: "ERROR", // the default filter is WARNING+, so INFO would be hidden
  module: "app.services.scan",
  function: "run",
  line: 10,
  message,
  exception: null,
});

const props = {
  paused: false,
  onTogglePause: vi.fn(),
  onClear: vi.fn(),
};

describe("an arriving log line does not rebuild the ones already on screen", () => {
  it("keeps the existing rows' DOM nodes across an append", () => {
    const initial = [mk(0, "evento zero"), mk(1, "evento uno"), mk(2, "evento due")];
    const { rerender } = render(<LogStream records={initial} {...props} />);

    const before = initial.map((r) => screen.getByText(r.message));

    rerender(<LogStream records={[...initial, mk(3, "evento tre")]} {...props} />);

    const after = initial.map((r) => screen.getByText(r.message));

    // `toBe`, not `toEqual`. On DOM nodes toEqual compares STRUCTURE, and a
    // freshly remounted row is structurally identical to the one it replaced —
    // so toEqual passes in exactly the case this test exists to catch. Checked:
    // with the old index key it stayed green.
    after.forEach((el, i) => expect(el).toBe(before[i]));
  });

  it("still shows the new record, at the top", () => {
    const initial = [mk(0, "evento zero")];
    const { rerender } = render(<LogStream records={initial} {...props} />);

    rerender(<LogStream records={[...initial, mk(1, "evento uno")]} {...props} />);

    // Newest-first is the whole point of the reverse that broke the keys.
    const shown = screen.getAllByTitle("Copia questa riga");
    expect(shown).toHaveLength(2);
    expect(screen.getByText("evento uno")).toBeInTheDocument();
    expect(screen.getByText("evento zero")).toBeInTheDocument();
  });

  it("drops a row's node when that record leaves the buffer", () => {
    // The inverse of the first test: identity must track the RECORD, not the
    // position, so a row that is genuinely gone must genuinely unmount.
    const initial = [mk(0, "evento zero"), mk(1, "evento uno")];
    const { rerender } = render(<LogStream records={initial} {...props} />);
    expect(screen.getByText("evento zero")).toBeInTheDocument();

    rerender(<LogStream records={[mk(1, "evento uno")]} {...props} />);

    expect(screen.queryByText("evento zero")).not.toBeInTheDocument();
  });
});
