import { Menu } from "lucide-react";
import { NavLink } from "react-router-dom";

import { NAV_PRIMARIE } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** La barra di navigazione in basso, sotto `lg` (C-68, E-16).
 *
 *  Le quattro destinazioni di ogni giorno a un tocco, dove arriva il pollice,
 *  e «Altro» che apre il menu completo. Prima ogni cambio di pagina costava
 *  due tocchi nell'angolo opposto al pollice.
 *
 *  Sta NEL flusso della colonna, non sovrapposta: `<main>` si accorcia della
 *  sua altezza invece di finirle sotto, e la pagina non salta quando compare.
 *  L'area sicura in fondo vale zero finche' il viewport non chiede
 *  `viewport-fit=cover`, e la barra e' gia' pronta se un giorno lo chiedera'. */
export function BarraInferiore({ onAltro, altroAperto }: { onAltro: () => void; altroAperto: boolean }) {
  const voce = "flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[0.7059rem] font-medium";
  return (
    <nav
      aria-label="Navigazione principale"
      className="shrink-0 border-t bg-background pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      <div className="flex">
        {NAV_PRIMARIE.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(voce, isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground")
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cn("h-5 w-5", isActive && "text-primary")} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
        <button
          type="button"
          onClick={onAltro}
          aria-expanded={altroAperto}
          aria-haspopup="dialog"
          className={cn(voce, "text-muted-foreground hover:text-foreground")}
        >
          <Menu className="h-5 w-5" />
          <span>Altro</span>
        </button>
      </div>
    </nav>
  );
}
