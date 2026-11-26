import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useColumnVisibility } from "./useColumnVisibility";

const COL = [{ id: "a", label: "A" }, { id: "b", label: "B" }, { id: "c", label: "C" }];

describe("le colonne nascoste di default (C-27)", () => {
  it("senza una scelta salvata valgono le nascoste di default", () => {
    const { result } = renderHook(() => useColumnVisibility("t1", COL, ["b"]));
    expect(result.current.isVisible("a")).toBe(true);
    expect(result.current.isVisible("b")).toBe(false);
  });

  it("una scelta salvata vince sul default, anche se e' «tutte visibili»", () => {
    localStorage.setItem("colvis:t2", JSON.stringify([]));
    const { result } = renderHook(() => useColumnVisibility("t2", COL, ["b"]));
    expect(result.current.isVisible("b")).toBe(true);
  });

  it("la scelta si salva", () => {
    const { result } = renderHook(() => useColumnVisibility("t3", COL, ["b"]));
    act(() => result.current.toggle("b"));
    expect(JSON.parse(localStorage.getItem("colvis:t3") ?? "null")).toEqual([]);
  });
});
