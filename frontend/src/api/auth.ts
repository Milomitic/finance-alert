import { api } from "./client";
import type { Me } from "./types";

export const auth = {
  login: (username: string, password: string) =>
    api<{ username: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () =>
    api<void>("/api/auth/logout", {
      method: "POST",
      body: "{}",
    }),
  me: () => api<Me>("/api/auth/me"),
};
