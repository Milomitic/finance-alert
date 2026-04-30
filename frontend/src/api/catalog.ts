import { api } from "./client";
import type { CatalogStatus } from "./types";

export const catalog = {
  refresh: (indexCode?: string) =>
    api<{ accepted: boolean }>("/api/catalog/refresh", {
      method: "POST",
      body: JSON.stringify(indexCode ? { index_code: indexCode } : {}),
    }),
  status: () => api<CatalogStatus>("/api/catalog/status"),
};
