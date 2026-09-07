import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PriceAlert } from "@/api/types";

import { PriceAlertDialog } from "./PriceAlertDialog";

/* The dialog was already built for editing — `editing` pre-fills the fields,
 * the title switches to "Modifica", the button to "Salva" — and nothing ever
 * passed it. Half a feature, sitting unreachable.
 *
 * Delete is the part that needed care rather than wiring. It destroys a row
 * the user wrote by hand, with no undo and no trash, so it asks first. The
 * confirmation is IN PLACE — the button becomes "Confermi?" — rather than a
 * second modal on top of the first: a dialog stacked on a dialog is heavier
 * than the decision deserves, and the two-step in the same spot keeps the
 * pointer where it already is.
 */

const alert: PriceAlert = {
  id: 42,
  stock_id: 7,
  target_price: 189.5,
  direction: "above",
  enabled: true,
  note: "resistenza",
  triggered_at: null,
  created_at: "2026-09-01T10:00:00Z",
};

function open(props: Partial<React.ComponentProps<typeof PriceAlertDialog>> = {}) {
  return render(
    <PriceAlertDialog
      open
      editing={alert}
      onClose={vi.fn()}
      onSubmit={vi.fn()}
      onDelete={vi.fn()}
      {...props}
    />,
  );
}

describe("deleting asks first, because it cannot be undone", () => {
  it("does not delete on the first click", async () => {
    const onDelete = vi.fn();
    open({ onDelete });

    await userEvent.click(screen.getByRole("button", { name: /elimina/i }));

    expect(onDelete).not.toHaveBeenCalled();
  });

  it("asks for confirmation in place", async () => {
    open();
    await userEvent.click(screen.getByRole("button", { name: /elimina/i }));
    expect(screen.getByRole("button", { name: /confermi/i })).toBeInTheDocument();
  });

  it("deletes on the second click", async () => {
    const onDelete = vi.fn();
    open({ onDelete });

    await userEvent.click(screen.getByRole("button", { name: /elimina/i }));
    await userEvent.click(screen.getByRole("button", { name: /confermi/i }));

    expect(onDelete).toHaveBeenCalledWith(42);
  });

  it("offers no delete when creating — there is nothing to destroy yet", () => {
    open({ editing: null });
    expect(screen.queryByRole("button", { name: /elimina/i })).not.toBeInTheDocument();
  });

  it("offers no delete when the caller cannot handle one", () => {
    open({ onDelete: undefined });
    expect(screen.queryByRole("button", { name: /elimina/i })).not.toBeInTheDocument();
  });
});

describe("the editor still edits", () => {
  it("pre-fills from the alert being edited", () => {
    open();
    expect(screen.getByLabelText(/target price/i)).toHaveValue(189.5);
    expect(screen.getByDisplayValue("resistenza")).toBeInTheDocument();
  });

  it("submits the edited values", async () => {
    const onSubmit = vi.fn();
    open({ onSubmit });

    const price = screen.getByLabelText(/target price/i);
    await userEvent.clear(price);
    await userEvent.type(price, "200");
    await userEvent.click(screen.getByRole("button", { name: /salva/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ target_price: 200, direction: "above" }),
    );
  });

  it("refuses a non-positive price instead of sending it", async () => {
    const onSubmit = vi.fn();
    open({ onSubmit });

    const price = screen.getByLabelText(/target price/i);
    await userEvent.clear(price);
    await userEvent.type(price, "0");
    await userEvent.click(screen.getByRole("button", { name: /salva/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/prezzo positivo/i)).toBeInTheDocument();
  });
});
