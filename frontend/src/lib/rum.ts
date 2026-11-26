/* L'invio delle misure del browser al RUM (`/api/rum/web-vitals`).
 *
 * Oltre alle Web Vitals, due misure della home (FA-179, fase D):
 *   DATI_FRESCHI  dal caricamento della pagina ai dati freschi della home;
 *   DATI_RITORNO  dal ritorno sulla pagina ai dati di nuovo freschi. */

export type VitalMetric = "LCP" | "INP" | "CLS" | "DATI_FRESCHI" | "DATI_RITORNO";

export function report(metric: VitalMetric, value: number, route: string): void {
  if (!Number.isFinite(value) || value < 0) return;
  const device = window.matchMedia?.("(max-width: 767px)").matches ? "mobile" : "desktop";
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
