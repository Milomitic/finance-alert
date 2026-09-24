import {
  Archive, ArchiveRestore, ArrowDown, ArrowUp, ArrowUpDown, Check, Clock, Hourglass,
  Target, Unplug, X,
} from "lucide-react";
import { type MouseEvent, useState } from "react";
import { Link } from "react-router-dom";

import type { Alert, PlanBrief } from "@/api/types";
import { AlertKindChip, AlertNatureCell } from "@/components/AlertChips";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Checkbox } from "@/components/ui/checkbox";
import { ColumnVisibilityMenu } from "@/components/ui/column-visibility-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TableSearchInput } from "@/components/ui/table-search-input";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useSignalCalibration } from "@/hooks/useSignalCalibration";
import {
  alertDelayDays,
  barraDiversaDalSegnale,
  formatShortDate,
  giornoDelSegnale,
  isAlertDelayed,
} from "@/lib/alertDates";
import { FORZA_TOOLTIP, PROBABILITA_TOOLTIP, isSignalKind, snapshotForza, snapshotProbabilita } from "@/lib/alertMeta";
import { ESITO_META, formatR, raccontaPiano, stopTroppoStretto } from "@/lib/planOutcome";
import { HintAnchor, HintUnderline } from "@/components/ui/info-hint";
import { cn } from "@/lib/utils";

/** Toggleable columns for the non-embedded alerts table.
 *  Checkbox + Titolo are always-on (identity + selection).
 *  The old single "Confidenza" column was split into "Forza" (pattern
 *  strength, tone-colored) + "Prob." (historical hit-rate, neutral). */
/* ⚠️ «Tono» e «Catena» tolte il 2026-09-22 (richiesta dell'utente). Il tono
 * lo porta gia' la pastiglia della Regola, nel colore e nell'icona — la
 * stessa ragione per cui era gia' fuori dalla scheda del titolo — e la catena
 * sta intera nel dettaglio del segnale, dove c'e' lo spazio per leggerla. Una
 * preferenza salvata che le nascondeva resta nel localStorage e non fa niente. */
/** Che cosa dice quella data, in una riga: sta sull'intestazione e nel
 *  popover, quindi va scritta una volta sola. */
const HINT_SEGNALE =
  "Il giorno in cui il segnale è comparso. È la data su cui poggiano il prezzo "
  + "d'ingresso e il piano; se la barra di mercato è precedente, l'orologio lo segnala.";

const ALERTS_COLS = [
  // ⚠️ UNA data sola, e l'id resta `data_segnale` perche' le preferenze
  // salvate dell'utente sono indicizzate su quello. La colonna «Rilevato» —
  // che mostrava `triggered_at`, cioe' l'ULTIMA REVISIONE — non c'e' piu':
  // erano due date accanto, nessuna delle quali era quella su cui poggia il
  // piano. Vedi `lib/alertDates.giornoDelSegnale`.
  { id: "data_segnale", label: "Segnale" },
  { id: "regola",      label: "Regola" },
  { id: "natura",      label: "Natura" },
  { id: "orizzonte",   label: "Orizzonte" },
  { id: "forza",       label: "Forza" },
  { id: "probabilita", label: "Prob." },
  // ⚠️ «Direzione» e non «Esito», e l'id resta `esito` perche' le preferenze
  // salvate dell'utente sono indicizzate su quello. Il nome vecchio era
  // ambiguo proprio dove conta: quella colonna dice se la DIREZIONE ha pagato
  // a orizzonte fisso, e accanto ora c'e' «Piano», che dice se il piano si
  // sarebbe chiuso in guadagno. Due domande diverse, due nomi.
  { id: "esito",       label: "Direzione" },
  { id: "piano",       label: "Piano" },
] as const;

/** Horizon label + tone classes (plain string-literal Record so Tailwind's
 *  purger keeps the classes — see CLAUDE.md tone-class rule). */
const HORIZON_META: Record<string, { label: string; cls: string }> = {
  short:  { label: "Breve", cls: "bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300" },
  medium: { label: "Medio", cls: "bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300" },
  long:   { label: "Lungo", cls: "bg-teal-100 text-teal-700 dark:bg-teal-950/50 dark:text-teal-300" },
};

interface Props {
  alerts: Alert[];
  selectedIds: Set<number>;
  onSelect: (id: number, selected: boolean) => void;
  onSelectAll: (selected: boolean) => void;
  onRowClick: (alert: Alert) => void;
  /** Inline ticker/name search folded into the Ticker column header.
   *  Filters server-side via the AlertListParams `q` param. */
  q: string;
  onQueryChange: (v: string) => void;
  /** Embedded mode for surfaces that show the alerts of a single
   *  stock (e.g. the StockAlertsHistoryCard on the stock-detail page).
   *  When true:
   *    - The select-all + per-row checkboxes are hidden (no bulk
   *      operations on a per-stock view).
   *    - The Ticker column header omits the search input and renders
   *      a plain "Ticker" label.
   *    - The Ticker + Nome columns are dropped entirely — they would
   *      repeat the same value on every row in this mode.
   *  Default false (the canonical alerts-page layout). */
  embedded?: boolean;
  /** Active sort column key (non-embedded only). */
  sortBy?: string;
  /** Active sort direction (non-embedded only). */
  sortDir?: "asc" | "desc";
  /** Called when a sortable header is clicked (non-embedded only). */
  onSort?: (col: string) => void;
  /** Per-row archive/unarchive action (non-embedded only). When provided, a
   *  hover-visible icon appears at the row end; clicking it toggles the
   *  archived state without opening the detail dialog. */
  onArchiveToggle?: (alert: Alert) => void;
}

/** Le intestazioni della tabella, piu' piccole del corpo (2026-09-22,
 *  richiesta dell'utente): erano a 1rem, piu' grandi delle righe che
 *  nominano. Maiuscoletto spaziato, come le intestazioni degli Esiti.
 *  `normal-case` sui bottoni non serve: l'`uppercase` si applica al testo. */
const INTESTAZIONE = "text-[0.7059rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground";

/** Small local sortable column header — same pattern as StockBrowserTable
 *  and BreadthMatrixTable but scoped to AlertsTable so we avoid an
 *  unrelated cross-component refactor. */
function SortableHeader({
  column,
  label,
  align = "left",
  hint,
  sortBy,
  sortDir,
  onSort,
}: {
  column: string;
  label: string;
  align?: "left" | "right";
  hint?: string;
  sortBy: string;
  sortDir: "asc" | "desc";
  onSort: (col: string) => void;
}) {
  const active = sortBy === column;
  return (
    <th
      className={cn(
        "px-3 py-1",
        INTESTAZIONE,
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {/* ⚠️ La spiegazione si aggancia al bottone di ordinamento, non gli
          sta accanto: era un'icona «i» sorella del bottone (un <button>
          dentro un <button> non e' HTML valido) e allargava la colonna su
          ogni riga. Ora la parola e' sottolineata a tratti e si apre in
          hover; il click resta all'ordinamento. */}
      <span
        className={cn(
          "inline-flex items-center gap-1",
          align === "right" && "ml-auto",
        )}
      >
        <HintAnchor text={hint}>
          <button
            type="button"
            onClick={() => onSort(column)}
            className={cn(
              "inline-flex items-center gap-1 uppercase hover:text-foreground transition-colors",
              active && "text-foreground",
            )}
          >
            {hint ? <HintUnderline>{label}</HintUnderline> : <span>{label}</span>}
            {active && sortDir === "desc" && <ArrowDown className="h-3 w-3" />}
            {active && sortDir === "asc" && <ArrowUp className="h-3 w-3" />}
            {!active && <ArrowUpDown className="h-3 w-3 opacity-30" />}
          </button>
        </HintAnchor>
      </span>
    </th>
  );
}

/** La gara stop-contro-target di un segnale, in una cella.
 *
 * ⚠️ Il numero e' l'R, non la percentuale: R e' la distanza dello stop, quindi
 * «+2,4R» dice quanto il piano ha reso RISPETTO A CIO' CHE RISCHIAVA, che e'
 * la sola lettura confrontabile fra segnali con stop diversi. Il titolo porta
 * la storia intera, comprese le gambe toccate DOPO la chiusura — «stop il 5,
 * target il 18» vale -1R ed e' giusto, e dice anche che quello stop era
 * troppo stretto.
 *
 * ⚠️ E un marcatore quando quell'ordine si e' verificato: e' la sola diagnosi
 * che `plan_outcomes` sa dare e nessun'altra colonna la porta. Ambra no —
 * `amber-600` vale 3,19:1 su fondo scheda, sotto la soglia AA; resta il
 * grassetto e il titolo.
 */
function PianoCell({ plan }: { plan: PlanBrief | null }) {
  if (!plan) {
    return (
      <span
        className="text-muted-foreground"
        title="Nessun piano risolto: o il detector non emetteva un livello di invalidazione quando il segnale è scattato, o la gara fra stop e target non si è ancora chiusa."
      >
        —
      </span>
    );
  }
  const meta = ESITO_META[plan.esito];
  const stretto = stopTroppoStretto(plan);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-semibold tabular-nums",
        meta?.tono === "ok"
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
          : meta?.tono === "bad"
            ? "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300"
            : "bg-muted text-muted-foreground",
      )}
      title={raccontaPiano(plan)}
    >
      {plan.esito === "tp1" ? (
        <Target className="h-3 w-3 shrink-0" />
      ) : plan.esito === "scaduto" ? (
        <Hourglass className="h-3 w-3 shrink-0" />
      ) : (
        <X className="h-3 w-3 shrink-0" />
      )}
      {formatR(plan.r_multiple)}
      {stretto && <span aria-hidden>*</span>}
    </span>
  );
}

export function AlertsTable({
  alerts,
  selectedIds,
  onSelect,
  onSelectAll,
  onRowClick,
  q,
  onQueryChange,
  embedded = false,
  sortBy = "triggered_at",
  sortDir = "desc",
  onSort,
  onArchiveToggle,
}: Props) {
  const allSelected = alerts.length > 0 && alerts.every((a) => selectedIds.has(a.id));

  // Per-detector calibration table for the Prob.-cell honesty marker. ONE
  // cached fetch (react-query staleTime 1h, shared with the signal popup and
  // the Settings page) — the lookup below is a plain dict access per row.
  const { data: calibration } = useSignalCalibration();

  /** Honesty tag for an alert's detector (coinflip / negative / edge / null).
   *  Null while the calibration table is loading or for non-signal alerts. */
  const calibrationTag = (rule_kind: string | null | undefined) => {
    if (!calibration || !isSignalKind(rule_kind)) return null;
    const detector = (rule_kind as string).slice("signal:".length);
    return calibration.detectors[detector]?.tag ?? null;
  };

  // Column visibility — non-embedded only. Embedded mode has a fixed set
  // of columns (no menu, no toggles).
  const { isVisible, toggle } = useColumnVisibility("alerts", ALERTS_COLS as unknown as { id: string; label: string }[]);

  // Context-menu state for the column-visibility dropdown.
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState({ x: 0, y: 0 });

  function openColumnMenu(e: MouseEvent) {
    e.preventDefault();
    setMenuAnchor({ x: e.clientX, y: e.clientY });
    setMenuOpen(true);
  }

  // Per-column visibility resolved ONCE so the header and body stay in
  // lockstep. Embedded mode (the per-ticker history card) shows a fixed
  // compact set — Rilevato | Regola | Orizzonte | Forza | Prob. | Direzione |
  // Piano — while the full alerts page honours the column-visibility menu.
  // ⚠️ No Tono column there: the Regola chip already wears the tone's colour
  // and icon, so «BULLISH» beside it was the same fact twice, in the card
  // where horizontal room is scarcest. (Previous embedded
  // bug: the signal_date CELL rendered but its HEADER was gated `!embedded`,
  // so every header sat one column right of its data. Deriving both from the
  // same flag makes that drift impossible.)
  const showCheckbox = !embedded;
  // Anche la scheda del titolo mostra questa data, ed e' la stessa: prima
  // mostrava «Rilevato», cioe' l'ultima revisione.
  const showDataSegnale = embedded || isVisible("data_segnale");
  const showTitolo = !embedded;
  const showRegola = embedded || isVisible("regola");
  const showNatura = !embedded && isVisible("natura");
  const showOrizzonte = embedded || isVisible("orizzonte");
  const showForza = embedded || isVisible("forza");
  const showProbabilita = embedded || isVisible("probabilita");
  const showEsito = embedded || isVisible("esito");
  const showPiano = embedded || isVisible("piano");
  // Archive action column: always-on when the callback is wired (full page),
  // never in embedded mode — like the checkbox, it's an action, not data,
  // so it doesn't participate in the column-visibility menu.
  const showArchive = !embedded && !!onArchiveToggle;
  // Le intestazioni ridotte valgono per la PAGINA Segnali. La scheda del
  // titolo (embedded) ha gia' le sue, a 13,5px dalla classe della tabella, e
  // non e' stata chiesta: resta com'era.
  const TESTA = embedded ? "text-base" : INTESTAZIONE;

  // colSpan for the empty-state row must match the visible column count.
  const colSpan = [
    showCheckbox, showDataSegnale, showTitolo, showRegola,
    showNatura, showOrizzonte, showForza, showProbabilita,
    showEsito, showPiano, showArchive,
  ].filter(Boolean).length;

  // Corpo a 0.875rem (text-sm), intestazioni PIU' PICCOLE (`INTESTAZIONE`):
  // erano a 1rem per una richiesta vecchia, e il 2026-09-22 l'utente le ha
  // chieste ridotte. E righe piu' basse: `py-1` sulle celle e pastiglia della
  // regola compatta, perche' e' la cella piu' alta a decidere l'altezza.
  return (
    <>
      {/* Column-visibility context menu (non-embedded only) */}
      {!embedded && (
        <ColumnVisibilityMenu
          columns={ALERTS_COLS as unknown as { id: string; label: string }[]}
          isVisible={isVisible}
          toggle={toggle}
          open={menuOpen}
          onOpenChange={setMenuOpen}
          anchor={menuAnchor}
        />
      )}
      <Table className={embedded ? "text-[13.5px] [&_td]:py-0.5 [&_td]:px-2 [&_th]:h-7 [&_th]:px-2 [&_th]:text-[13.5px]" : "text-sm [&_td]:py-1 [&_th]:h-8"}>
      <TableHeader>
        {/* Right-click anywhere on the header row opens the column-visibility
            menu (non-embedded only). The menu positions itself at the cursor. */}
        <TableRow onContextMenu={embedded ? undefined : openColumnMenu}>
          {showCheckbox && (
            <TableHead className="w-8">
              <Checkbox
                checked={allSelected}
                onCheckedChange={(checked) => onSelectAll(!!checked)}
              />
            </TableHead>
          )}
          {showDataSegnale && (
            onSort ? (
              <SortableHeader
                column="emissione"
                label="Segnale"
                hint={HINT_SEGNALE}
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className={TESTA} hint={HINT_SEGNALE}>
                Segnale
              </TableHead>
            )
          )}
          {showTitolo && (
            /* Titolo column: logo + ticker (top) / company name (below),
               like the dashboard cards. Holds the inline ticker/name search.
               Always visible — identity column. */
            onSort ? (
              <th className={cn("px-3 py-1 text-left", INTESTAZIONE)}>
                <div className="flex items-center gap-2 min-w-0">
                  <button
                    type="button"
                    onClick={() => onSort("ticker")}
                    className={cn(
                      "inline-flex items-center gap-1 uppercase hover:text-foreground transition-colors shrink-0",
                      sortBy === "ticker" && "text-foreground",
                    )}
                  >
                    <span>Titolo</span>
                    {sortBy === "ticker" && sortDir === "desc" && <ArrowDown className="h-3 w-3" />}
                    {sortBy === "ticker" && sortDir === "asc" && <ArrowUp className="h-3 w-3" />}
                    {sortBy !== "ticker" && <ArrowUpDown className="h-3 w-3 opacity-30" />}
                  </button>
                  <TableSearchInput
                    value={q}
                    onChange={onQueryChange}
                    placeholder="cerca ticker o nome…"
                    ariaLabel="Filtra per ticker o nome"
                    className="flex-1 max-w-[200px]"
                  />
                </div>
              </th>
            ) : (
              <TableHead className={TESTA}>
                <div className="flex items-center gap-2 min-w-0">
                  <span className="shrink-0">Titolo</span>
                  <TableSearchInput
                    value={q}
                    onChange={onQueryChange}
                    placeholder="cerca ticker o nome…"
                    ariaLabel="Filtra per ticker o nome"
                    className="flex-1 max-w-[200px]"
                  />
                </div>
              </TableHead>
            )
          )}
          {showRegola && (
            <TableHead className={TESTA}>Regola</TableHead>
          )}
          {showNatura && (
            <TableHead className={TESTA} hint="Natura del segnale: continuazione del trend o inversione">
              Natura
            </TableHead>
          )}
          {showOrizzonte && (
            <TableHead className={TESTA} hint="Orizzonte temporale del segnale (breve / medio / lungo)">
              Orizzonte
            </TableHead>
          )}
          {showForza && (
            onSort ? (
              <SortableHeader
                column="strength"
                label="Forza"
                align="right"
                hint={FORZA_TOOLTIP}
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className={cn(TESTA, "text-right")} hint={FORZA_TOOLTIP}>
                Forza
              </TableHead>
            )
          )}
          {/* Prob. is NOT sortable, unlike every other numeric column here.
              Measured over 2,246 live signals, Probabilità takes ONE OR TWO
              distinct values per detector and spans 47-52 across the whole
              engine — Forza, beside it, takes 34-39 values per detector over
              60-98. So ordering by it ordered rows by detector, in a sequence
              that read as "best signals first" and was nothing of the kind.
              The "Tipo segnale" filter selects detectors properly. */}
          {showProbabilita && (
            <TableHead className={cn(TESTA, "text-right")} hint={PROBABILITA_TOOLTIP}>
              Prob.
            </TableHead>
          )}
          {showEsito && (
            <TableHead
              className={TESTA}
              hint="La DIREZIONE ha pagato all'orizzonte del detector: verde = azzeccata, rosso = mancata, … = in attesa dell'orizzonte, «Fermo» = la serie prezzi del titolo non avanza più e l'orizzonte non potrà mai completarsi. ⚠️ Non dice niente su stop e target: quella è la colonna «Piano» qui accanto, e le due possono discordare — un segnale può prendere il target in tre sedute e finire l'orizzonte sotto il prezzo d'ingresso."
            >
              Direzione
            </TableHead>
          )}
          {showPiano && (
            <TableHead
              className={TESTA}
              hint="Quale fra stop e target il prezzo ha toccato per PRIMO, con il guadagno in multipli di R (R = la distanza dello stop). L'ESITO è quello della gara, perché una posizione con quel target aveva anche uno stop: contare i soli tocchi darebbe un tasso che non corrisponde a nessun guadagno. Ma ogni tocco viene REGISTRATO comunque — la data del primo tocco di stop, 1° e 2° target su tutto l'orizzonte, anche dopo la chiusura — ed è da lì che la scheda Esiti conta gli «stop troppo stretti». Passa sulla cella per la sequenza. «—» quando il detector non emetteva un livello di invalidazione, o quando la gara non si è ancora chiusa."
            >
              Piano
            </TableHead>
          )}
          {showArchive && (
            /* Action column — empty header, fixed narrow width. */
            <TableHead className="w-10" aria-label="Azioni" />
          )}
        </TableRow>
      </TableHeader>
      <TableBody>
        {alerts.length === 0 && (
          <TableRow>
            <TableCell
              colSpan={colSpan}
              className="text-center text-muted-foreground py-8"
            >
              {q.trim()
                ? `Nessun risultato per "${q}".`
                : "Nessun segnale con questi filtri."}
            </TableCell>
          </TableRow>
        )}
        {alerts.map((a) => (
          <TableRow
            key={a.id}
            // ⚠️ Raggiungibile da tastiera. Trovato nel collaudo in browser
            // (2026-09-16): nel dettaglio titolo le righe non contenevano un
            // solo elemento focalizzabile, quindi senza mouse un segnale non si
            // apriva affatto. Solo la RIGA reagisce a Invio/Spazio: la casella
            // e il link del ticker dentro fanno il loro mestiere.
            tabIndex={0}
            className="cursor-pointer group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
            onClick={() => onRowClick(a)}
            onKeyDown={(e) => {
              if (e.target !== e.currentTarget) return;
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onRowClick(a);
              }
            }}
          >
            {showCheckbox && (
              <TableCell onClick={(e) => e.stopPropagation()}>
                <Checkbox
                  checked={selectedIds.has(a.id)}
                  onCheckedChange={(c) => onSelect(a.id, !!c)}
                />
              </TableCell>
            )}
            {/* Segnale — il giorno in cui e' comparso, uno solo */}
            {showDataSegnale && (
              <TableCell className="font-semibold tabular-nums">
                {(() => {
                  const delayed = isAlertDelayed(a);
                  const delta = alertDelayDays(a);
                  const barra = barraDiversaDalSegnale(a);
                  return (
                    <span
                      className="inline-flex items-center gap-1"
                      title={[
                        `Comparso il ${giornoDelSegnale(a)}`,
                        barra
                          ? (barra < giornoDelSegnale(a)
                              ? `candela del ${barra}`
                              : `ancora valido sulla barra del ${barra}`)
                          : null,
                        delayed && delta != null
                          ? `rilevato ${delta}g dopo la candela: possibile backfill o scan saltato`
                          : null,
                      ].filter(Boolean).join(" · ")}
                    >
                      {delayed && (
                        <Clock className="h-3 w-3 text-amber-700 dark:text-amber-400 shrink-0" />
                      )}
                      {formatShortDate(giornoDelSegnale(a))}
                    </span>
                  );
                })()}
              </TableCell>
            )}
            {showTitolo && (
              /* Titolo cell: always visible (identity column). */
              <TableCell>
                {/* Ticker e nome sulla STESSA riga (2026-09-22, richiesta
                    dell'utente): su due righe erano la cella piu' alta della
                    tabella. Il nome cede per primo — `truncate`, `min-w-0` — e
                    il ticker, che e' l'identita', non si stringe mai. */}
                <div className="flex items-center gap-2 min-w-0">
                  <StockLogo ticker={a.ticker ?? ""} size="xs" />
                  <div className="flex min-w-0 items-baseline gap-1.5">
                    {a.ticker ? (
                      <Link
                        to={`/stocks/${encodeURIComponent(a.ticker)}`}
                        onClick={(e) => e.stopPropagation()}
                        className="shrink-0 font-semibold hover:underline leading-tight"
                        title={`Vai al dettaglio di ${a.ticker}`}
                      >
                        {a.ticker}
                      </Link>
                    ) : (
                      <span className="font-semibold">—</span>
                    )}
                    {a.name && (
                      <span
                        className="min-w-0 truncate text-xs text-muted-foreground max-w-[220px] leading-tight"
                        title={a.name}
                      >
                        {a.name}
                      </span>
                    )}
                  </div>
                </div>
              </TableCell>
            )}
            {showRegola && (
              <TableCell>
                {/* Chip compatto ovunque (dal 2026-09-22 anche nella pagina):
                    e' la cella piu' alta della riga, quindi e' lei a decidere
                    l'altezza delle righe. Classi letterali: il purger. */}
                <AlertKindChip alert={a} className="px-1.5 py-0.5 text-[0.7647rem]" />
              </TableCell>
            )}
            {showNatura && (
              <TableCell>
                <AlertNatureCell alert={a} size="sm" />
              </TableCell>
            )}
            {/* Orizzonte — temporal horizon of the signal (breve/medio/lungo),
                from snapshot.horizon. Non-signal / legacy rows show an em dash. */}
            {showOrizzonte && (
              <TableCell>
                {(() => {
                  const hz = (a.snapshot as Record<string, unknown> | undefined)?.horizon;
                  const meta = typeof hz === "string" ? HORIZON_META[hz] : undefined;
                  if (!meta) return <span className="text-muted-foreground">—</span>;
                  return (
                    <span className={cn("inline-block px-1.5 py-0.5 rounded text-xs font-medium", meta.cls)}>
                      {meta.label}
                    </span>
                  );
                })()}
              </TableCell>
            )}
            {/* Forza — pattern strength (0-100). Coloured percentage
                (rose < 50, amber 50-69, emerald >= 70) with a strength bar on
                the full page. Embedded (narrow card) shows just the % to save
                width. Non-signal / price alerts have no Forza → em dash. */}
            {showForza && (
              <TableCell>
                {(() => {
                  const forza = snapshotForza(a.snapshot as Record<string, unknown> | undefined);
                  if (forza == null) {
                    return <div className="text-right"><span className="text-muted-foreground">—</span></div>;
                  }
                  const pct = Math.max(0, Math.min(100, forza));
                  const bar =
                    pct >= 70 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-rose-500";
                  const txt =
                    pct >= 70
                      ? "text-emerald-800 dark:text-emerald-400"
                      : pct >= 50
                        ? "text-amber-700 dark:text-amber-400"
                        : "text-rose-600 dark:text-rose-400";
                  return (
                    <div className="flex items-center justify-end gap-2" title={`Forza ${pct}% — ${FORZA_TOOLTIP}`}>
                      <span className={cn(embedded ? "text-[0.7647rem]" : "text-sm", "font-semibold tabular-nums w-10 text-right", txt)}>
                        {pct}%
                      </span>
                      {!embedded && (
                        <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                          <div className={cn("h-full rounded-full", bar)} style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </div>
                  );
                })()}
              </TableCell>
            )}
            {/* Probabilità — historical hit-rate (0-100). Rendered in a NEUTRAL
                info treatment (slate text / sky bar) so it reads as a different
                axis from the tone-colored Forza. Legacy alerts lacking it show
                an em dash. */}
            {showProbabilita && (
              <TableCell>
                {(() => {
                  const prob = snapshotProbabilita(a.snapshot as Record<string, unknown> | undefined);
                  if (prob == null) {
                    return <div className="text-right"><span className="text-muted-foreground">—</span></div>;
                  }
                  const pct = Math.max(0, Math.min(100, prob));
                  // Honesty marker: tiny amber/red dot when the detector's
                  // beta-stripped calibration says coinflip / negative — same
                  // copy as the badge in SignalSnapshotView, in dot form.
                  const tag = calibrationTag(a.rule_kind);
                  return (
                    <div className="flex items-center justify-end gap-2" title={`Probabilità ${pct}% — ${PROBABILITA_TOOLTIP}`}>
                      {tag === "coinflip" && (
                        <span
                          className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0"
                          title="Storicamente ~50/50 al netto del mercato: nessun edge direzionale dimostrato"
                        />
                      )}
                      {tag === "negative" && (
                        <span
                          className="h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0"
                          title="Edge storico NEGATIVO al netto del mercato: segnale anti-predittivo"
                        />
                      )}
                      <span className={cn(embedded ? "text-[0.7647rem]" : "text-sm", "font-semibold tabular-nums w-10 text-right text-slate-700 dark:text-slate-300")}>
                        {pct}%
                      </span>
                      {!embedded && (
                        <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                          <div className="h-full rounded-full bg-sky-500 dark:bg-sky-400" style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </div>
                  );
                })()}
              </TableCell>
            )}
            {/* Esito — realized outcome from the signal_outcomes warehouse.
                Green check chip "+X.X%" on hit, red x chip on miss, muted "…"
                while the horizon is still maturing, blank for legacy rows
                without a signal_date (they never mature). */}
            {showEsito && (
              <TableCell>
                {(() => {
                  const hit = a.outcome_hit;
                  if (hit != null) {
                    const fwd = a.outcome_fwd_return;
                    const pct =
                      fwd != null ? `${fwd >= 0 ? "+" : ""}${(fwd * 100).toFixed(1)}%` : "";
                    const hz = a.outcome_horizon_days;
                    const title = `Esito a ${hz ?? "?"}gg: ${hit ? "direzione azzeccata" : "direzione mancata"}${pct ? ` (${pct})` : ""}`;
                    return (
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold tabular-nums",
                          hit
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
                            : "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
                        )}
                        title={title}
                      >
                        {hit ? <Check className="h-3 w-3 shrink-0" /> : <X className="h-3 w-3 shrink-0" />}
                        {pct}
                      </span>
                    );
                  }
                  const pending = isSignalKind(a.rule_kind) && !!a.signal_date;
                  if (!pending) return null;
                  // ⚠️ La serie del titolo si è fermata: questo segnale non sta
                  // aspettando l'orizzonte, non lo raggiungerà mai. Ambra e non
                  // rosa: non è una direzione sbagliata, è un dato che manca —
                  // la stessa separazione fra «rosa/smeraldo = verso» e «tutto
                  // il resto» che questo progetto applica altrove.
                  if (a.series_stalled) {
                    return (
                      <span
                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60"
                        title={
                          "La serie prezzi del titolo si è fermata" +
                          (a.series_last_bar ? " il " + a.series_last_bar : "") +
                          ": l'orizzonte del segnale non può più completarsi."
                        }
                      >
                        <Unplug className="h-3 w-3 shrink-0" />
                        Fermo
                      </span>
                    );
                  }
                  return (
                    <span
                      className="text-muted-foreground"
                      title="Esito in attesa dell'orizzonte: non è ancora trascorso"
                    >
                      …
                    </span>
                  );
                })()}
              </TableCell>
            )}
            {/* Piano — la gara stop-contro-target (plan_outcomes). ⚠️ Domanda
                DIVERSA da quella della colonna accanto, non la stessa
                misurata meglio: il titolo della pastiglia racconta quale
                gamba ha chiuso E quali il prezzo ha toccato dopo, che e'
                l'unica diagnosi che questo magazzino sa dare. */}
            {showPiano && (
              <TableCell>
                <PianoCell plan={a.plan ?? null} />
              </TableCell>
            )}
            {/* Archivia/Disarchivia — hover-visible icon at the row end.
                stopPropagation on the CELL (same pattern as the checkbox
                cell) so a click never opens the detail dialog. */}
            {showArchive && (
              <TableCell onClick={(e) => e.stopPropagation()} className="w-10">
                <button
                  type="button"
                  onClick={() => onArchiveToggle?.(a)}
                  title={a.archived_at ? "Disarchivia segnale" : "Archivia segnale"}
                  aria-label={a.archived_at ? "Disarchivia segnale" : "Archivia segnale"}
                  className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                >
                  {a.archived_at ? (
                    <ArchiveRestore className="h-4 w-4" />
                  ) : (
                    <Archive className="h-4 w-4" />
                  )}
                </button>
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
    </>
  );
}

// ToneChip + Kind badge moved into the shared `AlertChips` module so
// the alerts table, the stock-detail history card, and the popup all
// render identical chips. See `frontend/src/components/AlertChips.tsx`.
