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
 *  ⚠️ E' `fixed`, con uno spaziatore della stessa altezza NEL flusso
 *  (2026-11-22). Stava solo nel flusso di una colonna alta 100dvh: appena
 *  qualcosa allungava il documento, il documento scorreva e la barra usciva
 *  dallo schermo senza tornare (segnalato su un Galaxy S26+). Fissa, nessuno
 *  scorrimento la porta via; lo spaziatore accorcia `<main>` come prima, quindi
 *  niente finisce sotto la barra e la pagina non salta.
 *
 *  Il viewport chiede `viewport-fit=cover`: su Android a tutto schermo la
 *  pagina arriva sotto i tre bottoni di sistema, e `safe-area-inset-bottom` ne
 *  porta l'altezza. Barra e spaziatore la aggiungono sotto le voci. */
export function BarraInferiore({ onAltro, altroAperto }: { onAltro: () => void; altroAperto: boolean }) {
  const voce = "flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[0.7059rem] font-medium";
  return (
    <>
    <div aria-hidden className="box-content h-14 shrink-0 pb-[env(safe-area-inset-bottom)] lg:hidden" />
    <nav
      aria-label="Navigazione principale"
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background pb-[env(safe-area-inset-bottom)] lg:hidden"
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
    </>
  );
}
