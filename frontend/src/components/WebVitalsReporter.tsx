import { useEffect } from "react";
import { onCLS, onINP, onLCP } from "web-vitals";

import { report, type VitalMetric } from "@/lib/rum";

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
