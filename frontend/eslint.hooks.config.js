import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

/* CI gate for SEVEN rules: rules-of-hooks, static-components,
 * set-state-in-effect, exhaustive-deps, refs, purity, immutability.
 *
 * Why a second config instead of putting `npm run lint` in the pipeline. The
 * full config reported 60 findings on 2026-09-09 and reports **34** today
 * (only-export-components 25, refs 5, e un falso positivo di rules-of-hooks in
 * `e2e/`, escluso qui sotto). Gating on all of them would block every deploy
 * for reasons unrelated to the change being deployed, so it would be switched
 * off within a week. Cleaning them up is worth doing, and is a separate job.
 *
 * `@typescript-eslint/no-unused-vars` reached ZERO on 2026-09-09 and is
 * deliberately NOT gated here, which is worth recording because the temptation
 * was real. Nine of its findings were placeholders the codebase already marks
 * with a leading underscore (`_`, `_band`, `_opts`) and the fix was to
 * configure the rule to read that convention, not to rename the code. But an
 * unused variable breaks nothing a user can feel, and that is the second half
 * of the bar below. Being at zero earns a rule consideration, not entry.
 *
 * rules-of-hooks is not in that category. A hook called conditionally is not a
 * style opinion: React identifies hooks by call order, so the violation throws
 * during render, and a throw during render with no boundary above it unmounts
 * the entire app. That is exactly what happened — `useIsPhone()` sat after an
 * early return in RunProgressToast and the dashboard went blank whenever a scan
 * started or finished.
 *
 * The rule was installed and enabled the whole time. It simply never ran
 * anywhere that could stop a merge. Nothing else catches it: it typechecks, it
 * builds, and a test only sees it if it renders the component in BOTH branch
 * states (see RunProgressToast.test.tsx).
 *
 * static-components was added on 2026-09-08, and the bar it had to clear was
 * the one in the paragraph above: NO NOISE. It reported 7 violations, 6 of
 * them a real defect and 1 a false positive, and it now reports 0 — so a red
 * result here still means something is genuinely broken, which is the only
 * property that keeps a gate switched on.
 *
 * It is not a style rule either. A component declared inside another
 * component's body is a new TYPE every render, and React reconciles by type:
 * it destroys the subtree and builds a new one. The pixels are identical, so a
 * mouse sees nothing. Focus lives on a node, and the node is gone — tab to a
 * tool in DrawingToolbar, press Enter, and you are on <body>. The two
 * offenders (DrawingToolbar, CalendarPage's ViewToggle) were both toggle
 * groups, i.e. controls whose whole job is to be pressed, so the remount was
 * triggered by the very click it punished.
 *
 * The false positive is worth knowing before adding the next disable:
 * `const Icon = getSectorIcon(x)` is a LOOKUP into a module-level map, so the
 * reference is stable, but the rule sees a capitalized local const used as JSX
 * and cannot tell. There is exactly one such disable, in SectorDetailPage.
 *
 * Keep this list short, and add to it only on the same terms: the rule must be
 * at zero when you gate it, and a violation must break something a user can
 * feel. The other v7 rules (exhaustive-deps, set-state-in-effect, purity) are
 * still ~50 findings and still a separate job.
 *
 * ─── set-state-in-effect ed exhaustive-deps, aggiunte il 2026-09-13 ──────
 *
 * Erano 14 e 8. Sono state portate a ZERO prima di entrare qui, che e' la
 * condizione che questo file si e' dato fin dall'inizio: un cancello che nasce
 * rosso non distingue «hai rotto qualcosa adesso» da «esiste un arretrato», e
 * viene spento entro una settimana.
 *
 * L'altra meta' della barra e' che una violazione rompa qualcosa che un utente
 * SENTE. Non e' stata data per buona: e' stata verificata caso per caso
 * durante la pulizia, e le due regole l'hanno superata con difetti veri.
 *
 * `set-state-in-effect` — scrivere stato dentro un effect significa che React
 * ha gia' DIPINTO il render precedente. Il fotogramma sbagliato esiste:
 *
 *   - il logo del titolo PRECEDENTE accanto al nome nuovo, in una tabella che
 *     scorre (StockLogo);
 *   - il cassetto del menu che lampeggia sopra la pagina di destinazione
 *     (Layout);
 *   - un conto alla rovescia del breaker sbagliato di minuti (DataSourcesCard);
 *   - e il caso che non e' estetico: nella ricerca, la riga evidenziata era
 *     l'ennesima di una lista gia' accorciata — premere Invio in quel
 *     fotogramma apriva il TITOLO SBAGLIATO (NavbarSearch).
 *
 * `exhaustive-deps` — qui la regola ha trovato due difetti che nessuno aveva
 * notato, ed e' la prova migliore che non e' rumore:
 *
 *   - in `MacdPanel` lo spessore si applicava alla sola linea MACD e non a
 *     quella del segnale, quindi due linee dello stesso pannello divergevano;
 *   - in `MarketChart` l'orologio sull'asse veniva impostato SOLO alla
 *     creazione: passando a un intervallo intraday le etichette restavano
 *     con la sola data. Un asse con sole date non sembra rotto — e' la forma
 *     «plausibile e quindi creduta» che CLAUDE.md registra altrove.
 *
 * ⚠️ E va detto come NON si soddisfano, perche' entrambe si possono chiudere
 * in un modo che peggiora il codice:
 *
 *   - `exhaustive-deps` non si chiude aggiungendo l'oggetto mancante alle
 *     dipendenze. Nei grafici avrebbe DISTRUTTO e ricostruito l'intero
 *     grafico a ogni cambio di colore, perdendo zoom e posizione. Si chiude
 *     facendo leggere al corpo dell'effetto solo cio' che dichiara — si
 *     estrae la fetta fuori;
 *   - `set-state-in-effect` non si chiude spostando la scrittura in render se
 *     il valore e' impuro: il primo tentativo su `DataSourcesCard` leggeva
 *     `Date.now()` in render e `react-hooks/purity` l'ha respinto. Li' la
 *     risposta era rimontare con una `key`.
 *
 * ⚠️ Una trappola specifica dell'aggiornamento in render, trovata da un test e
 * non a ragionamento: un effect gira ANCHE al primo montaggio, mentre un
 * aggiornamento in render guardato da `prec !== corrente` no, se si
 * inizializza `prec` col valore corrente. Dove il montaggio conta (LogStream,
 * PriceAlertDialog) la guardia parte da una sentinella.
 *
 * ─── refs, purity, immutability, e cio' che NON e' entrato (2026-09-13) ──
 *
 * Tutte e tre erano gia' a zero o ci sono state portate, e appartengono alla
 * stessa famiglia: descrivono cosa rende un render RIPETIBILE. React puo'
 * renderizzare in modo speculativo e scartare il risultato, quindi un render
 * che legge un ref, che legge l'orologio o che muta un oggetto puo' produrre
 * due esiti diversi per lo stesso stato. Non e' teoria: `purity` ha respinto
 * una correzione scritta in questa stessa sessione — un `Date.now()` in
 * render, messo li' per togliere un `set-state-in-effect` — e aveva ragione.
 * La risposta giusta era rimontare il componente con una `key`.
 *
 * ⚠️ `react-refresh/only-export-components` e' a ZERO (era 25) e NON e'
 * entrata, deliberatamente.
 *
 * Rompe il Fast Refresh: modificando un file che esporta un componente E
 * altro, Vite ricarica la pagina invece di sostituire il componente. Costa a
 * chi SVILUPPA, non a chi usa — e la seconda meta' della barra di questo file
 * dice che una violazione deve rompere qualcosa che un utente sente. E' la
 * stessa ragione per cui `no-unused-vars` sta fuori pur essendo a zero da
 * settembre: essere a zero merita una CONSIDERAZIONE, non l'ingresso.
 *
 * Il rischio noto e accettato e' che i 25 tornino. Se un giorno tornassero,
 * la scelta e' fra ammettere la regola cambiando la barra — dichiarandolo — e
 * rifare la pulizia; non fra ammetterla di nascosto e fingere che la barra
 * sia sempre stata questa.
 *
 * ⚠️ E NON e' stato gatto `npm run lint` per intero, benche' oggi sia a zero.
 * Un gate su una config che segue le `recommended` di un plugin diventa rosso
 * quando il plugin aggiunge una regola — cioe' su una decisione di qualcun
 * altro, su codice che nessuno ha toccato. E' esattamente la forma che questo
 * file esiste per evitare. Le regole si nominano una per una.
 */
export default defineConfig([
  /* `e2e/` non contiene React.
   *
   * ⚠️ Va escluso, non silenziato riga per riga: Playwright passa alle sue
   * fixture una funzione chiamata `use`, e `rules-of-hooks` la legge come un
   * hook React chiamato fuori da un componente. E' un falso positivo
   * strutturale — si ripresenterebbe a ogni nuova fixture — e disattivare la
   * regola sul posto insegnerebbe a farlo anche dove conta. La cartella gira
   * in Node sotto Playwright, dove nessuna regola dei hook ha significato. */
  globalIgnores(['dist', 'e2e']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [tseslint.configs.base],
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/static-components': 'error',
      'react-hooks/set-state-in-effect': 'error',
      'react-hooks/exhaustive-deps': 'error',
      'react-hooks/refs': 'error',
      'react-hooks/purity': 'error',
      'react-hooks/immutability': 'error',
    },
    plugins: { 'react-hooks': reactHooks },
    // The `eslint-disable` comments scattered around the codebase target rules
    // this config does not enable, so eslint would flag every one of them as
    // unused — ~10 warnings that mean nothing here and would train everyone to
    // ignore this gate's output. The full config still checks them.
    linterOptions: { reportUnusedDisableDirectives: 'off' },
  },
])
