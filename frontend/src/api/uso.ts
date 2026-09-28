import { api } from "@/api/client";

/** Una pagina aperta (FA-114). Il server riduce il percorso a una forma di
 *  cardinalita' limitata (`app/core/rotte.py`): qui passa il percorso vero.
 *  `keepalive` perche' la chiamata sopravviva a una navigazione immediata. */
export function registraPagina(path: string, vista: string | null): Promise<unknown> {
  return api("/api/uso/pagina", {
    method: "POST",
    body: JSON.stringify({ path, vista }),
    keepalive: true,
  });
}
