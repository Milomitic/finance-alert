import { ListChecks, LayoutDashboard, Search, Bell, Sliders, Settings, LogOut } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useLogout, useMe } from "@/hooks/useAuth";
import { useUnreadAlertsCount } from "@/hooks/useUnreadAlertsCount";
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
  { to: "/stocks/AAPL", label: "Stocks", icon: Search, enabled: true },
  { to: "/alerts", label: "Alerts", icon: Bell, enabled: true },
  { to: "/rules", label: "Regole", icon: Sliders, enabled: false },
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
                {entry.to === "/alerts" && <UnreadBadge />}
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-end gap-3 border-b px-6">
          <span className="text-sm text-muted-foreground">
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
    </div>
  );
}

function UnreadBadge() {
  const q = useUnreadAlertsCount();
  const count = q.data?.count ?? 0;
  if (!count) return null;
  return (
    <span className="ml-auto rounded-full bg-destructive text-destructive-foreground text-xs px-2 py-0.5">
      {count > 99 ? "99+" : count}
    </span>
  );
}
