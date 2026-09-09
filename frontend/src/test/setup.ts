// Component-test setup (loaded via vite.config `setupFiles`):
//  - registers @testing-library/jest-dom matchers (toBeInTheDocument, …);
//  - unmounts rendered trees between tests. Auto-cleanup only self-registers
//    when a global `afterEach` exists (i.e. with `globals: true`); we keep
//    explicit vitest imports, so wire cleanup by hand.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/* ⚠️ A WORKING `localStorage`, because neither jsdom's nor Node's is usable
 * here.
 *
 * Node 25 ships its own global `localStorage` (the source of the
 * "`--localstorage-file` was provided without a valid path" warning on every
 * run) and it SHADOWS jsdom's — `globalThis.localStorage === window.localStorage`
 * and neither has a callable `setItem`, `getItem` or `clear`.
 *
 * That is worse than a missing feature: every storage-backed module in this
 * app wraps its access in try/catch, correctly, because a private window or a
 * browser blocking site data can throw. So the broken object is swallowed, the
 * code takes its "storage unavailable" path, and a test asserting that a
 * preference PERSISTS passes without ever having stored anything — the "a test
 * can be true of nothing" failure CLAUDE.md records in two other forms.
 *
 * A plain in-memory Map restores real semantics. It is per-process, and the
 * `afterEach` below clears it so tests cannot leak state into each other. */
class MemoryStorage implements Storage {
  private map = new Map<string, string>();
  get length() { return this.map.size; }
  clear() { this.map.clear(); }
  getItem(k: string) { return this.map.has(k) ? this.map.get(k)! : null; }
  key(i: number) { return Array.from(this.map.keys())[i] ?? null; }
  removeItem(k: string) { this.map.delete(k); }
  setItem(k: string, v: string) { this.map.set(k, String(v)); }
}

const memory = new MemoryStorage();
for (const target of [globalThis, window]) {
  Object.defineProperty(target, "localStorage", {
    value: memory, configurable: true, writable: true,
  });
}

afterEach(() => {
  cleanup();
  // Storage is global and survives a test file's teardown otherwise, so a
  // preference written by one test would be read as a "remembered" value by
  // the next — a passing test built on another test's leftovers.
  memory.clear();
});
