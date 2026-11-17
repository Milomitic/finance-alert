import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useConfermaInDuePassi } from "./useConfermaInDuePassi";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useConfermaInDuePassi", () => {
  it("il primo tocco arma soltanto, il secondo esegue", () => {
    const azione = vi.fn();
    const { result } = renderHook(() => useConfermaInDuePassi(azione));
    act(() => result.current.premi());
    expect(azione).not.toHaveBeenCalled();
    expect(result.current.armato).toBe(true);
    act(() => result.current.premi());
    expect(azione).toHaveBeenCalledTimes(1);
    expect(result.current.armato).toBe(false);
  });

  it("senza il secondo tocco torna a riposo e non esegue", () => {
    const azione = vi.fn();
    const { result } = renderHook(() => useConfermaInDuePassi(azione, 4000));
    act(() => result.current.premi());
    act(() => vi.advanceTimersByTime(4001));
    expect(result.current.armato).toBe(false);
    act(() => result.current.premi());
    expect(azione).not.toHaveBeenCalled();
  });
});
