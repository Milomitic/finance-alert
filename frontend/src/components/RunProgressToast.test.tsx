import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ScanStatusInfo } from "@/api/types";

import { setFirstPaintActive } from "@/lib/firstPaint";

import { RunProgressToast, type RunToastLabels } from "./RunProgressToast";

/* The toast is hidden far more often than it is visible: it returns null
 * whenever there is no run, the run was dismissed, or a finished run has aged
 * out of its post-completion window. Every hook it calls must therefore sit
 * ABOVE those returns, because React identifies hooks purely by call order.
 *
 * A `useIsPhone()` placed next to the JSX that read it broke exactly that. The
 * hidden render called seven hooks and the visible render called eight, so the
 * first time a scan started React threw mid-render — and with no error boundary
 * above the toast at the time, the whole app unmounted and the dashboard went
 * blank. The symptom ("the loading bar appears, then everything vanishes")
 * pointed at the bar rather than at the hook, and cost two wrong fixes.
 *
 * Nothing else catches this. It typechecks and it builds; only React's runtime
 * dispatcher notices, and only on the render where the branch actually flips.
 * So the test that matters is not "does it render" — it is "does it survive
 * TRANSITIONING between hidden and visible, in both directions".
 */

const labels: RunToastLabels = {
  headlines: {
    running: "Scansione in corso",
    stale: "Scansione bloccata",
    success: "Scansione completata",
    failed: "Scansione fallita",
  },
  phaseLabel: (phase) => (phase ? `fase ${phase}` : null),
  counters: [{ label: "Titoli", value: (s) => s.stocks_scanned }],
  baselineRatePerSec: () => 5,
};

function status(over: Partial<ScanStatusInfo> = {}): ScanStatusInfo {
  return {
    is_running: true,
    last_run_id: 1,
    trigger: null,
    status: "running",
    phase: "fetching",
    started_at: new Date().toISOString(),
    completed_at: null,
    last_progress_at: new Date().toISOString(),
    progress_done: 10,
    progress_total: 100,
    stocks_scanned: 10,
    stocks_skipped: 0,
    alerts_fired: 0,
    current_target: "AAPL",
    error_message: null,
    is_stale: false,
    seconds_since_last_progress: 0,
    ...over,
  };
}

describe("RunProgressToast — hook order across visibility changes", () => {
  it("survives hidden → visible (the transition that blanked the dashboard)", () => {
    // React reports a hook-order violation via console.error rather than by
    // throwing where the test can see it, so failures are asserted on the spy
    // as well as on the render itself.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    // Hidden: no run at all, so every early return is taken.
    const { rerender } = render(
      <RunProgressToast status={undefined} labels={labels} />,
    );
    expect(screen.queryByText(/Scansione in corso/)).toBeNull();

    // Visible: a scan starts. This is the render where the hook count changed.
    rerender(<RunProgressToast status={status()} labels={labels} />);
    expect(screen.getByText(/Scansione in corso/)).toBeTruthy();

    const hookErrors = spy.mock.calls
      .map((c) => String(c[0]))
      .filter((m) => /order of Hooks|Rendered (more|fewer) hooks/.test(m));
    expect(hookErrors).toEqual([]);
    spy.mockRestore();
  });

  it("survives visible → hidden (run finishes and ages out)", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { rerender } = render(
      <RunProgressToast status={status()} labels={labels} />,
    );
    expect(screen.getByText(/Scansione in corso/)).toBeTruthy();

    // Completed long enough ago that the post-completion window has closed —
    // the toast takes the `!isRunning && !inPostCompletionWindow` return.
    rerender(
      <RunProgressToast
        status={status({
          is_running: false,
          status: "success",
          completed_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
        })}
        labels={labels}
      />,
    );
    expect(screen.queryByText(/Scansione in corso/)).toBeNull();

    const hookErrors = spy.mock.calls
      .map((c) => String(c[0]))
      .filter((m) => /order of Hooks|Rendered (more|fewer) hooks/.test(m));
    expect(hookErrors).toEqual([]);
    spy.mockRestore();
  });
});

describe("RunProgressToast — one loading bar at a time", () => {
  afterEach(() => setFirstPaintActive(false));

  it("renders nothing while a first-paint gate covers the page", () => {
    /* A scan running when the dashboard loads used to paint its own bar in the
     * corner at the same moment the gate painted one in the middle: two
     * indicators for one wait. The toast defers — the gate is the one that
     * knows when the page is ready. */
    setFirstPaintActive(true);
    render(<RunProgressToast status={status()} labels={labels} />);
    expect(screen.queryByText(/Scansione in corso/)).toBeNull();
  });

  it("comes back once the gate opens", () => {
    setFirstPaintActive(true);
    render(<RunProgressToast status={status()} labels={labels} />);
    expect(screen.queryByText(/Scansione in corso/)).toBeNull();

    // No manual rerender: the store must push the change itself, or the toast
    // would stay hidden until something else happened to re-render it.
    act(() => setFirstPaintActive(false));
    expect(screen.getByText(/Scansione in corso/)).toBeTruthy();
  });
});
