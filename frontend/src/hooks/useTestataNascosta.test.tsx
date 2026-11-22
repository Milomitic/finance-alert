import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useTestataNascosta } from "./useTestataNascosta";

function scorri(el: HTMLElement, y: number) {
  act(() => {
    el.scrollTop = y;
    el.dispatchEvent(new Event("scroll"));
  });
}

describe("useTestataNascosta", () => {
  it("si nasconde scorrendo in giu', riappare scorrendo in su", () => {
    const el = document.createElement("div");
    const ref = { current: el };
    const { result } = renderHook(() => useTestataNascosta(ref));
    expect(result.current).toBe(false);
    scorri(el, 300);
    expect(result.current).toBe(true);
    scorri(el, 304); // tremolio sotto soglia: niente
    expect(result.current).toBe(true);
    scorri(el, 250);
    expect(result.current).toBe(false);
    scorri(el, 400);
    expect(result.current).toBe(true);
  });

  it("vicino alla cima resta visibile, anche scendendo", () => {
    const el = document.createElement("div");
    const { result } = renderHook(() => useTestataNascosta({ current: el }));
    scorri(el, 40);
    expect(result.current).toBe(false);
  });

  it("cambiando pagina torna visibile", () => {
    const el = document.createElement("div");
    const ref = { current: el };
    const { result, rerender } = renderHook(({ k }) => useTestataNascosta(ref, { chiave: k }), {
      initialProps: { k: "/a" },
    });
    scorri(el, 500);
    expect(result.current).toBe(true);
    rerender({ k: "/b" });
    expect(result.current).toBe(false);
  });
});
