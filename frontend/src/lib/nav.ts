/* ─── La barra di navigazione, come DATO ──────────────────────────────────
 *
 * Vive fuori da `Layout.tsx` perche non e un componente e non ha niente a che
 * fare con il rendering della shell. Il beneficio immediato e che il test
 * sulla navigazione legge l'elenco senza montare l'intera applicazione; quello
 * a lungo termine e che un file che esporta componenti E costanti rompe il
 * Fast Refresh — `react-refresh/only-export-components`, che questo repo non
 * gated per scelta ma che qui segnalava una separazione mancante vera.
 */
import {
  Bell,
  Briefcase,
  Building2,
  CalendarDays,
  Filter,
  HeartPulse,
  Hourglass,
  LayoutDashboard,
  ScanSearch,
} from "lucide-react";
import type { ComponentType } from "react";

export interface NavEntry {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  enabled: boolean;
}

/** Un gruppo di destinazioni. `label: null` = nessuna intestazione: la voce
 *  sta da sola, come un'ancora in cima o in fondo alla barra. */
export interface NavGroup {
  label: string | null;
  items: NavEntry[];
}

/* ─── La barra raggruppata ────────────────────────────────────────────────
 *
 * Voce 5.2 del piano. Nove destinazioni in un elenco piatto non dicono che
 * Esplora, Screener, Calendario e Superinvestor rispondono tutte alla stessa
 * domanda — «che cosa c'e la fuori» — mentre In formazione, Segnali e
 * Posizioni rispondono a un'altra: «che cosa sto seguendo».
 *
 * ⚠️ Sono ETICHETTE, non pagine: nessuna rotta cambia e nessuna destinazione
 * nasce. Rinominare gli indirizzi (`/sectors` che si chiama «Esplora» e un
 * difetto vero di leggibilita) romperebbe i segnalibri senza risolvere niente
 * che si veda, e il piano lo tiene fuori da questa tranche apposta.
 *
 * ⚠️ Due voci restano SENZA gruppo, e il piano ne prevedeva tre di gruppi.
 * «Strumenti» avrebbe contenuto Stato e Metodo — ma FA-037 le ha gia fuse in
 * una destinazione sola, quindi il gruppo avrebbe avuto un figlio unico, cioe
 * una riga di cornice con zero informazione. Dashboard era gia un'ancora; ora
 * Diagnostica e la sua simmetrica in fondo.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, enabled: true },
    ],
  },
  {
    label: "Analisi",
    items: [
      // /sectors is the post-watchlist hub: cross-sector overview with
      // breadth, score medians, top-movers, and tile drill-downs into
      // the per-sector detail page.
      //
      // `ScanSearch` (a magnifier inside scan brackets) rather than the old
      // `Grid3x3`: the grid told you the LAYOUT of the page, not what it is
      // for. Beside it sits Screener with a Filter icon, and the two read as a
      // pair — filtrare contro esplorare.
      { to: "/sectors", label: "Esplora", icon: ScanSearch, enabled: true },
      // /stocks route stays; the page is conceptually a screener (filters +
      // ranking) so that's the label. Filter icon to telegraph the function.
      { to: "/stocks", label: "Screener", icon: Filter, enabled: true },
      { to: "/calendar", label: "Calendario", icon: CalendarDays, enabled: true },
      { to: "/institutionals", label: "Superinvestor", icon: Building2, enabled: true },
    ],
  },
  {
    // ⚠️ L'ordine non e estetico: e la vita di un'idea. Un setup diventa un
    // segnale che diventa una posizione, e da settembre 2026 quella catena e
    // percorribile davvero — `converted_alert_id` e `Position.alert_id` la
    // rendono nei dati. Segnali stava prima di In formazione, cioe la barra
    // raccontava la storia al contrario.
    label: "Monitoraggio",
    items: [
      { to: "/setups", label: "In formazione", icon: Hourglass, enabled: true },
      // Rules used to be a separate page; now lives in the AlertsPage right
      // sidebar so the user composes rules + reviews their alerts in one
      // surface. The /rules route was removed.
      { to: "/alerts", label: "Segnali", icon: Bell, enabled: true },
      // Tracked trades: playbook entries persisted as positions with live P&L
      // and auto stop/target hit detection. Briefcase = "portfolio" flavor.
      { to: "/positions", label: "Posizioni", icon: Briefcase, enabled: true },
    ],
  },
  {
    label: null,
    items: [
      // ⚠️ Una sola destinazione diagnostica, con due schede dentro.
      //
      // Erano due pagine con nomi diversi e posti diversi: «Salute» qui e
      // «Impostazioni» in fondo alla barra, sotto un ingranaggio — cioe nel
      // posto dove ogni applicazione mette le preferenze, mentre quella pagina
      // conteneva otto pannelli diagnostici e zero impostazioni.
      { to: "/diagnostics", label: "Diagnostica", icon: HeartPulse, enabled: true },
    ],
  },
];

/** L'elenco piatto, DERIVATO dai gruppi e non scritto a mano.
 *
 * Il titolo della scheda si legge da qui, e la barra si rende dai gruppi: due
 * elenchi mantenuti a mano divergerebbero al primo inserimento, e la
 * divergenza sarebbe muta — una destinazione nuova con il titolo generico,
 * oppure un titolo per una voce che dalla barra e sparita. */
export const NAV: NavEntry[] = NAV_GROUPS.flatMap((g) => g.items);
