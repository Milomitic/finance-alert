import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DeployHealth } from "@/api/platformHealth";

import DataHealthCard from "./DataHealthCard";

/* ─── La data delle patch a schermo, e i suoi TRE stati ───────────────────
 *
 * Il 12 settembre 2026 il livello Docker che scarica le patch di sicurezza
 * Debian e' risultato inerte da 24 giorni: buildkit ne riusava la cache perche'
 * il comando non nominava niente di variabile. Nessuna superficie dell'app lo
 * mostrava, quindi si e' scoperto solo quando trivy ha rotto la pipeline con
 * tre CVE CRITICAL gia' corrette a monte.
 *
 * ⚠️ Il test che conta e' quello sullo stato IGNOTO. «Stantia» e «fresca» sono
 * facili; il modo di sbagliare questa scheda e' far sembrare fresca
 * un'immagine che semplicemente non dichiara la data — cioe' collassare tre
 * stati su due, che e' la distinzione fra assenza e zero che il repo applica
 * ovunque. */

function deploy(over: Partial<DeployHealth> = {}): DeployHealth {
  return {
    git_sha: "9458682c401a57b8f8fd13070a80d601442960ed",
    uptime_seconds: 120,
    started_at: "2026-09-12T14:50:00Z",
    image_built_at: "2026-09-12T14:39:33Z",
    apt_security_date: "2026-09-12",
    apt_age_days: 0,
    apt_stale: false,
    ...over,
  };
}

describe("DataHealthCard — patch di sicurezza", () => {
  it("mostra la data e quanto e' vecchia", () => {
    render(<DataHealthCard data={null} deploy={deploy()} />);
    expect(screen.getByText("Patch sicurezza")).toBeInTheDocument();
    expect(screen.getByText(/2026-09-12/)).toBeInTheDocument();
    expect(screen.getByText(/oggi/)).toBeInTheDocument();
  });

  it("un'immagine fresca NON porta l'avviso", () => {
    /* Controllo negativo dell'asserzione successiva: senza questo, una scheda
     * che stampa sempre l'avviso passerebbe il test sullo stato stantio. */
    render(<DataHealthCard data={null} deploy={deploy({ apt_age_days: 2 })} />);
    expect(screen.queryByText(/ricostruisce l'immagine/)).not.toBeInTheDocument();
    expect(screen.getByText(/2 giorni fa/)).toBeInTheDocument();
  });

  it("un'immagine stantia lo dice, e dice cosa fare", () => {
    render(
      <DataHealthCard
        data={null}
        deploy={deploy({ apt_security_date: "2026-08-19", apt_age_days: 24, apt_stale: true })}
      />,
    );
    expect(screen.getByText(/24 giorni fa/)).toBeInTheDocument();
    /* Un avviso che non dice l'azione e' un avviso che si impara a ignorare. */
    expect(screen.getByText(/ricostruisce l'immagine/)).toBeInTheDocument();
  });

  it("⚠️ una data IGNOTA non si traveste da fresca", () => {
    render(
      <DataHealthCard
        data={null}
        deploy={deploy({ apt_security_date: null, apt_age_days: null, apt_stale: null })}
      />,
    );
    expect(screen.getByText("non dichiarate")).toBeInTheDocument();
    // Ne' "oggi", ne' "0 giorni fa": assente non e' zero.
    expect(screen.queryByText(/oggi/)).not.toBeInTheDocument();
    expect(screen.queryByText(/0 giorni fa/)).not.toBeInTheDocument();
  });

  it("una risposta senza i campi nuovi non rompe la scheda", () => {
    /* Retrocompatibilita': durante un rollout il pod vecchio serve ancora il
     * payload senza questi campi, e la scheda deve reggerlo. */
    const vecchio = {
      git_sha: "abc1234", uptime_seconds: 10, started_at: null,
    } as unknown as DeployHealth;
    render(<DataHealthCard data={null} deploy={vecchio} />);
    expect(screen.getByText("non dichiarate")).toBeInTheDocument();
  });
});
