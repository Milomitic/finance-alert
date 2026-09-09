import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { axeViolations, describeViolations } from "@/test/axe";

import Layout from "./Layout";

/* The shared shell renders on every single route, so a structural defect here
 * is a defect on sixteen pages at once. Four were found by hand on 2026-09-09
 * (document language, missing skip link, an icon-only logout button with no
 * name, one title for every page). This is the automated floor that stops the
 * next four from arriving unnoticed.
 *
 * ⚠️ Green here is NOT "accessible". jsdom loads no stylesheet, so contrast,
 * touch targets and anything decided by display:none are all invisible to it —
 * see the note in src/test/axe.ts. Two of the four defects above could not have
 * been caught by this file. It covers the structural half, which is the half a
 * tool is actually good at.
 */

vi.mock("@/hooks/useAuth", () => ({
  useMe: () => ({ data: { username: "tester" } }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function renderShell(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/*" element={<Layout />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("il guscio condiviso non ha violazioni strutturali", () => {
  it("sulla rotta iniziale", async () => {
    const { container } = renderShell("/");

    const violations = await axeViolations(container);

    expect(violations, describeViolations(violations)).toHaveLength(0);
  }, 20_000);

  it("ogni controllo interattivo ha un nome accessibile", async () => {
    // The rule that would have caught the logout button IF jsdom applied CSS.
    // It still earns its place: it catches an icon-only button that never had
    // a label at all, which is the more common way this defect arrives.
    const { container } = renderShell("/positions");

    const violations = await axeViolations(container, {
      runOnly: { type: "rule", values: ["button-name", "link-name", "aria-command-name"] },
    });

    expect(violations, describeViolations(violations)).toHaveLength(0);
  }, 20_000);

  it("l'ARIA dichiarata è valida e non orfana", async () => {
    // aria-* attributes pointing at ids that do not exist, or roles used
    // without their required parent, are silent: the page looks correct and
    // the screen reader reads something else.
    const { container } = renderShell("/");

    const violations = await axeViolations(container, {
      runOnly: {
        type: "rule",
        values: [
          "aria-valid-attr",
          "aria-valid-attr-value",
          "aria-required-attr",
          "aria-required-parent",
          "aria-required-children",
          "aria-allowed-attr",
        ],
      },
    });

    expect(violations, describeViolations(violations)).toHaveLength(0);
  }, 20_000);

  it("non esistono id duplicati", async () => {
    // The skip link points at #contenuto. A second element with that id would
    // send the reader somewhere arbitrary, and nothing on screen would differ.
    const { container } = renderShell("/");

    const violations = await axeViolations(container, {
      runOnly: { type: "rule", values: ["duplicate-id", "duplicate-id-aria"] },
    });

    expect(violations, describeViolations(violations)).toHaveLength(0);
  }, 20_000);
});

describe("il rilevatore funziona davvero", () => {
  it("segnala un pulsante senza nome, così un verde significa qualcosa", async () => {
    // Without this, every assertion above could be passing because axe is
    // misconfigured and reports nothing. The same reason CLAUDE.md insists a
    // regression test must be seen to fail.
    const { container } = render(
      <div>
        <button type="button" />
      </div>,
    );

    const violations = await axeViolations(container, {
      runOnly: { type: "rule", values: ["button-name"] },
    });

    expect(violations).toHaveLength(1);
    expect(violations[0].id).toBe("button-name");
  }, 20_000);
});
