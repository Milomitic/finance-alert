import { useCallback, useEffect, useRef, useState } from "react";

/** Un'azione che non si annulla chiede un secondo tocco (C-70, C-44).
 *
 *  Il primo tocco arma, il secondo esegue; dopo `ms` senza il secondo tocco
 *  torna a riposo da solo. Niente `confirm()` del browser: interrompe la
 *  pagina, non si stila e su telefono copre tutto per una scelta da poco.
 *  Lo stato cambia solo nei gestori e nel timer, mai in un effetto. */
export function useConfermaInDuePassi(azione: () => void, ms = 4000): {
  armato: boolean;
  premi: () => void;
} {
  const [armato, setArmato] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const premi = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    if (armato) {
      timer.current = null;
      setArmato(false);
      azione();
      return;
    }
    setArmato(true);
    timer.current = setTimeout(() => {
      timer.current = null;
      setArmato(false);
    }, ms);
  }, [armato, azione, ms]);

  return { armato, premi };
}
