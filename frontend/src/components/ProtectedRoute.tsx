import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useMe } from "@/hooks/useAuth";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { data, isLoading, isError } = useMe();
  if (isLoading) {
    return <div className="p-8 text-sm text-muted-foreground">Caricamento…</div>;
  }
  if (isError || !data) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
