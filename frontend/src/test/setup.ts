// Component-test setup (loaded via vite.config `setupFiles`):
//  - registers @testing-library/jest-dom matchers (toBeInTheDocument, …);
//  - unmounts rendered trees between tests. Auto-cleanup only self-registers
//    when a global `afterEach` exists (i.e. with `globals: true`); we keep
//    explicit vitest imports, so wire cleanup by hand.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
