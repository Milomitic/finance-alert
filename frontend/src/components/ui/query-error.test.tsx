import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QueryError } from "@/components/ui/query-error";

describe("QueryError", () => {
  it("renders the message inside a role=alert region", () => {
    render(<QueryError message="dei segnali" />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Errore nel caricamento dei segnali.",
    );
  });

  it("defaults the message when none is given", () => {
    render(<QueryError />);
    expect(screen.getByRole("alert")).toHaveTextContent("Errore nel caricamento dei dati.");
  });

  it("shows a retry button only when onRetry is provided, and calls it", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<QueryError />);
    expect(screen.queryByRole("button")).toBeNull();

    rerender(<QueryError onRetry={onRetry} />);
    expect(screen.getByRole("button")).toHaveTextContent(/riprova/i);
    await userEvent.click(screen.getByRole("button"));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("disables the retry button while a retry is in flight", () => {
    render(<QueryError onRetry={() => {}} isRetrying />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
