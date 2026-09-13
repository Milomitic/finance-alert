import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { InfraHealth } from "@/api/platformHealth";

import InfraCard from "./InfraCard";

/* ─── Un numero non e' una diagnosi ───────────────────────────────────────
 *
 * La scheda diceva «Target giù 1», «Alert attivi 2», «Riavvii 3» e teneva i
 * nomi dentro un attributo `title`. Su un telefono `title` non si apre mai, e
 * anche col mouse andava cercato: il risultato pratico era che ogni problema
 * mandava comunque a `kubectl`, cioe' esattamente cio' che la scheda esiste
 * per evitare. I riavvii non avevano nemmeno quello — solo il conteggio.
 *
 * ⚠️ Il test che conta di piu' e' l'ultimo: il blocco NON deve comparire
 * quando non c'e' niente da dire. Una sezione «nessun problema» sempre
 * presente e' rumore che si impara a saltare, e allora non la si legge
 * nemmeno quando si riempie.
 */

function infra(over: Partial<InfraHealth> = {}): InfraHealth {
  return {
    available: true,
    error: null,
    prometheus_url: "http://prom:9090",
    targets_up: 20,
    targets_down: 0,
    down_targets: [],
    alerts_firing: 0,
    firing_alerts: [],
    restarts_24h: 0,
    restart_details: [],
    memory_pct: 40,
    cert_days: 60,
    argocd: { sync: "Synced", health: "Healthy" },
    components: [],
    ...over,
  } as InfraHealth;
}

describe("InfraCard — dettagli dei problemi", () => {
  it("nomina l'alert, la severita', su cosa e cosa dice", () => {
    render(
      <InfraCard
        data={infra({
          alerts_firing: 1,
          firing_alerts: [{
            name: "KubePodCrashLooping",
            severity: "warning",
            since: new Date(Date.now() - 12 * 60_000).toISOString(),
            summary: "Il pod app riavvia in ciclo",
            target: "finance-alert-0",
          }],
        })}
      />,
    );
    expect(screen.getByText("KubePodCrashLooping")).toBeInTheDocument();
    expect(screen.getByText("warning")).toBeInTheDocument();
    expect(screen.getByText(/finance-alert-0/)).toBeInTheDocument();
    expect(screen.getByText("Il pod app riavvia in ciclo")).toBeInTheDocument();
    // «da 12m» risponde alla domanda che ci si fa davanti a un alert; un
    // istante ISO risponde a un'altra.
    expect(screen.getByText(/da 12m/)).toBeInTheDocument();
  });

  it("un alert senza annotazioni mostra comunque il nome", () => {
    /* ⚠️ `summary` e `since` vengono da `/api/v1/alerts`, che puo' non
     * rispondere. Il nome da solo e' meno utile, mai sbagliato — e la scheda
     * non deve rompersi ne' inventare un testo. */
    render(
      <InfraCard
        data={infra({
          alerts_firing: 1,
          firing_alerts: [{
            name: "TargetDown", severity: null, since: null,
            summary: null, target: null,
          }],
        })}
      />,
    );
    expect(screen.getByText("TargetDown")).toBeInTheDocument();
  });

  it("nomina il target giù con la sua istanza", () => {
    render(
      <InfraCard
        data={infra({
          targets_down: 1,
          down_targets: [
            { namespace: "monitoring", job: "kubelet", instance: "10.0.0.4:10250" },
          ],
        })}
      />,
    );
    expect(screen.getByText("monitoring/kubelet")).toBeInTheDocument();
    expect(screen.getByText("10.0.0.4:10250")).toBeInTheDocument();
  });

  it("dice QUALE contenitore si e' riavviato e PERCHE'", () => {
    render(
      <InfraCard
        data={infra({
          restarts_24h: 3,
          restart_details: [
            { pod: "finance-alert-0", container: "app", count: 3, reason: "OOMKilled" },
          ],
        })}
      />,
    );
    expect(screen.getByText("app")).toBeInTheDocument();
    expect(screen.getByText(/finance-alert-0/)).toBeInTheDocument();
    expect(screen.getByText("×3")).toBeInTheDocument();
    expect(screen.getByText("OOMKilled")).toBeInTheDocument();
  });

  it("⚠️ un motivo mancante non diventa «Unknown»", () => {
    /* Il motivo dell'ultima terminazione puo' mancare legittimamente: un pod
     * ricreato da zero non ne ha uno. Una parola inventata lo farebbe sembrare
     * letto — la stessa distinzione fra assenza e zero che il repo applica ai
     * numeri, applicata a una stringa. */
    render(
      <InfraCard
        data={infra({
          restarts_24h: 1,
          restart_details: [
            { pod: "finance-alert-0", container: "app", count: 1, reason: null },
          ],
        })}
      />,
    );
    expect(screen.getByText("motivo non registrato")).toBeInTheDocument();
    expect(screen.queryByText(/unknown/i)).not.toBeInTheDocument();
  });

  it("⚠️ con tutto a posto il blocco NON compare", () => {
    /* Il controllo negativo di tutti i test sopra: senza, una scheda che
     * disegna sempre le tre sezioni li passerebbe comunque. */
    render(<InfraCard data={infra()} />);
    expect(screen.queryByText("Alert attivi")).toBeInTheDocument(); // la metrica resta
    expect(screen.queryByText("Target giù")).toBeInTheDocument();
    // ...ma nessuna voce di dettaglio.
    expect(screen.queryByText("motivo non registrato")).not.toBeInTheDocument();
    expect(screen.queryByText("monitoring/kubelet")).not.toBeInTheDocument();
  });

  it("regge un payload senza il campo nuovo", () => {
    /* Durante un rollout il pod vecchio serve ancora un payload senza
     * `restart_details`. */
    const vecchio = { ...infra(), restarts_24h: 2 } as InfraHealth;
    delete (vecchio as Partial<InfraHealth>).restart_details;
    render(<InfraCard data={vecchio} />);
    expect(screen.getByText("Riavvii (24h)")).toBeInTheDocument();
  });
});
