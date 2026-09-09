import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const VITALS = ["largest-contentful-paint", "layout-shift", "event"] as const;
type VitalMetric = "LCP" | "INP" | "CLS";

function report(metric: VitalMetric, value: number, route: string): void {
  if (!Number.isFinite(value) || value < 0) return;
  const device = window.matchMedia("(max-width: 767px)").matches ? "mobile" : "desktop";
  const body = JSON.stringify({ metric, value, route, device });
  const blob = new Blob([body], { type: "application/json" });
  if (navigator.sendBeacon?.("/api/rum/web-vitals", blob)) return;
  void fetch("/api/rum/web-vitals", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => undefined);
}

/** Collects one bounded sample per vital and sends it when the route is left
 * or the page is hidden. Unsupported browsers simply produce no samples. */
export function WebVitalsReporter() {
  const { pathname } = useLocation();
  useEffect(() => {
    if (typeof PerformanceObserver === "undefined") return;
    const observers: PerformanceObserver[] = [];
    let lcp: number | null = null;
    let inp: number | null = null;
    let cls = 0;
    const observe = (type: (typeof VITALS)[number], callback: (entry: PerformanceEntry) => void) => {
      if (!(PerformanceObserver as typeof PerformanceObserver & { supportedEntryTypes?: string[] }).supportedEntryTypes?.includes(type)) return;
      const observer = new PerformanceObserver((list) => list.getEntries().forEach(callback));
      observer.observe({ type, buffered: true } as PerformanceObserverInit);
      observers.push(observer);
    };
    observe("largest-contentful-paint", (entry) => { lcp = entry.startTime; });
    observe("event", (entry) => {
      const duration = (entry as PerformanceEventTiming).duration;
      if (duration > 0) inp = Math.max(inp ?? 0, duration);
    });
    observe("layout-shift", (entry) => {
      const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number };
      if (!shift.hadRecentInput) cls += shift.value ?? 0;
    });
    const flush = () => {
      if (lcp != null) report("LCP", lcp, pathname);
      if (inp != null) report("INP", inp, pathname);
      report("CLS", cls, pathname);
    };
    window.addEventListener("pagehide", flush, { once: true });
    return () => {
      flush();
      observers.forEach((observer) => observer.disconnect());
      window.removeEventListener("pagehide", flush);
    };
  }, [pathname]);
  return null;
}
