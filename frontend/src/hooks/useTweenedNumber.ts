import { useEffect, useRef, useState } from "react";

/**
 * Smoothly interpolate a numeric value toward a moving target using
 * requestAnimationFrame. Returns the current animated value.
 *
 * When `target` changes, kicks off a new tween from whatever value is
 * currently on screen (not from the previous target) — so chained
 * fast updates feel continuous rather than restart-jumpy.
 *
 * Easing: cubic ease-out (1 - (1-t)^3). Fast initial acceleration
 * with a gentle landing — feels "live data settling" rather than
 * "linear robot count-up".
 *
 * First-render behavior: snaps to the initial target with no tween,
 * because tweening from 0 to e.g. 173.45 on mount is visually noisy
 * and irrelevant to the user (the price was already that, you just
 * arrived on the page).
 *
 * Cleanup: cancels the in-flight RAF on unmount or new target so we
 * never have orphan animation loops driving a setState on unmounted
 * components.
 */
export function useTweenedNumber(
  target: number | null | undefined,
  durationMs = 350,
): number | null {
  const [shown, setShown] = useState<number | null>(
    target != null && Number.isFinite(target) ? target : null,
  );
  const animRef = useRef<number>(0);
  const fromRef = useRef<number>(0);
  const startRef = useRef<number>(0);
  const shownRef = useRef<number | null>(shown);
  shownRef.current = shown;

  /* ⚠️ Gli SNAP si fanno in fase di render, non dentro l'effect.
   *
   * Sono due: bersaglio assente -> niente da mostrare; primo valore (o ritorno
   * da `null`) -> si mostra subito, senza animazione. Nessuno dei due e'
   * un'animazione, sono aggiustamenti di stato a una prop che cambia — ed e'
   * il caso che React documenta per l'aggiornamento in render.
   *
   * La differenza non e' stilistica. Da dentro un effect React ha gia'
   * DIPINTO il render precedente: sullo schermo compare per un fotogramma il
   * valore vecchio (o uno zero) e poi salta a quello giusto. Aggiornando in
   * render, React scarta il risultato e ri-renderizza prima di dipingere:
   * quel fotogramma sbagliato non esiste. E' anche cio' che
   * `react-hooks/set-state-in-effect` intende per «renderizzazioni a
   * cascata».
   *
   * ⚠️ La guardia `target !== precedente` e' obbligatoria: senza, l'aggiorna-
   * mento in render si ri-innescherebbe a ogni passata e il render non
   * terminerebbe mai. */
  const [precedente, setPrecedente] = useState(target);
  if (target !== precedente) {
    setPrecedente(target);
    if (target == null || !Number.isFinite(target)) {
      setShown(null);
    } else if (shown == null) {
      setShown(target);
    }
  }

  useEffect(() => {
    // Gli snap sono gia' stati applicati in render; qui resta la sola
    // animazione. Questi due `return` non scrivono stato.
    if (target == null || !Number.isFinite(target)) return;
    if (shownRef.current == null) return;
    if (target === shownRef.current) return;

    fromRef.current = shownRef.current;
    startRef.current = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startRef.current;
      const t = Math.min(1, elapsed / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      const current = fromRef.current + (target - fromRef.current) * eased;
      if (t >= 1) {
        setShown(target);
        return;
      }
      setShown(current);
      animRef.current = requestAnimationFrame(tick);
    };

    cancelAnimationFrame(animRef.current);
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [target, durationMs]);

  return shown;
}
