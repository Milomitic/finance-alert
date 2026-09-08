import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { DrawingToolbar, type DrawingMode } from "./DrawingToolbar";

/* A component DEFINED INSIDE another component's body is a brand-new type on
 * every render. React compares types to decide reconcile-vs-remount, so it
 * cannot tell `Tool` from render N apart from `Tool` from render N+1: it
 * unmounts the old subtree and mounts a new one. The DOM node the user was
 * touching is destroyed and replaced by an identical-looking one.
 *
 * That is invisible to a mouse — the pixels are the same. It is not invisible
 * to a keyboard: focus lives on a NODE, and the node is gone, so the browser
 * drops focus to <body>. Tab to a tool, press Enter, and you are back at the
 * top of the page with the toolbar behind you.
 *
 * `react-hooks/static-components` reports this, and it now runs in the gated
 * config (eslint.hooks.config.js) so it cannot come back. This test exists
 * because a lint rule says "don't", and does not say what it costs.
 */

function Harness() {
  // The toolbar is controlled, so without a parent that actually flips `mode`
  // there is no re-render and the bug cannot appear. The state lives in
  // StockDetailPage in the real app.
  const [mode, setMode] = useState<DrawingMode>("none");
  return <DrawingToolbar mode={mode} onSetMode={setMode} onClearAll={() => {}} />;
}

describe("activating a tool does not throw the keyboard user off the toolbar", () => {
  it("keeps focus on the tool that was just pressed", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.tab();
    expect(document.activeElement).toHaveAccessibleName("H-line");

    await user.keyboard("{Enter}");

    // Same button, now active. If the toolbar rebuilt its component types,
    // this is <body>.
    expect(document.activeElement).toHaveAccessibleName("H-line");
  });

  it("still toggles the mode it is told to toggle", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // aria-pressed is the real signal, not a test-only hook: these are
    // toggles, and until now only the button's FILL said which one was armed.
    const trend = () => screen.getByRole("button", { name: "Linea" });
    expect(trend()).toHaveAttribute("aria-pressed", "false");

    await user.click(trend());
    expect(trend()).toHaveAttribute("aria-pressed", "true");

    // Pressing the armed tool disarms it rather than re-arming it.
    await user.click(trend());
    expect(trend()).toHaveAttribute("aria-pressed", "false");
  });
});
