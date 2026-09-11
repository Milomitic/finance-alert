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
    // ⚠️ `manual` e non `null`: da FA-046 il toast compare SOLO per un run che
    // l'utente ha chiesto. I test qui sotto parlano di ordine degli hook, non
    // di chi ha avviato lo scan, quindi la fixture deve essere visibile.
    trigger: "manual",
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

describe("RunProgressToast — un popup che si apre da solo interrompe", () => {
  /* Il toast compariva a OGNI scan, e la maggior parte degli scan non li
   * chiede nessuno: il cron ne lancia due al giorno piu uno all'avvio del
   * processo. Il risultato e un pannello che copre l'angolo in basso a destra
   * mentre si sta leggendo altro, per un lavoro che non riguarda chi guarda.
   *
   * ⚠️ La distinzione non e stata inventata per l'occasione: `ScanRun.trigger`
   * e `"cron" | "manual"` dal modello, ed e gia nel payload. Chiedere al dato
   * chi ha avviato il run e piu solido che tenere uno stato condiviso fra il
   * bottone e il toast, che vivono in due punti diversi dell'albero.
   */

  it("⚠️ uno scan del cron non apre niente: e il caso che questa voce chiude", () => {
    render(<RunProgressToast status={status({ trigger: "cron" })} labels={labels} />);
    expect(screen.queryByText(/Scansione in corso/)).toBeNull();
  });

  it("uno scan chiesto dall'utente si vede", () => {
    render(<RunProgressToast status={status({ trigger: "manual" })} labels={labels} />);
    expect(screen.getByText(/Scansione in corso/)).toBeTruthy();
  });

  it("⚠️ un trigger sconosciuto NON si vede: ignoto non e «l'ha chiesto lui»", () => {
    // Le righe vecchie possono avere `trigger` nullo. Il valore di riposo deve
    // essere il silenzio, altrimenti la correzione si spegne da sola su ogni
    // dato che non porta il campo.
    render(<RunProgressToast status={status({ trigger: null })} labels={labels} />);
    expect(screen.queryByText(/Scansione in corso/)).toBeNull();
  });

  it("nemmeno la finestra dopo il completamento apre un run del cron", () => {
    // Il toast resta 30s dopo la fine per far leggere l'esito. Se quel ramo
    // non guardasse il trigger, un cron notturno comparirebbe comunque.
    render(
      <RunProgressToast
        status={status({
          trigger: "cron",
          is_running: false,
          status: "success",
          completed_at: new Date().toISOString(),
        })}
        labels={labels}
      />,
    );
    expect(screen.queryByText(/Scansione completata/)).toBeNull();
  });

  it("il passaggio cron → manuale non rompe l'ordine degli hook", () => {
    // Stessa ragione del resto del file: e una transizione nascosto/visibile,
    // cioe esattamente dove il conteggio degli hook puo cambiare.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { rerender } = render(
      <RunProgressToast status={status({ trigger: "cron" })} labels={labels} />,
    );
    expect(screen.queryByText(/Scansione in corso/)).toBeNull();
    rerender(<RunProgressToast status={status({ trigger: "manual", last_run_id: 2 })} labels={labels} />);
    expect(screen.getByText(/Scansione in corso/)).toBeTruthy();
    const hookErrors = spy.mock.calls
      .map((c) => String(c[0]))
      .filter((m) => /order of Hooks|Rendered (more|fewer) hooks/.test(m));
    expect(hookErrors).toEqual([]);
    spy.mockRestore();
  });
});

import scanHeaderSource from "@/components/dashboard/ScanHeaderButton.tsx?raw";

describe("la copia non promette un pannello che non arrivera", () => {
  /* ⚠️ Controllo sulla SORGENTE. Il tooltip diceva «vedi il toast in basso a
   * destra» mentre un run era in corso, ed e falso da quando il pannello
   * compare solo per i run chiesti: il bottone e disabilitato perche qualcosa
   * gira, e quel qualcosa e quasi sempre il cron.
   *
   * E la forma «un rename fa mentire i commenti» applicata al testo che legge
   * l'utente — peggio di un commento sbagliato, che inganna solo chi mantiene.
   * Un test di comportamento non lo vede: la stringa viene resa correttamente,
   * e semplicemente non vera. */
  it("non manda a cercare un toast in basso a destra", () => {
    expect(scanHeaderSource).not.toMatch(/toast in basso a destra/i);
  });

  it("dice invece dove lo stato si trova davvero", () => {
    expect(scanHeaderSource).toMatch(/Diagnostica/);
  });
});
