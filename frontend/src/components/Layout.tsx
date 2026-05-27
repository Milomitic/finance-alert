import {
  Bell,
  Building2,
  CalendarDays,
  Filter,
  Grid3x3,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sun,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavbarSearch } from "@/components/NavbarSearch";
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

const NAV: NavEntry[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, enabled: true },
  // /sectors is the post-watchlist hub: cross-sector overview with
  // breadth, score medians, top-movers, and tile drill-downs into
  // the per-sector detail page. Grid icon to telegraph the
  // "everything at a glance" function (vs ListChecks' to-do flavor
  // that the old Watchlists entry carried).
  { to: "/sectors", label: "Settori", icon: Grid3x3, enabled: true },
  // /stocks route stays; the page is conceptually a screener (filters +
  // ranking) so that's the label. Filter icon to telegraph the function.
  { to: "/stocks", label: "Screener", icon: Filter, enabled: true },
  { to: "/calendar", label: "Calendario", icon: CalendarDays, enabled: true },
  { to: "/institutionals", label: "Superinvestor", icon: Building2, enabled: true },
  // Rules used to be a separate page; now lives in the AlertsPage right
  // sidebar so the user composes rules + reviews their alerts in one
  // surface. The /rules route was removed.
  { to: "/alerts", label: "Segnali", icon: Bell, enabled: true },
  { to: "/health", label: "Salute", icon: HeartPulse, enabled: true },
  { to: "/settings", label: "Impostazioni", icon: Settings, enabled: true },
];

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
    <nav className="flex flex-1 flex-col gap-1 p-3">
      {NAV.map((entry) => {
        const Icon = entry.icon;
        const base = cn(
          "flex items-center rounded text-sm transition-colors",
          collapsed ? "justify-center px-0 py-2.5" : "gap-2 px-3 py-2",
        );
        if (!entry.enabled) {
          return (
            <span
              key={entry.to}
              title={`${entry.label} — Disponibile nelle prossime fasi`}
              className={cn(base, "cursor-not-allowed text-muted-foreground/60")}
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

/** Light/dark theme switch — lives at the bottom of the menu. Mirrors the
 *  NavList row styling (same paddings + collapsed icon-only mode) so it reads
 *  as part of the menu. Sun when dark (→ switch to light), Moon when light. */
function ThemeToggleButton({
  theme,
  onToggle,
  collapsed = false,
}: {
  theme: Theme;
  onToggle: () => void;
  collapsed?: boolean;
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
      className={cn(
        "flex items-center rounded text-sm text-foreground hover:bg-accent transition-colors w-full",
        collapsed ? "justify-center px-0 py-2.5" : "gap-2 px-3 py-2",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && label}
    </button>
  );
}

export default function Layout() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggle: toggleTheme } = useTheme();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
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
    <div className="flex min-h-screen bg-background">
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
        {/* Theme switch pinned to the bottom of the rail (NavList is flex-1). */}
        <Separator />
        <div className="p-3">
          <ThemeToggleButton
            theme={theme}
            onToggle={toggleTheme}
            collapsed={sidebarCollapsed}
          />
        </div>
      </aside>

      {/* Mobile drawer: overlay + slide-in panel. Rendered only when
          open so it stays out of the a11y tree otherwise. */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
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
            <div className="p-3">
              <ThemeToggleButton theme={theme} onToggle={toggleTheme} />
            </div>
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
            variant="ghost"
            size="icon"
            className="lg:hidden shrink-0"
            aria-label="Apri menu"
            onClick={() => setMobileNavOpen(true)}
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
            <span className="hidden sm:inline">Esci</span>
          </Button>
        </header>
        <main className="flex-1 min-w-0 overflow-y-auto p-3 sm:p-6">
          <Outlet />
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
      <ScanProgressToast />
      <ScoreRecomputeToast />
    </div>
  );
}
