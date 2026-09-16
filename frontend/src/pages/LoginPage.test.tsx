import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import LoginPage from "./LoginPage";

const authState = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  isPending: false,
  me: null as { username: string } | null,
}));
vi.mock("@/hooks/useAuth", () => ({
  useMe: () => ({ data: authState.me }),
  useLogin: () => authState,
}));

function showLogin() {
  return render(<MemoryRouter initialEntries={["/login"]}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/" element={<p>Area di analisi</p>} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  authState.mutateAsync.mockReset();
  authState.isPending = false;
  authState.me = null;
});

describe("login interactions", () => {
  it("focuses the missing field and associates its error without requesting login", async () => {
    const user = userEvent.setup();
    showLogin();
    await user.click(screen.getByRole("button", { name: "Accedi" }));
    expect(screen.getByLabelText("Username")).toHaveFocus();
    expect(screen.getByLabelText("Username")).toHaveAccessibleDescription("Inserisci lo username");
    await user.type(screen.getByLabelText("Username"), "demo");
    await user.click(screen.getByRole("button", { name: "Accedi" }));
    expect(screen.getByLabelText("Password", { exact: true })).toHaveFocus();
    expect(screen.getByLabelText("Password", { exact: true })).toHaveAccessibleDescription("Inserisci la password");
    expect(authState.mutateAsync).not.toHaveBeenCalled();
  });

  it("reveals and hides the password without submitting or changing its value", async () => {
    const user = userEvent.setup();
    showLogin();
    const password = screen.getByLabelText("Password", { exact: true });
    await user.type(password, "local-test-password");
    await user.click(screen.getByRole("button", { name: "Mostra password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("local-test-password");
    await user.click(screen.getByRole("button", { name: "Nascondi password" }));
    expect(password).toHaveAttribute("type", "password");
    expect(authState.mutateAsync).not.toHaveBeenCalled();
  });

  it.each([
    [401, "Credenziali non valide"],
    [429, "Troppi tentativi"],
    [500, "Accesso non riuscito"],
  ])("keeps the form usable and announces an HTTP %s failure", async (status, message) => {
    const user = userEvent.setup();
    authState.mutateAsync.mockRejectedValue(new ApiError(status, "private server detail"));
    showLogin();
    await user.type(screen.getByLabelText("Username"), "demo");
    await user.type(screen.getByLabelText("Password", { exact: true }), "local-test-password");
    await user.click(screen.getByRole("button", { name: "Accedi" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("alert")).not.toHaveTextContent("private server detail");
    expect(screen.queryByText("Area di analisi")).not.toBeInTheDocument();
  });

  it("submits unchanged credentials and navigates after success", async () => {
    const user = userEvent.setup();
    authState.mutateAsync.mockResolvedValue({ username: "demo" });
    showLogin();
    await user.type(screen.getByLabelText("Username"), "demo");
    await user.type(screen.getByLabelText("Password", { exact: true }), "with spaces ");
    await user.keyboard("{Enter}");
    await screen.findByText("Area di analisi");
    expect(authState.mutateAsync).toHaveBeenCalledWith({ username: "demo", password: "with spaces " });
  });

  it("blocks a second submission while the request is pending", async () => {
    authState.isPending = true;
    showLogin();
    const button = screen.getByRole("button", { name: "Accesso in corso…" });
    expect(button).toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    expect(authState.mutateAsync).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("takes an existing session directly to the app", async () => {
    authState.me = { username: "demo" };
    showLogin();
    await screen.findByText("Area di analisi");
    expect(authState.mutateAsync).not.toHaveBeenCalled();
  });
});
