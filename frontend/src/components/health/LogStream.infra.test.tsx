import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { StreamedLog } from "@/hooks/usePlatformHealthStream";

import LogStream from "./LogStream";

/* Infra logs bring a failure the app's own stream never had.
 *
 * The SSE stream reads an in-process ring buffer: it cannot be unreachable, so
 * "no rows" has exactly one meaning. Loki is over the network, so "no rows"
 * splits into two states that render identically and want opposite reactions —
 * the component was quiet, or the log pipeline is down. A panel that shows one
 * calm empty box for both is a monitor reporting good news about its own
 * blindness.
 *
 * Alertmanager is the concrete case, measured while building this: its
 * selector returned nothing over six hours and plenty over thirty days. It had
 * been silent for nine days, which for an alert router is the desired state.
 */

const mk = (seq: number, message: string, level = "ERROR"): StreamedLog => ({
  seq,
  ts: 1_757_000_000 + seq,
  level,
  module: "argocd-server-1",
  function: "argocd-server",
  line: 0,
  message,
  exception: null,
});

const baseOrigin = {
  options: [
    { key: "argocd", label: "ArgoCD", note: "sincronizzazioni" },
    { key: "postgres", label: "PostgreSQL", note: "connessioni" },
  ],
  value: "app",
  onChange: vi.fn(),
  windowMinutes: 60,
  onWindowChange: vi.fn(),
  reachable: null as boolean | null,
  loading: false,
};

const props = {
  paused: false,
  onTogglePause: vi.fn(),
  onClear: vi.fn(),
};

describe("quiet is not unreachable", () => {
  it("says Loki did not answer when it did not", () => {
    render(
      <LogStream
        records={[]}
        {...props}
        origin={{ ...baseOrigin, value: "argocd", reachable: false }}
      />,
    );

    expect(screen.getByText(/Loki non ha risposto/i)).toBeInTheDocument();
  });

  it("does NOT claim the component was quiet when the query failed", () => {
    render(
      <LogStream
        records={[]}
        {...props}
        origin={{ ...baseOrigin, value: "argocd", reachable: false }}
      />,
    );

    expect(screen.queryByText(/silenzioso, non assente/i)).not.toBeInTheDocument();
  });

  it("says the component was quiet when Loki answered with nothing", () => {
    render(
      <LogStream
        records={[]}
        {...props}
        origin={{ ...baseOrigin, value: "argocd", reachable: true }}
      />,
    );

    expect(screen.getByText(/silenzioso, non assente/i)).toBeInTheDocument();
    expect(screen.queryByText(/Loki non ha risposto/i)).not.toBeInTheDocument();
  });

  it("does not accuse Loki while the first request is still in flight", () => {
    // `reachable: null` is "we have not heard yet", which is neither of the
    // two answers. Rendering it as a failure would flash a red banner on every
    // switch between sources.
    render(
      <LogStream
        records={[]}
        {...props}
        origin={{ ...baseOrigin, value: "argocd", reachable: null, loading: true }}
      />,
    );

    expect(screen.queryByText(/Loki non ha risposto/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Interrogazione in corso/i)).toBeInTheDocument();
  });

  it("keeps the app stream's own empty message when the origin is the app", () => {
    render(<LogStream records={[]} {...props} origin={baseOrigin} />);

    expect(screen.getByText(/Nessun log corrisponde ai filtri/i)).toBeInTheDocument();
    expect(screen.queryByText(/Loki non ha risposto/i)).not.toBeInTheDocument();
  });
});

describe("an infra source opens at every level", () => {
  it("shows an INFO row that the WARNING+ default would have hidden", () => {
    // The backend's level parsing is a heuristic: components share no log
    // format and anything unclassifiable falls back to INFO. If the panel
    // opened at the usual WARNING+ threshold, an unclassified error would be
    // invisible and the source would look quiet.
    render(
      <LogStream
        records={[mk(1, "connesso a 10.42.0.1:5432", "INFO")]}
        {...props}
        origin={{ ...baseOrigin, value: "postgres", reachable: true }}
      />,
    );

    expect(screen.getByText(/connesso a 10.42.0.1:5432/)).toBeInTheDocument();
  });

  it("still hides INFO on the app stream, where levels are real", () => {
    render(
      <LogStream records={[mk(1, "riga informativa", "INFO")]} {...props} origin={baseOrigin} />,
    );

    expect(screen.queryByText(/riga informativa/)).not.toBeInTheDocument();
  });
});

describe("the picker", () => {
  it("offers the app plus every source the backend published", () => {
    render(<LogStream records={[]} {...props} origin={baseOrigin} />);

    expect(screen.getByRole("option", { name: "App (live)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "ArgoCD" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "PostgreSQL" })).toBeInTheDocument();
  });

  it("offers a time window only when looking at infra", () => {
    // The app stream is a live buffer; a "last 24 hours" control there would
    // promise a query it does not make.
    const { rerender } = render(
      <LogStream records={[]} {...props} origin={baseOrigin} />,
    );
    expect(screen.queryByTitle(/Finestra temporale/i)).not.toBeInTheDocument();

    rerender(
      <LogStream
        records={[]}
        {...props}
        origin={{ ...baseOrigin, value: "argocd", reachable: true }}
      />,
    );
    expect(screen.getByTitle(/Finestra temporale/i)).toBeInTheDocument();
  });

  it("names the component in the heading so the panel is never ambiguous", () => {
    render(
      <LogStream
        records={[]}
        {...props}
        origin={{ ...baseOrigin, value: "postgres", reachable: true }}
      />,
    );

    expect(screen.getByRole("heading", { name: /PostgreSQL/ })).toBeInTheDocument();
  });
});
