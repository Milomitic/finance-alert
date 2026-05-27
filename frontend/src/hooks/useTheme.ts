import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";

/** Read the persisted theme; default to light (the app is light-first).
 *  A tiny inline script in index.html applies this before first paint to
 *  avoid a flash — this hook then keeps React state in sync with the DOM. */
function readStored(): Theme {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* private mode / no storage — fall through to default */
  }
  return "light";
}

function applyTheme(t: Theme): void {
  // Tailwind is configured with darkMode: ["class"], so toggling the `dark`
  // class on <html> flips every `dark:` variant across the app.
  document.documentElement.classList.toggle("dark", t === "dark");
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
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
