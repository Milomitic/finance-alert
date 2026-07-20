import type { IChartApi } from "lightweight-charts";

/** Download the chart as a PNG. lightweight-charts renders to canvas, so
 *  `takeScreenshot()` captures the candles / series / markers / axes (the
 *  HTML legend overlay is not part of the canvas). */
export function downloadChartPng(chart: IChartApi | null, filename: string): void {
  if (!chart) return;
  const canvas = chart.takeScreenshot();
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, "image/png");
}
