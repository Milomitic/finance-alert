import {
  Bell,
  Building2,
  CalendarDays,
  Filter,
  Grid3x3,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Settings,
} from "lucide-react";
import { NavbarSearch } from "@/components/NavbarSearch";
import { ScanProgressToast } from "@/components/ScanProgressToast";
import { ScoreRecomputeToast } from "@/components/ScoreRecomputeToast";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

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

export default function Layout() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="flex w-60 flex-col border-r bg-card">
        <div className="px-5 py-4">
          <h1 className="text-base font-semibold">Finance Alert</h1>
          <p className="text-xs text-muted-foreground">v0.1 — Fase 1</p>
        </div>
        <Separator />
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
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "text-foreground hover:bg-accent"
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {entry.label}
              </NavLink>
            );
          })}
        </nav>
      </aside>
      {/* `min-w-0` is essential: flex children default to
          `min-width: auto` which means "fit content". When a child
          (e.g. the dashboard's MarketTickerTape with its duplicated
          scrolling track) has intrinsic content wider than the
          viewport, the WHOLE page becomes horizontally scrollable
          unless this column allows itself to shrink below its
          content. Same trick applied on `<main>`. */}
      <div className="flex flex-1 flex-col min-w-0">
        <header className="flex h-14 items-center gap-4 border-b px-6">
          <NavbarSearch />
          <span className="ml-auto text-sm text-muted-foreground">
            {me.data ? me.data.username : ""}
          </span>
          <Button variant="ghost" size="sm" onClick={onLogout} disabled={logout.isPending}>
            <LogOut className="mr-2 h-4 w-4" />
            Esci
          </Button>
        </header>
        <main className="flex-1 min-w-0 overflow-y-auto p-6">
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

