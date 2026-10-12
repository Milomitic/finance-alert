import { cn } from "@/lib/utils";

/* Negoziabile su eToro, detto con un segno e non con un'etichetta
 * (richiesta dell'utente, 2026-10-12). Accanto al ticker, alla taglia della
 * stella dei preferiti: si nota se lo si cerca e non compete col nome.
 *
 * Due stati, perche' il dato c'e' sempre (`su_etoro` vale False di default):
 * pieno quando il titolo si negozia, spento e in grigio quando no. `su`
 * assente (un chiamante che non lo passa) non disegna niente: un segno grigio
 * direbbe «non c'e'» senza saperlo. */
export function EtoroMarchio({ su, className }: { su: boolean | undefined; className?: string }) {
  if (su == null) return null;
  const testo = su ? "Si negozia su eToro" : "Non negoziabile su eToro";
  return (
    <span
      className={cn("inline-flex shrink-0", !su && "opacity-35 grayscale", className)}
      title={testo}
      data-su-etoro={su ? "si" : "no"}
    >
      <svg viewBox="0 0 16 16" width={18} height={18} role="img" aria-label={testo}>
        <rect width="16" height="16" rx="4" fill={su ? "#13c636" : "#94a3b8"} />
        <text
          x="8"
          y="11.6"
          textAnchor="middle"
          fontSize="11"
          fontWeight="800"
          fontFamily="ui-sans-serif, system-ui, sans-serif"
          fill="#fff"
        >
          e
        </text>
      </svg>
    </span>
  );
}
