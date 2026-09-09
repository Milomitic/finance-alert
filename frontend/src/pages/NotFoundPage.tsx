import { ArrowLeft, Home, SearchX } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";

/** Friendly fallback for unknown routes. Keeps a direct link to the dashboard
 * and lets the user return without relying on browser chrome. */
export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-12">
      <div className="w-full max-w-md space-y-5 text-center">
        <SearchX className="mx-auto h-12 w-12 text-muted-foreground" aria-hidden="true" />
        <div className="space-y-2">
          <p className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Errore 404</p>
          <h1 className="text-2xl font-bold">Pagina non trovata</h1>
          <p className="text-sm text-muted-foreground">
            L’indirizzo potrebbe essere cambiato o non essere più disponibile.
          </p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          <Button variant="outline" onClick={() => navigate(-1)}>
            <ArrowLeft className="mr-1.5 h-4 w-4" /> Indietro
          </Button>
          <Button asChild>
            <Link to="/">
              <Home className="mr-1.5 h-4 w-4" /> Dashboard
            </Link>
          </Button>
        </div>
      </div>
    </main>
  );
}
