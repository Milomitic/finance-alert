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
  Settings,
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
  { to: "/alerts", label: "Alerts", icon: Bell, enabled: true },
  { to: "/health", label: "Salute", icon: HeartPulse, enabled: true },
  { to: "/settings", label: "Impostazioni", icon: Settings, enabled: true },
];

/** The nav link list — shared verbatim by the desktop sidebar and the
 *  mobile drawer so there's a single source of truth for entries +
 *  active styling. `onNavigate` lets the mobile drawer close itself
 *  the moment a link is tapped. */
function NavList({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-1 flex-col gap-1 p-3">
      {NAV.map((entry) => {
        const Icon = entry.icon;
        if (!entry.enabled) {
          return (
            <span
              key={entry.to}
              title="Disponibile nelle prossime fasi"
              className="flex cursor-not-allowed items-center gap-2 rounded px-3 py-2 text-sm text-muted-foreground/60"
            >
              <Icon className="h-4 w-4" />
              {entry.label}
            </span>
          );
        }
        return (
          <NavLink
            key={entry.to}
            to={entry.to}
            end={entry.to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 rounded px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-foreground hover:bg-accent",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {entry.label}
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

export default function Layout() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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
          replaces it on phones/tablets. */}
      <aside className="hidden lg:flex w-60 flex-col border-r bg-card">
        <SidebarBrand />
        <Separator />
        <NavList />
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
