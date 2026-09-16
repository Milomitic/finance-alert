import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { MemoryRouter, Route, Routes, useNavigate, useSearchParams } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useScrollRestoration } from "./useScrollRestoration";

/* Lo scorrimento di <main> segue la cronologia (collaudo in browser,
 * 2026-09-16: un titolo aperto da una lista scorsa partiva a meta' pagina, e
 * tornando indietro la lista stava in fondo). jsdom non fa layout, quindi la
 * posizione si imposta e si legge come proprieta'; lo scorrimento vero e' stato
 * misurato nel browser. */

function Shell() {
  const main = useRef<HTMLElement>(null);
  useScrollRestoration(main);
  const naviga = useNavigate();
  const [, setParams] = useSearchParams();
  return (
    <>
      <button type="button" onClick={() => naviga("/titolo")}>vai</button>
      <button type="button" onClick={() => naviga(-1)}>indietro</button>
      <button type="button" onClick={() => naviga(1)}>avanti</button>
      <button type="button" onClick={() => setParams({ tono: "ribassisti" }, { replace: true })}>
        filtra
      </button>
      <main ref={main} data-testid="main">
        <Routes>
          <Route path="/lista" element={<p>lista</p>} />
          <Route path="/titolo" element={<p>titolo</p>} />
        </Routes>
      </main>
    </>
  );
}

const premi = (nome: string) => fireEvent.click(screen.getByRole("button", { name: nome }));

function scorri(el: HTMLElement, y: number) {
  el.scrollTop = y;
  fireEvent.scroll(el);
}

describe("useScrollRestoration", () => {
  it("una pagina nuova parte dall'alto, e indietro ritrova la posizione", async () => {
    render(
      <MemoryRouter initialEntries={["/lista"]}>
        <Shell />
      </MemoryRouter>,
    );
    const main = screen.getByTestId("main");
    scorri(main, 2500);

    premi("vai");
    expect(main.scrollTop).toBe(0);
    scorri(main, 300);

    premi("indietro");
    await waitFor(() => expect(main.scrollTop).toBe(2500), { timeout: 3000 });

    premi("avanti");
    await waitFor(() => expect(main.scrollTop).toBe(300), { timeout: 3000 });
  });

  it("un cambio di filtro (replace) non sposta la vista", () => {
    render(
      <MemoryRouter initialEntries={["/lista"]}>
        <Shell />
      </MemoryRouter>,
    );
    const main = screen.getByTestId("main");
    scorri(main, 800);
    premi("filtra");
    expect(main.scrollTop).toBe(800);
  });
});
