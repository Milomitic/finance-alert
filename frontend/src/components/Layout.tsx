import {
  Bell,
  Hourglass,
  Briefcase,
  Building2,
  CalendarDays,
  Filter,
  ScanSearch,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavbarSearch } from "@/components/NavbarSearch";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ScanProgressToast } from "@/components/ScanProgressToast";
import { ScoreRecomputeToast } from "@/components/ScoreRecomputeToast";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useLogout, useMe } from "@/hooks/useAuth";
import { useTheme, type Theme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

interface NavEntry {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  enabled: boolean;
}

/** Un gruppo di destinazioni. `label: null` = nessuna intestazione: la voce
 *  sta da sola, come un'ancora in cima o in fondo alla barra. */
interface NavGroup {
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
const NAV_GROUPS: NavGroup[] = [
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

export { NAV_GROUPS };

/** The nav link list — shared verbatim by the desktop sidebar and the
 *  mobile drawer so there's a single source of truth for entries +
 *  active styling. `onNavigate` lets the mobile drawer close itself
 *  the moment a link is tapped. When `collapsed` the desktop rail
 *  renders icons only (labels hidden, full label moved to the hover
 *  tooltip + accessible label) so navigation stays usable at w-16. */
function NavList({
  onNavigate,
  collapsed = false,
}: {
  onNavigate?: () => void;
  collapsed?: boolean;
}) {
  return (
    <nav className="flex flex-1 flex-col gap-1 p-3 overflow-y-auto min-h-0">
      {NAV_GROUPS.map((group, gi) => (
        <div
          key={group.label ?? `anchor-${gi}`}
          // Gruppo VERO, non solo disegnato: con `aria-label` un lettore di
          // schermo annuncia «Analisi, gruppo» invece di leggere nove voci di
          // seguito, che e' esattamente la piattezza che questa voce corregge.
          role={group.label ? "group" : undefined}
          aria-label={group.label ?? undefined}
          className="flex flex-col gap-1"
        >
          {/* ⚠️ Un gruppo SENZA etichetta che segue uno etichettato porta
              comunque un confine. Trovato dalla verifica a schermo: nel DOM
              `Diagnostica` e fuori da ogni gruppo — il test lo asserisce e
              passa — ma resa senza stacco, subito sotto `Posizioni`, si LEGGE
              come l'ultima voce di Monitoraggio. Struttura giusta, lettura
              sbagliata, ed e esattamente la classe di difetto che il quinto
              criterio di chiusura del piano affida a chi guarda.
              Il primo gruppo non ne porta: sopra non c'e niente da separare. */}
          {!group.label && gi > 0 && (
            <Separator data-nav-separator="true" className="my-1.5" />
          )}
          {group.label &&
            (collapsed ? (
              // Nel binario a 64px un'intestazione di testo sarebbe
              // illeggibile: resta il confine, che e' la meta dell'informazione
              // che l'intestazione porta.
              <Separator data-nav-separator="true" className="my-1.5" />
            ) : (
              <div className="px-3 pt-3 pb-1 text-[0.65rem] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                {group.label}
              </div>
            ))}
          {group.items.map((entry) => {
        const Icon = entry.icon;
        const base = cn(
          "flex items-center rounded text-base transition-colors",
          collapsed ? "justify-center px-0 py-2.5" : "gap-2 px-3 py-2",
        );
        if (!entry.enabled) {
          return (
            <span
              key={entry.to}
              title={`${entry.label} — Disponibile nelle prossime fasi`}
              className={cn(base, "cursor-not-allowed text-muted-foreground")}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && entry.label}
            </span>
          );
        }
        return (
          <NavLink
            key={entry.to}
            to={entry.to}
            end={entry.to === "/"}
            onClick={onNavigate}
            // Title only when collapsed — expanded shows the label inline,
            // so a tooltip would be redundant noise.
            title={collapsed ? entry.label : undefined}
            aria-label={collapsed ? entry.label : undefined}
            className={({ isActive }) =>
              cn(
                base,
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-foreground hover:bg-accent",
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {!collapsed && entry.label}
          </NavLink>
        );
          })}
        </div>
      ))}
    </nav>
  );
}

function SidebarBrand() {
  return (
    <div className="px-5 py-4">
      <h1 className="text-base font-semibold">Finance Alert</h1>
      <p className="text-xs text-muted-foreground">v0.1 — Fase 1</p>
    </div>
  );
}

/** Light/dark theme switch — icon-only (no text label), lives in the sidebar
 *  footer. Sun when dark (→ switch to light), Moon when light. The accessible
 *  name lives on title/aria-label so the icon alone stays unambiguous. */
function ThemeToggleButton({
  theme,
  onToggle,
}: {
  theme: Theme;
  onToggle: () => void;
}) {
  const isDark = theme === "dark";
  const Icon = isDark ? Sun : Moon;
  const label = isDark ? "Tema chiaro" : "Tema scuro";
  return (
    <button
      type="button"
      onClick={onToggle}
      title={label}
      aria-label={label}
      className="flex items-center justify-center rounded p-2 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
    >
      <Icon className="h-4 w-4 shrink-0" />
    </button>
  );
}

/** Sidebar footer pinned below the nav: il controllo del tema.
 *
 *  ⚠️ Qui c'era un link «Impostazioni» sotto un ingranaggio, e portava a una
 *  pagina di diagnostica. E stato tolto invece di essere rinominato: la
 *  diagnostica ha adesso la sua voce nel menu principale, e l'ingranaggio
 *  significa preferenze ovunque.
 *
 *  ⚠️ E NON e stato sostituito da una pagina di preferenze vuota. Le
 *  preferenze reali esistono ma vivono ognuna accanto alla funzione che
 *  serve — tema e barra laterale qui, timeframe del grafico nel grafico,
 *  viste salvate nel filtro, colonne nella tabella — e una destinazione vuota
 *  creata per simmetria del menu sarebbe un posto dove non trovare niente.
 *  L'ingranaggio torna quando c'e qualcosa da metterci dentro.
 *
 *  Il tema resta qui perche e l'unica preferenza globale che l'app abbia. */
function SidebarFooter({
  theme,
  onToggle,
  collapsed = false,
}: {
  theme: Theme;
  onToggle: () => void;
  collapsed?: boolean;
}) {
  return (
    <div className="p-3 flex flex-col gap-1">
      <div className={cn("flex", collapsed ? "justify-center" : "justify-end")}>
        <ThemeToggleButton theme={theme} onToggle={onToggle} />
      </div>
    </div>
  );
}

export default function Layout() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggle: toggleTheme } = useTheme();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const mobileMenuTriggerRef = useRef<HTMLButtonElement>(null);
  const mobileCloseRef = useRef<HTMLButtonElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  // Desktop sidebar collapse (icon-rail). Persisted so the choice
  // survives reloads. Lazy init reads localStorage once; the effect
  // mirrors every change back. Defaults to expanded.
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem("sidebar-collapsed") === "1";
    } catch {
      return false;
    }
  });
  // The tab said "Finance-Alert" on every page, so a window with the screener,
  // a stock and the calendar open showed three identical tabs. The label comes
  // from NAV, the same array that renders the menu, so the two cannot drift.
  //
  // Detail routes (/stocks/NVDA, /alerts/123) are deliberately NOT guessed
  // from a prefix: /stocks/NVDA is a stock, not "Screener", and a confidently
  // wrong title is worse than a generic one. Those pages can set their own.
  useEffect(() => {
    const exact = NAV.find((entry) => entry.to === location.pathname);
    // `/settings` e `/health` ora reindirizzano su `/diagnostics`, che e in
    // NAV: il caso speciale che c'era qui non serve piu.
    const label = exact?.label ?? null;
    document.title = label ? `${label} · Finance-Alert` : "Finance-Alert";
  }, [location.pathname]);

  useEffect(() => {
    try {
      localStorage.setItem("sidebar-collapsed", sidebarCollapsed ? "1" : "0");
    } catch {
      /* private mode / quota — non-fatal, just don't persist */
    }
  }, [sidebarCollapsed]);

  // Close the drawer on any route change — covers nav taps, the
  // navbar search jumping to a stock, browser back/forward, etc.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  // Treat the mobile navigation as a dialog: move focus inside on open,
  // trap Tab, close on Escape, and return focus to the hamburger on close.
  useEffect(() => {
    if (!mobileNavOpen) {
      const trigger = previouslyFocusedRef.current ?? mobileMenuTriggerRef.current;
      if (trigger && document.contains(trigger)) trigger.focus();
      previouslyFocusedRef.current = null;
      return;
    }
    mobileCloseRef.current?.focus();
    const drawer = mobileCloseRef.current?.closest("aside");
    if (!drawer) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileNavOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        drawer.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    drawer.addEventListener("keydown", onKeyDown);
    return () => drawer.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen]);

  // Lock body scroll while the drawer overlay is open so the page
  // behind it doesn't scroll under the user's thumb.
  useEffect(() => {
    if (!mobileNavOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileNavOpen]);

  const onLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* FIRST focusable element in the document, deliberately. Placed after
          the sidebar it skipped nothing: the rail's collapse toggle and its
          ~12 links came first, which is precisely what a keyboard user needs
          to get past. A regression test asserts the ordering, because the
          link looks correct wherever it sits. */}
      <a
        href="#contenuto"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:border focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-md"
      >
        Salta al contenuto
      </a>
      {/* Desktop sidebar — hidden below lg; the mobile drawer below
          replaces it on phones/tablets. Collapses to a w-16 icon rail
          via the toggle; the width animates while labels swap in/out. */}
      <aside
        className={cn(
          "hidden lg:flex flex-col border-r bg-card transition-[width] duration-200 ease-out",
          sidebarCollapsed ? "w-16" : "w-60",
        )}
      >
        {/* Brand + collapse toggle. When collapsed, the brand text is
            dropped and the toggle centers in the rail; expanded shows
            the brand on the left and the toggle on the right. */}
        <div
          className={cn(
            "flex items-center py-4",
            sidebarCollapsed ? "justify-center px-2" : "justify-between pl-5 pr-2",
          )}
        >
          {!sidebarCollapsed && (
            <div className="min-w-0">
              <h1 className="text-base font-semibold truncate">Finance Alert</h1>
              <p className="text-xs text-muted-foreground">v0.1 — Fase 1</p>
            </div>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0"
            aria-label={sidebarCollapsed ? "Espandi menu" : "Comprimi menu"}
            title={sidebarCollapsed ? "Espandi menu" : "Comprimi menu"}
            onClick={() => setSidebarCollapsed((c) => !c)}
          >
            {sidebarCollapsed ? (
              <PanelLeftOpen className="h-5 w-5" />
            ) : (
              <PanelLeftClose className="h-5 w-5" />
            )}
          </Button>
        </div>
        <Separator />
        <NavList collapsed={sidebarCollapsed} />
        {/* Impostazioni + theme toggle pinned to the bottom of the rail
            (NavList is flex-1 and scrolls; this footer stays visible). */}
        <Separator />
        <SidebarFooter
          theme={theme}
          onToggle={toggleTheme}
          collapsed={sidebarCollapsed}
        />
      </aside>

      {/* Mobile drawer: overlay + slide-in panel. Rendered only when
          open so it stays out of the a11y tree otherwise. */}
      {mobileNavOpen && (
        /* ⚠️ `role` + `aria-modal` non sono decorazione: il drawer si
           COMPORTA gia da modale — il fuoco entra, resta in trappola nelle due
           direzioni, ESC chiude e il fuoco torna al bottone, lo scorrimento e
           bloccato — ma senza queste due parole un lettore di schermo non
           annuncia un confine e non sa che il resto della pagina e fuori
           gioco. L'utente sente il trap come «il fuoco non si muove piu»
           invece che come «sono dentro un pannello», che e' la forma peggiore:
           funziona per chi guarda e confonde chi ascolta.
           Trovato collaudando FA-011 su un browser vero; axe non lo prende,
           perche un `div` senza ruolo non viola nulla — e un'ASSENZA, non una
           dichiarazione sbagliata. */
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Menu di navigazione"
          className="fixed inset-0 z-50 lg:hidden"
        >
          <button
            type="button"
            aria-label="Chiudi menu"
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setMobileNavOpen(false)}
          />
          <aside className="absolute left-0 top-0 flex h-full w-64 max-w-[80vw] flex-col border-r bg-card shadow-xl animate-in slide-in-from-left duration-200">
            <div className="flex items-center justify-between pr-2">
              <SidebarBrand />
              <Button
                ref={mobileCloseRef}
                variant="ghost"
                size="icon"
                aria-label="Chiudi menu"
                onClick={() => setMobileNavOpen(false)}
              >
                <X className="h-5 w-5" />
              </Button>
            </div>
            <Separator />
            <div className="flex-1 overflow-y-auto">
              <NavList onNavigate={() => setMobileNavOpen(false)} />
            </div>
            <Separator />
            <SidebarFooter
              theme={theme}
              onToggle={toggleTheme}
            />
          </aside>
        </div>
      )}

      {/* `min-w-0` is essential: flex children default to
          `min-width: auto` which means "fit content". When a child
          (e.g. the dashboard's MarketTickerTape with its duplicated
          scrolling track) has intrinsic content wider than the
          viewport, the WHOLE page becomes horizontally scrollable
          unless this column allows itself to shrink below its
          content. Same trick applied on `<main>`. */}
      <div className="flex flex-1 flex-col min-w-0">
        <header className="flex h-14 items-center gap-2 border-b px-3 sm:gap-4 sm:px-6">
          {/* Hamburger — only on screens without the persistent
              sidebar. */}
          <Button
            ref={mobileMenuTriggerRef}
            variant="ghost"
            size="icon"
            className="lg:hidden shrink-0"
            aria-label="Apri menu"
            onClick={() => { previouslyFocusedRef.current = document.activeElement as HTMLElement; setMobileNavOpen(true); }}
          >
            <Menu className="h-5 w-5" />
          </Button>
          <NavbarSearch />
          <span className="ml-auto hidden text-sm text-muted-foreground sm:inline">
            {me.data ? me.data.username : ""}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={onLogout}
            disabled={logout.isPending}
            className="shrink-0"
          >
            <LogOut className="h-4 w-4 sm:mr-2" />
            {/* sr-only rather than hidden: `hidden` removes the word from the
                accessibility tree too, so on a phone this button was an icon
                with no name at all. This way the accessible name is the same
                text desktop users read, from one source. */}
            <span className="sr-only sm:not-sr-only">Esci</span>
          </Button>
        </header>
        <main id="contenuto" className="flex-1 min-w-0 overflow-y-auto p-3 sm:p-6">
          {/* Keyed by pathname so the boundary is a fresh instance per route:
              boundaries never clear their own error state, so without this a
              single crash would leave every subsequent page blank until a full
              reload. Navigating away is the recovery. The header and nav sit
              OUTSIDE it and stay usable. */}
          <ErrorBoundary key={location.pathname} label={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      {/* Persistent progress notifications — mounted globally so they
          survive route changes. The user can navigate around while a
          background job runs and still see live progress. Both toasts
          float bottom-right; in practice only one shows at a time
          (concurrent scan + recompute is server-blocked by the 409
          guard, and the post-completion windows rarely overlap). Each
          auto-dismisses 30s after completion; click anywhere on the
          toast body to dismiss earlier. */}
      {/* `fallback={null}`: these are chrome. If one throws, the right outcome
          is that it disappears and the dashboard behind it keeps working —
          exactly what did NOT happen when the scan toast called a hook after an
          early return and took the whole page down with it. The console still
          gets the error. */}
      <ErrorBoundary fallback={null} label="ScanProgressToast">
        <ScanProgressToast />
      </ErrorBoundary>
      <ErrorBoundary fallback={null} label="ScoreRecomputeToast">
        <ScoreRecomputeToast />
      </ErrorBoundary>
    </div>
  );
}
