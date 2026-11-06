# Server MCP locale di Finance Alert

Server MCP in **sola lettura** sull'API di produzione, per usare i dati dell'app
dalla chat di Claude sul PC. Gira in locale (stdio); non c'e' niente da esporre
in rete.

## Strumenti

| Strumento | Cosa restituisce |
|---|---|
| `salute` | stato dell'app, versione, scansione in corso |
| `segnali` | segnali recenti, filtrabili per titolo, tono, solo i tuoi titoli |
| `segnale` | il dettaglio di un segnale: catena, fattori, piano |
| `titolo` | anagrafica, prezzo, Stock score, valutazione tecnica |
| `fondamentali` | bilancio, risultati con le stime, prossima trimestrale |
| `notizie` | notizie recenti di un titolo |
| `posizioni_etoro` | conto e posizioni aperte |
| `calendario` | macro e trimestrali dei prossimi giorni |
| `prestazioni_detector` | esiti dei segnali al netto del mercato, con i campioni |
| `esiti_piani` | esiti dei piani (stop contro target) in multipli di R |

## Sicurezza

- Il token e' di **sola lettura per costruzione**: il backend lo accetta solo su
  GET/HEAD e risponde 403 a qualunque altro metodo (`backend/app/api/deps.py`).
- In produzione c'e' solo l'**impronta** SHA-256 del token
  (`MCP_TOKEN_SHA256` nel Secret `finance-alert-prod`). Il token in chiaro sta
  solo in `~/.finance-alert/mcp-token` su questo PC, mai nel repository.
- Revoca: togliere `MCP_TOKEN_SHA256` dal Secret e riavviare il pod.
- Rotazione: nuovo token nel file, nuova impronta nel Secret, riavvio del pod.

## Configurazione

- `FINANCE_ALERT_URL`: default `https://80-225-80-141.sslip.io`
- `FINANCE_ALERT_TOKEN_FILE`: default `~/.finance-alert/mcp-token`

Claude Code lo trova da `.mcp.json` nella radice del repository. Per Claude
desktop si aggiunge lo stesso comando in `claude_desktop_config.json`, con
`--directory` assoluto.

⚠️ Se ogni chiamata scade, l'IP di casa e' probabilmente cambiato ed e' fuori
dall'allowlist della 443: vedi CLAUDE.md, «L'app non si apre da casa».

## Test

    cd mcp && uv run pytest -q
