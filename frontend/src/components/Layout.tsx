import {
  Bell,
  CalendarDays,
  Filter,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Settings,
} from "lucide-react";
import { NavbarSearch } from "@/components/NavbarSearch";
import { ScanProgressToast } from "@/components/ScanProgressToast";
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
  { to: "/watchlists", label: "Watchlists", icon: ListChecks, enabled: true },
  // /stocks route stays; the page is conceptually a screener (filters +
  // ranking) so that's the label. Filter icon to telegraph the function.
  { to: "/stocks", label: "Screener", icon: Filter, enabled: true },
  { to: "/calendar", label: "Calendario", icon: CalendarDays, enabled: true },
  // Rules used to be a separate page; now lives in the AlertsPage right
  // sidebar so the user composes rules + reviews their alerts in one
  // surface. The /rules route was removed.
  { to: "/alerts", label: "Alerts", icon: Bell, enabled: true },
  { to: "/settings", label: "Impostazioni", icon: Settings, enabled: false },
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
      <div className="flex flex-1 flex-col">
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
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
      {/* Persistent scan-progress notification — mounted globally so it
          survives route changes. The user can navigate around while a
          scan runs and still see the live progress. Auto-dismisses 30s
          after completion; click anywhere on the toast to dismiss. */}
      <ScanProgressToast />
    </div>
  );
}

