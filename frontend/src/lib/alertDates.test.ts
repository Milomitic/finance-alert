import { describe, expect, it } from "vitest";

import {
  DELAYED_DETECTION_MIN_DAYS,
  daysBetween,
  formatShortDate,
  isDelayedDetection,
} from "@/lib/alertDates";

describe("daysBetween", () => {
  it("returns 0 for the same calendar day even with different times", () => {
    // Midday UTC so the calendar day is the same in any test-runner tz.
    expect(daysBetween("2026-07-06T12:00:00Z", "2026-07-06")).toBe(0);
  });

  it("counts whole calendar days between the two dates", () => {
    expect(daysBetween("2026-07-08", "2026-07-06")).toBe(2);
    expect(daysBetween("2026-07-10T09:00:00Z", "2026-07-06")).toBe(4);
  });

  it("returns null when either side is missing or unparsable", () => {
    expect(daysBetween(null, "2026-07-06")).toBeNull();
    expect(daysBetween("2026-07-06", undefined)).toBeNull();
    expect(daysBetween("not-a-date", "2026-07-06")).toBeNull();
  });
});

describe("isDelayedDetection", () => {
  // Threshold raised 1 → 4 (audit 2026-07-08): a weekend gap (~2 days) plus
  // one skipped scan is NORMAL cadence, not a delay worth an orange chip.
  it(`fires only at >= ${DELAYED_DETECTION_MIN_DAYS} calendar days`, () => {
    // Same day / normal cadence → no chip.
    expect(isDelayedDetection("2026-07-06T18:00:00Z", "2026-07-06")).toBe(false);
    expect(isDelayedDetection("2026-07-07", "2026-07-06")).toBe(false);
    // Friday close → Monday scan (weekend ≈ 2-3 days) → still no chip.
    expect(isDelayedDetection("2026-07-06", "2026-07-03")).toBe(false);
    // 4+ days = real backfill/outage → chip.
    expect(isDelayedDetection("2026-07-10", "2026-07-06")).toBe(true);
    expect(isDelayedDetection("2026-07-20", "2026-07-06")).toBe(true);
  });

  it("never fires for legacy alerts without a signal_date", () => {
    expect(isDelayedDetection("2026-07-06T18:00:00Z", null)).toBe(false);
    expect(isDelayedDetection("2026-07-06T18:00:00Z", undefined)).toBe(false);
  });
});

describe("formatShortDate", () => {
  it("formats an ISO date as DD/MM/YY and tolerates missing values", () => {
    expect(formatShortDate("2026-07-06")).toBe("06/07/26");
    expect(formatShortDate(null)).toBe("—");
    expect(formatShortDate(undefined)).toBe("—");
  });
});
