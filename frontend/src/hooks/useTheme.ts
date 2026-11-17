import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";

/** Il tema salvato; senza una scelta salvata, quello del sistema (E-28).
 *  `public/theme-init.js` fa lo stesso prima del primo disegno, per evitare il
 *  lampo: questo hook tiene lo stato React allineato al DOM. */
function readStored(): Theme {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* private mode / no storage — fall through to the system */
  }
  try {
    if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark";
  } catch {
    /* matchMedia assente (jsdom): chiaro */
  }
  return "light";
}

/** Applica il tema al DOM. Non lo salva: finche' l'utente non sceglie, il
 *  tema segue il sistema, e salvarlo all'apertura lo congelerebbe. */
function applyTheme(t: Theme): void {
  // Tailwind is configured with darkMode: ["class"], so toggling the `dark`
  // class on <html> flips every `dark:` variant across the app.
  document.documentElement.classList.toggle("dark", t === "dark");
  // La barra del browser segue il tema della pagina, non un colore fisso.
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t === "dark" ? "#121212" : "#ffffff");
}

function persist(t: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, t);
  } catch {
    /* non-fatal: just don't persist */
  }
}

/** Light/dark theme with localStorage persistence. `toggle()` flips it and
 *  applies the `dark` class on <html>. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(readStored);

  // Sync the DOM class to state on mount (covers the case where the pre-paint
  // script didn't run, e.g. SSR/dev edge cases) and on any external change.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      persist(next);
      return next;
    });
  }, []);

  return { theme, toggle };
}
