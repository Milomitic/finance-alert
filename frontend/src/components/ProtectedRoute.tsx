import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useMe } from "@/hooks/useAuth";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { data, isLoading, isError } = useMe();
  const location = useLocation();
  if (isLoading) {
    // Lo stesso spinner del caricamento delle rotte (`App.tsx`): un solo
    // aspetto per lo stesso momento d'attesa.
    return (
      <div className="flex min-h-[40vh] items-center justify-center" role="status" aria-label="Caricamento">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (isError || !data) {
    // La pagina di partenza viaggia nello stato: dopo l'accesso si torna li'
    // (D-89), non sempre alla dashboard.
    return <Navigate to="/login" replace state={{ da: location }} />;
  }
  return <>{children}</>;
}
