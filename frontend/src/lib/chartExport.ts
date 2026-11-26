import type { IChartApi } from "lightweight-charts";

/** Download the chart as a PNG. lightweight-charts renders to canvas, so
 *  `takeScreenshot()` captures the candles / series / markers / axes (the
 *  HTML legend overlay is not part of the canvas). */
export function downloadChartPng(chart: IChartApi | null, filename: string): void {
  if (!chart) return;
  const canvas = conFondo(chart.takeScreenshot());
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

/** Il grafico ha fondo trasparente: aperto in un visualizzatore o incollato
 *  in una chat dell'altro tema, gli assi sparivano (FA-175, B-64). Lo si
 *  disegna sul colore della scheda del tema attivo. */
export function conFondo(sorgente: HTMLCanvasElement): HTMLCanvasElement {
  const tela = document.createElement("canvas");
  tela.width = sorgente.width;
  tela.height = sorgente.height;
  const ctx = tela.getContext("2d");
  if (!ctx) return sorgente;
  const card = getComputedStyle(document.documentElement).getPropertyValue("--card").trim();
  ctx.fillStyle = card ? `hsl(${card})` : "#ffffff";
  ctx.fillRect(0, 0, tela.width, tela.height);
  ctx.drawImage(sorgente, 0, 0);
  return tela;
}
