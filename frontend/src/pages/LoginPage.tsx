import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLogin, useMe } from "@/hooks/useAuth";

/**
 * The login form is a plain controlled form on purpose (perf). It used to pull
 * react-hook-form + zod + @hookform/resolvers just to enforce "field not empty"
 * — and those three libs were used NOWHERE else in the app, so they weighed down
 * the very first, unauthenticated paint for two required fields. A couple of
 * useState hooks do the same job with none of the weight.
 */
export default function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [attempted, setAttempted] = useState(false);

  useEffect(() => {
    if (me.data) navigate("/", { replace: true });
  }, [me.data, navigate]);

  // Errors only show after a submit attempt (same UX as the old onSubmit mode).
  const usernameError = attempted && !username ? "Inserisci lo username" : null;
  const passwordError = attempted && !password ? "Inserisci la password" : null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (!username || !password) return;
    try {
      await login.mutateAsync({ username, password });
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        toast.error("Credenziali non valide");
      } else {
        toast.error("Errore durante il login");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Accedi a Finance Alert</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                aria-invalid={!!usernameError}
              />
              {usernameError && <p className="text-xs text-destructive">{usernameError}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!passwordError}
              />
              {passwordError && <p className="text-xs text-destructive">{passwordError}</p>}
            </div>
            <Button type="submit" disabled={login.isPending}>
              {login.isPending ? "Accesso in corso…" : "Accedi"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
