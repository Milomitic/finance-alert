import { useEffect } from "react";
import { onCLS, onINP, onLCP } from "web-vitals";

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

// Core Web Vitals describe a document navigation, not each SPA route. Register
// once, including under StrictMode; do not replay buffered entries on every route.
let initialized = false;

export function WebVitalsReporter() {
  useEffect(() => {
    if (initialized) return;
    initialized = true;
    const entryRoute = window.location.pathname;
    const sent = new Set<string>();
    const send = (metric: { id: string; name: VitalMetric; value: number }) => {
      if (sent.has(metric.id)) return;
      sent.add(metric.id);
      report(metric.name, metric.value, entryRoute);
    };
    // The library implements CLS session windows, INP interaction grouping,
    // visibility handling and bfcache lifecycle, unlike raw observer maxima.
    onCLS(send);
    onINP(send);
    onLCP(send);
  }, []);
  return null;
}
