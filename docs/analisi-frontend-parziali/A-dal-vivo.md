# A — Analisi dal vivo dell'interfaccia (desktop 1440px, mobile 375px)

Metodo: backend locale su :8000 e Vite su :5173, sessione coniata col firmatario dell'app,
browser integrato. Desktop 1440x900, mobile col preset 375x812 (`window.innerWidth` letto
dalla pagina). Su ogni pagina e' stato eseguito uno script di misura (traboccamenti dentro
`<main>`, istogramma dei corpi carattere, contrasto calcolato, bersagli tattili, troncamenti)
oltre all'osservazione degli screenshot. Database locale, piu' vecchio della produzione.

## /login

### Desktop
- **[A-01] Corpi da 11px nel pannello sinistro** — Dove: /login, 1440px, eyebrow «OSSERVA. COLLEGA. APPROFONDISCI.», «AREA PERSONALE», sottotitoli delle tre voci, «Meno rumore. Piu' contesto.». Problema: quattro testi a 11,1px e uno a 11,6px, in grigio-verde su fondo quasi nero; su uno schermo da 1440px la colonna sinistra ha molto spazio libero e il testo piu' piccolo e' quello che spiega il prodotto. Perche' conta: e' la prima pagina che si vede e la parte descrittiva si legge a fatica. Proposta: portare i sottotitoli a 13px e l'eyebrow a 12px. Impatto: basso. Sforzo: S.
- **[A-02] Due frasi di chiusura che dicono la stessa cosa** — Dove: /login, 1440px, sotto la scheda («Il tuo punto di partenza per leggere il mercato.») e in fondo alla colonna sinistra («Meno rumore. Piu' contesto.»), piu' «Usa le credenziali del tuo account.» dentro la scheda. Problema: tre righe di contorno a 11px che non aggiungono informazione. Perche' conta: rumore attorno all'unica azione della pagina. Proposta: tenerne una. Impatto: basso. Sforzo: S.

### Mobile
- **[A-03] Blocco di accesso spinto in basso da 95px di vuoto in testa** — Dove: /login, 375px. Problema: il logo comincia a ~95px dall'alto e la scheda finisce a ~735px su 812: il pulsante «Accedi» sta a 640px, con la tastiera aperta finisce coperto. Perche' conta: su telefono si deve scorrere a tastiera aperta per premere Accedi. Proposta: ridurre il margine superiore a ~32px e compattare titolo «Il mercato, messo a fuoco.» (2 righe da 30px) in una riga piu' piccola. Impatto: medio. Sforzo: S.
- **[A-04] Motto a 10,2px** — Dove: /login, 375px, «Il tuo osservatorio sui mercati» sotto il logo. Problema: 10,2px con spaziatura larga. Perche' conta: sotto la soglia di leggibilita' su telefono. Proposta: 12px o toglierlo su mobile. Impatto: basso. Sforzo: S.
- Da preservare: pagina pulita, una sola azione, campi alti 52px, occhio mostra-password, nessun traboccamento.

