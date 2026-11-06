"""Server MCP locale di Finance Alert: SOLA LETTURA sull'API di produzione.

Gira sul PC dell'utente (trasporto stdio) e parla con l'app in HTTPS con un
token di sola lettura. Il backend accetta il token solo su GET/HEAD
(`api/deps._utente_da_token`), quindi nessuno strumento di qui puo' scrivere,
nemmeno per sbaglio: la garanzia sta sul server, non in questo file.

Configurazione:
- `FINANCE_ALERT_URL`        default https://80-225-80-141.sslip.io
- `FINANCE_ALERT_TOKEN_FILE` default ~/.finance-alert/mcp-token (il token in
                             chiaro, solo su questo PC, mai nel repository)

⚠️ Se ogni chiamata scade senza risposta, quasi certamente l'IP di casa e'
cambiato e la 443 non e' piu' nell'allowlist di OCI: vedi CLAUDE.md, «L'app non
si apre da casa».
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

URL = os.environ.get("FINANCE_ALERT_URL", "https://80-225-80-141.sslip.io").rstrip("/")
FILE_TOKEN = Path(os.environ.get("FINANCE_ALERT_TOKEN_FILE", Path.home() / ".finance-alert" / "mcp-token"))

#: Chiavi che pesano molto e non servono a una risposta in chat: serie di
#: prezzi, indicatori, storici. Si tolgono prima di restituire.
CHIAVI_PESANTI = frozenset({
    "ohlcv", "indicators", "history", "series", "sparkline", "chart", "bars",
    "storico_consenso", "closes", "points", "overlay", "chain_events",
})
MAX_LISTA = 25


class ErroreApp(RuntimeError):
    """Un errore da mostrare in chat, gia' in parole."""


def leggi_token(percorso: Path = FILE_TOKEN) -> str:
    try:
        token = percorso.read_text(encoding="utf-8").strip()
    except FileNotFoundError as e:
        raise ErroreApp(f"Token non trovato in {percorso}: crealo come descritto in mcp/README.md.") from e
    if not token:
        raise ErroreApp(f"Il file del token {percorso} e' vuoto.")
    return token


def chiama(percorso: str, parametri: dict[str, Any] | None = None, *, client: httpx.Client | None = None,
           timeout: float = 30.0) -> Any:
    """GET sull'API, con gli errori tradotti in frasi utili."""
    parametri = {k: v for k, v in (parametri or {}).items() if v is not None}
    proprio = client is None
    c = client or httpx.Client(base_url=URL, timeout=timeout,
                               headers={"Authorization": f"Bearer {leggi_token()}"})
    try:
        r = c.get(percorso, params=parametri)
    except httpx.TimeoutException as e:
        raise ErroreApp(
            "L'app non risponde (tempo scaduto). Se succede a ogni chiamata, probabilmente l'IP "
            "di casa e' cambiato ed e' fuori dall'allowlist della porta 443 su OCI."
        ) from e
    except httpx.HTTPError as e:
        raise ErroreApp(f"Connessione all'app fallita: {e}") from e
    finally:
        if proprio:
            c.close()
    if r.status_code == 401:
        raise ErroreApp("Token rifiutato (401): controlla il file del token e MCP_TOKEN_SHA256 nel Secret.")
    if r.status_code == 404:
        raise ErroreApp(f"Non trovato: {percorso}")
    if r.status_code >= 400:
        raise ErroreApp(f"L'app ha risposto {r.status_code} su {percorso}: {r.text[:300]}")
    return r.json()


def sfoltisci(x: Any, profondita: int = 0) -> Any:
    """Toglie le serie pesanti e accorcia le liste lunghe, dichiarandolo."""
    if isinstance(x, dict):
        return {k: sfoltisci(v, profondita + 1) for k, v in x.items() if k not in CHIAVI_PESANTI}
    if isinstance(x, list):
        corta = [sfoltisci(v, profondita + 1) for v in x[:MAX_LISTA]]
        if len(x) > MAX_LISTA:
            corta.append(f"... altri {len(x) - MAX_LISTA} elementi non mostrati")
        return corta
    return x


def riassumi_segnale(a: dict[str, Any]) -> dict[str, Any]:
    """Un segnale in una riga. Data, prezzo, Forza e orizzonte sono quelli
    dell'EMISSIONE (`first_*`), non dell'ultima revisione: vedi CLAUDE.md,
    «Un alert e' una riga VIVA»."""
    s = a.get("snapshot") or {}
    nato = s.get("first_emitted_at") or a.get("triggered_at")
    rule = a.get("rule_kind") or ""
    return {
        "id": a.get("id"),
        "comparso_il": (nato or "")[:10] or None,
        "barra_del_segnale": a.get("signal_date"),
        "ticker": a.get("ticker"),
        "nome": a.get("name"),
        "detector": rule.split(":", 1)[1] if rule.startswith("signal:") else rule,
        "tono": s.get("tone"),
        "forza": s.get("first_strength", s.get("strength")),
        "orizzonte": s.get("first_horizon", s.get("horizon")),
        "prezzo_ingresso": s.get("first_price", a.get("trigger_price")),
        "valuta": a.get("currency"),
        "archiviato": a.get("archived_at") is not None,
    }


mcp = MCPServer(
    name="finance-alert",
    instructions=(
        "Dati di Finance Alert, l'app personale dell'utente: segnali tecnici, punteggi, "
        "fondamentali, notizie, calendario macro e trimestrali, posizioni eToro, esiti del motore. "
        "Tutto in sola lettura. I segnali sono un filtro d'attenzione, non previsioni: gli studi "
        "del progetto non hanno trovato vantaggio direzionale dimostrato. Non dare consigli "
        "d'investimento personalizzati a partire da questi dati."
    ),
)
SOLA_LETTURA = ToolAnnotations(read_only_hint=True, idempotent_hint=True, destructive_hint=False)


@mcp.tool(annotations=SOLA_LETTURA)
def salute() -> dict[str, Any]:
    """Stato dell'app in produzione: salute, versione, scansione in corso."""
    return chiama("/api/health")


@mcp.tool(annotations=SOLA_LETTURA)
def segnali(ticker: str | None = None, giorni: int = 7, tono: str | None = None,
            solo_miei: bool = False, limite: int = 30) -> dict[str, Any]:
    """Segnali emessi negli ultimi `giorni`, dal piu' recente.

    ticker: filtra un titolo (es. "AAPL"). tono: "bull" o "bear".
    solo_miei: solo titoli in posizione o fra i preferiti.
    """
    dal = (date.today() - timedelta(days=max(1, giorni))).isoformat()
    d = chiama("/api/alerts", {"ticker": ticker, "date_from": dal, "tone": tono,
                               "solo_rilevanti": solo_miei or None, "limit": min(max(1, limite), 200)})
    return {"totale": d.get("total"), "altri": d.get("has_more"),
            "segnali": [riassumi_segnale(a) for a in d.get("items", [])]}


@mcp.tool(annotations=SOLA_LETTURA)
def segnale(alert_id: int) -> dict[str, Any]:
    """Il dettaglio di un segnale: catena, fattori, livelli, piano."""
    return sfoltisci(chiama(f"/api/alerts/{alert_id}"))


@mcp.tool(annotations=SOLA_LETTURA)
def titolo(ticker: str) -> dict[str, Any]:
    """Scheda di un titolo: anagrafica, prezzo, Stock score (qualita') e
    valutazione tecnica. Senza serie storiche."""
    t = ticker.strip().upper()
    out: dict[str, Any] = {"dettaglio": sfoltisci(chiama(f"/api/stocks/{t}/detail"))}
    for chiave, percorso in (("stock_score", f"/api/stocks/{t}/score"),
                             ("tecnico", f"/api/stocks/{t}/technical")):
        try:
            out[chiave] = sfoltisci(chiama(percorso))
        except ErroreApp as e:
            out[chiave] = str(e)
    return out


@mcp.tool(annotations=SOLA_LETTURA)
def fondamentali(ticker: str) -> Any:
    """Bilancio annuale e trimestrale, risultati con le stime, prossima trimestrale."""
    return sfoltisci(chiama(f"/api/stocks/{ticker.strip().upper()}/fundamentals"))


@mcp.tool(annotations=SOLA_LETTURA)
def notizie(ticker: str, quante: int = 10) -> Any:
    """Le notizie piu' recenti di un titolo."""
    return sfoltisci(chiama(f"/api/stocks/{ticker.strip().upper()}/news",
                            {"limit": min(max(1, quante), 25)}))


@mcp.tool(annotations=SOLA_LETTURA)
def posizioni_etoro() -> dict[str, Any]:
    """Il conto eToro: valore, margine e posizioni aperte (sola lettura)."""
    d = chiama("/api/etoro/portafoglio")
    return {"configurato": d.get("configurato"), "conto": d.get("conto"),
            "aperte": sfoltisci(d.get("aperte") or [])}


@mcp.tool(annotations=SOLA_LETTURA)
def calendario(giorni: int = 7, tipo: str | None = None) -> Any:
    """Calendario dei prossimi `giorni`. tipo: "macro" o "earnings" (trimestrali)."""
    oggi = date.today()
    return sfoltisci(chiama("/api/calendar", {
        "from": oggi.isoformat(), "to": (oggi + timedelta(days=min(max(1, giorni), 60))).isoformat(),
        "kinds": tipo}))


@mcp.tool(annotations=SOLA_LETTURA)
def prestazioni_detector() -> Any:
    """Gli esiti dei segnali per detector, al netto del mercato, con i campioni.
    Leggere l'intervallo, non il solo tasso: le finestre indipendenti sono poche."""
    return sfoltisci(chiama("/api/platform/detector-performance"))


@mcp.tool(annotations=SOLA_LETTURA)
def esiti_piani() -> Any:
    """Gli esiti dei piani (stop contro target, in multipli di R) per detector."""
    return sfoltisci(chiama("/api/platform/plan-performance"))


#: I simboli non-azionari che l'app sa servire (`LIVE_ASSET_DEFINITIONS` in
#: backend/app/api/market.py, piu' i futures sugli indici). Il backend rifiuta
#: gli altri di proposito: qui servono solo a dire cosa chiedere.
SIMBOLI_MERCATO = (
    "^GSPC (S&P 500), ^IXIC (Nasdaq Composite), ^DJI (Dow Jones), ^VIX, ^N225 (Nikkei), "
    "^STOXX50E (Euro Stoxx 50), FTSEMIB.MI, ^HSI (Hang Seng), 000300.SS (CSI 300), "
    "GC=F (oro), SI=F (argento), CL=F (WTI), NG=F (gas), BTC-USD, ETH-USD, "
    "futures sugli indici ES=F, NQ=F, YM=F, NKD=F"
)
COLONNE_STORICO = ("data", "apertura", "massimo", "minimo", "chiusura", "volume")
#: Dieci anni di analisi piu' uno per scaldare una media a 200 sedute.
ANNI_DEFAULT = 11


def _riga(b: dict[str, Any], solo_chiusure: bool) -> list[Any]:
    d = str(b["date"])[:10]
    if solo_chiusure:
        return [d, round(float(b["close"]), 4)]
    return [d, *(round(float(b[k]), 4) for k in ("open", "high", "low", "close")), b.get("volume")]


def leggi_storico(simbolo: str, dal: str | None = None, al: str | None = None,
                  solo_chiusure: bool = False) -> dict[str, Any]:
    """Il corpo di `storico`, separato perche' i test lo chiamino senza MCP.

    Prima il catalogo (azioni, nel database dell'app), poi i mercati: il
    catalogo risponde una lista VUOTA a un simbolo che non conosce, e
    l'endpoint dei mercati rende tutta la storia, quindi l'intervallo di date
    si applica qui."""
    s = simbolo.strip().upper()
    oggi = date.today()
    dal = dal or date(oggi.year - ANNI_DEFAULT, oggi.month, 1).isoformat()
    barre = chiama(f"/api/stocks/{s}/ohlcv", {"dal": dal, "al": al}, timeout=60.0)
    fonte = "catalogo (database dell'app)"
    if not barre:
        try:
            d = chiama(f"/api/markets/{s}/detail", {"range": "1d"}, timeout=120.0)
        except ErroreApp as e:
            raise ErroreApp(
                f"{s} non e' un titolo del catalogo ne' un mercato servito dall'app. "
                f"Mercati disponibili: {SIMBOLI_MERCATO}. ({e})"
            ) from e
        barre = [b for b in d.get("bars") or []
                 if str(b["date"])[:10] >= dal and (al is None or str(b["date"])[:10] <= al)]
        fonte = "mercati (yfinance, storia completa)"
    righe = [_riga(b, solo_chiusure) for b in barre]
    return {
        "simbolo": s, "fonte": fonte, "barre": len(righe),
        "dal": righe[0][0] if righe else None, "al": righe[-1][0] if righe else None,
        "colonne": ["data", "chiusura"] if solo_chiusure else list(COLONNE_STORICO),
        "righe": righe,
    }


@mcp.tool(annotations=SOLA_LETTURA)
def storico(simbolo: str, dal: str | None = None, al: str | None = None,
            solo_chiusure: bool = False) -> dict[str, Any]:
    """Serie storica GIORNALIERA di un titolo o di un mercato, per statistiche sul passato.

    simbolo: un ticker del catalogo (AAPL, UCG.MI, 0700.HK...: ~10 anni nel
    database dell'app) oppure un mercato: ^GSPC, ^IXIC, ^DJI, ^VIX, ^N225,
    ^STOXX50E, FTSEMIB.MI, ^HSI, 000300.SS, GC=F, SI=F, CL=F, NG=F, BTC-USD,
    ETH-USD, ES=F, NQ=F, YM=F, NKD=F (storia completa: il Nasdaq dal 1971).
    dal / al: date ISO, incluse. Senza `dal`: gli ultimi ~11 anni, cioe' dieci
    di analisi piu' le sedute che scaldano una media a 200 giorni.
    solo_chiusure: solo data e chiusura, risposta piu' leggera.

    Le serie lunghe sono migliaia di righe: elaborarle con codice (Python) sul
    file in cui il client salva la risposta, non a occhio. Medie mobili e ogni
    altra statistica si calcolano su queste barre.
    """
    return leggi_storico(simbolo, dal, al, solo_chiusure)


if __name__ == "__main__":
    mcp.run()
