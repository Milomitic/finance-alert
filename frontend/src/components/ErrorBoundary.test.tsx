import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

/* What these assert is containment, not presentation.
 *
 * React unmounts the entire tree when a render throws with no boundary above
 * it. That turned a hook-order bug in a corner toast into a blank dashboard,
 * twice. The boundary's job is to make the blast radius one subtree.
 */

function Boom(): React.ReactElement {
  throw new Error("crash di prova");
}

/** React logs caught errors to console.error; silence it so the suite output
 *  stays readable, and so a real unexpected error still stands out. */
function quiet() {
  return vi.spyOn(console, "error").mockImplementation(() => {});
}

describe("ErrorBoundary", () => {
  it("keeps siblings alive when a child throws", () => {
    const spy = quiet();
    render(
      <div>
        <ErrorBoundary fallback={null}>
          <Boom />
        </ErrorBoundary>
        <p>la dashboard è ancora qui</p>
      </div>,
    );
    expect(screen.getByText("la dashboard è ancora qui")).toBeTruthy();
    spy.mockRestore();
  });

  it("renders nothing for fallback={null} — chrome should vanish, not shout", () => {
    const spy = quiet();
    const { container } = render(
      <ErrorBoundary fallback={null}>
        <Boom />
      </ErrorBoundary>,
    );
    expect(container.textContent).toBe("");
    spy.mockRestore();
  });

  it("shows the diagnostic panel when no fallback is given", () => {
    const spy = quiet();
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    // The message must reach the screen: the whole point is that a crash is
    // visible as a crash rather than as an empty page. `getAllBy` because it
    // legitimately appears twice — once in the summary line, once inside the
    // stack trace details.
    expect(screen.getByText(/Errore di rendering/)).toBeTruthy();
    expect(screen.getAllByText(/crash di prova/).length).toBeGreaterThan(0);
    spy.mockRestore();
  });

  it("renders children untouched when nothing throws", () => {
    render(
      <ErrorBoundary fallback={null}>
        <p>contenuto normale</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("contenuto normale")).toBeTruthy();
  });
});
