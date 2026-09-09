import { StrictMode } from "react";
import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const observers = vi.hoisted(() => ({ onCLS: vi.fn(), onINP: vi.fn(), onLCP: vi.fn() }));
vi.mock("web-vitals", () => observers);
import { WebVitalsReporter } from "./WebVitalsReporter";

it("registers document observers once despite StrictMode and route rerenders", () => {
  Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn(() => ({ matches: false })) });
  const beacon = vi.fn().mockReturnValue(true);
  Object.defineProperty(navigator, "sendBeacon", { configurable: true, value: beacon });
  const view = render(<StrictMode><WebVitalsReporter /></StrictMode>);
  view.rerender(<StrictMode><WebVitalsReporter /></StrictMode>);
  expect(observers.onLCP).toHaveBeenCalledTimes(1);
  expect(observers.onINP).toHaveBeenCalledTimes(1);
  expect(observers.onCLS).toHaveBeenCalledTimes(1);
  const report = observers.onLCP.mock.calls[0][0];
  report({ id: "document-1", name: "LCP", value: 1200 });
  report({ id: "document-1", name: "LCP", value: 1300 });
  expect(beacon).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(beacon).toHaveBeenCalledTimes(1);
});
