import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import type { Alert } from "@/api/types";
import {
  NATURE_BG,
  NATURE_LABEL,
  NATURE_SHORT,
  TONE_BG,
  TONE_LABEL,
  getAlertKindMeta,
  getAlertMeta,
  signalNature,
  type AlertTone,
} from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* ─── AlertKindChip + AlertToneChip — shared across alert surfaces ────────
 *
 * Three places render alert metadata: the alerts page table
 * (`AlertsTable`), the stock-detail card (`StockAlertsHistoryCard`), and
 * the detail popup (`AlertDetailDialog`). Before this module the kind
 * label and the bullish/bearish indicator were rendered with different
 * inline JSX in each place — they drifted visually as we touched one
 * and not the others. Centralizing here means every alert surface
 * shows the exact same chips.
 *
 *   <AlertKindChip alert={a} />
 *     → tone-colored pill: icon + meta.label (e.g. "Golden Cross",
 *       "Price target ↑"). The background tone tells the user the
 *       semantic direction at a glance, before reading the label.
 *
 *   <AlertToneChip alert={a} />
 *     → outline pill: TrendingUp/Down + "Bullish" / "Bearish" word.
 *       Skips rendering for `tone === "neutral"` so the chip only
 *       appears when there's a directional read worth signaling.
 *
 * The two are typically rendered together: kind chip says WHAT, tone
 * chip says DIRECTION. Different shapes (filled vs outlined) so the
 * eye groups them as a pair instead of as two competing chips.
 */

interface Props {
  alert: Alert;
  /** Pass `size="sm"` for compact contexts (table cells, dense lists);
   *  default `size="md"` for the popup header and the stock-detail card. */
  size?: "sm" | "md";
  className?: string;
}

/** Le forme brevi delle tabelle dense (la home). */
interface PropsBreve extends Props {
  /** Etichetta ABBREVIATA a schermo, quella intera nel nome accessibile e nel
   *  suggerimento. */
  breve?: boolean;
}

/** Il testo di una pastiglia abbreviata: il breve si VEDE, l'intero si
 *  ASCOLTA. ⚠️ Non `aria-label` sullo span: su un elemento senza ruolo e'
 *  vietato dalla specifica e i lettori di schermo lo ignorano, quindi si
 *  sentirebbe «I» invece di «Inversione». */
export function Abbreviato({ breve, intero }: { breve: string; intero: string }) {
  if (breve === intero) return <>{intero}</>;
  return (
    <>
      <span aria-hidden>{breve}</span>
      <span className="sr-only">{intero}</span>
    </>
  );
}

export function AlertKindChip({ alert, size = "md", className, breve = false }: PropsBreve) {
  const meta = getAlertMeta(alert);
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded font-semibold whitespace-nowrap",
        size === "sm"
          ? "px-1.5 py-0.5 text-[0.7059rem]"
          : "px-2 py-1 text-sm",
        TONE_BG[meta.tone],
        className,
      )}
      title={meta.label}
    >
      <Icon className={size === "sm" ? "h-2.5 w-2.5" : "h-3.5 w-3.5"} />
      {breve ? <Abbreviato breve={meta.short} intero={meta.label} /> : meta.label}
    </span>
  );
}

/** La regola di un segnale quando non c'e' un `Alert` intero — una riga del
 *  magazzino degli esiti, un setup — con la STESSA pastiglia della home:
 *  icona, etichetta breve, fondo del verso (verde rialzista, rosso ribassista).
 *
 *  ⚠️ Il verso arriva a parte (`tone` "bull"/"bear") perche' il nome del
 *  detector da solo non lo porta: `getAlertKindMeta` rende sempre neutro. */
export function DetectorChip({
  detector, tone, size = "sm", breve = true, className,
}: {
  detector: string;
  tone: string | null | undefined;
  size?: "sm" | "md";
  breve?: boolean;
  className?: string;
}) {
  const meta = getAlertKindMeta(`signal:${detector}`);
  const Icon = meta.icon;
  const tono: AlertTone = tone === "bull" ? "bullish" : tone === "bear" ? "bearish" : "neutral";
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded font-semibold whitespace-nowrap",
        size === "sm" ? "px-1.5 py-0.5 text-[0.7059rem]" : "px-2 py-1 text-sm",
        TONE_BG[tono],
        className,
      )}
      title={tono === "neutral" ? meta.label : `${meta.label} · ${TONE_LABEL[tono].toLowerCase()}`}
    >
      <Icon className={cn("shrink-0", size === "sm" ? "h-2.5 w-2.5" : "h-3.5 w-3.5")} aria-hidden />
      {breve ? <Abbreviato breve={meta.short} intero={meta.label} /> : meta.label}
    </span>
  );
}

export function AlertToneChip({ alert, size = "md", className }: Props) {
  const meta = getAlertMeta(alert);
  // Neutral / warning tones don't get a directional badge — the kind
  // chip's color already communicates the semantic, and a "Neutro" /
  // "Allerta" word badge would just add noise.
  if (meta.tone !== "bullish" && meta.tone !== "bearish") {
    return null;
  }
  const ToneIcon = meta.tone === "bullish" ? TrendingUp : TrendingDown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border font-semibold uppercase tracking-wider whitespace-nowrap",
        size === "sm"
          ? "px-1 py-0.5 text-[0.6765rem]"
          : "px-2 py-0.5 text-xs",
        meta.tone === "bullish"
          ? "border-emerald-300/70 dark:border-emerald-700/60 text-emerald-800 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40"
          : "border-rose-300/70 dark:border-rose-700/60 text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40",
        className,
      )}
      title={`Tono semantico: ${TONE_LABEL[meta.tone].toLowerCase()}`}
    >
      <ToneIcon className={size === "sm" ? "h-2.5 w-2.5" : "h-3.5 w-3.5"} />
      {TONE_LABEL[meta.tone]}
    </span>
  );
}

/** Fallback for non-directional alerts where you still want to show
 *  *something* in a "tone" column. Renders a faint `—` for neutral
 *  alerts; the directional chip otherwise. Same component as
 *  `AlertToneChip` but with the placeholder for non-null layouts. */
export function AlertToneCell({ alert, size = "md" }: Props) {
  const meta = getAlertMeta(alert);
  if (meta.tone !== "bullish" && meta.tone !== "bearish") {
    return (
      <span
        className={cn(
          "text-muted-foreground",
          size === "sm" ? "text-[0.7059rem]" : "text-sm",
        )}
      >
        —
      </span>
    );
  }
  return <AlertToneChip alert={alert} size={size} />;
}

/* ─── AlertNatureChip + AlertNatureCell — continuation vs reversal ───────
 *
 * Signal alerts carry a "nature": is this a trend *continuation*
 * (Continuazione) or a *reversal* (Inversione)? The classification lives
 * in `signalNature(rule_kind, chain)` and is rendered identically in the
 * alerts table, the dashboard feed, and the detail popup so the three
 * surfaces never drift. Returns null for non-signal / unclassifiable
 * alerts (the chip variant), or a faint em dash (the cell variant).
 */
export function AlertNatureChip({ alert, size = "md", className, breve = false }: PropsBreve) {
  const nat = signalNature(
    alert.rule_kind,
    (alert.snapshot as { chain?: { label?: string }[] } | undefined)?.chain,
  );
  if (!nat) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded font-semibold whitespace-nowrap",
        size === "sm" ? "px-1.5 py-0.5 text-[0.7059rem]" : "px-2 py-0.5 text-xs",
        // L'iniziale in un quadrato: C e I hanno larghezze diverse, e una
        // colonna di lettere storte si legge peggio di una di pastiglie.
        breve && "min-w-5 justify-center",
        NATURE_BG[nat],
        className,
      )}
      title={`Natura del segnale: ${NATURE_LABEL[nat].toLowerCase()}`}
    >
      {breve ? <Abbreviato breve={NATURE_SHORT[nat]} intero={NATURE_LABEL[nat]} /> : NATURE_LABEL[nat]}
    </span>
  );
}

/** Table-cell variant: renders a faint `—` placeholder for
 *  non-signal alerts so the column stays aligned, the chip otherwise. */
export function AlertNatureCell({ alert, size = "md" }: Props) {
  const nat = signalNature(
    alert.rule_kind,
    (alert.snapshot as { chain?: { label?: string }[] } | undefined)?.chain,
  );
  if (!nat) {
    return (
      <span
        className={cn(
          "text-muted-foreground",
          size === "sm" ? "text-[0.7059rem]" : "text-sm",
        )}
      >
        —
      </span>
    );
  }
  return <AlertNatureChip alert={alert} size={size} />;
}

// Re-export Minus so consumers that want a placeholder icon don't have
// to import lucide separately. Tiny convenience.
export { Minus };
