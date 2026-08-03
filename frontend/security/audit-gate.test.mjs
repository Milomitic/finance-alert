import { describe, expect, it } from "vitest";

import { advisoryIds, evaluate } from "./audit-gate.mjs";

/* This file decides whether a vulnerability reaches production. A bug here is
 * worse than no gate at all: a gate that silently passes everything still
 * reports "clean", which is the most convincing form of being wrong. */

const GHSA = "GHSA-qwww-vcr4-c8h2";

function report(vulns) {
  return { vulnerabilities: Object.fromEntries(vulns.map((v) => [v.name, v])) };
}

const allow = [
  { id: GHSA, package: "react-router", reason: "n/a here", review_by: "2099-01-01" },
];

describe("audit gate", () => {
  it("blocks an advisory nobody has reviewed", () => {
    const r = report([
      { name: "evil", severity: "critical", via: [{ url: `https://github.com/advisories/GHSA-aaaa-bbbb-cccc` }] },
    ]);
    const { blocking } = evaluate(r, allow, "2026-08-03");
    expect(blocking).toHaveLength(1);
    expect(blocking[0].pkg).toBe("evil");
  });

  it("excuses one that carries a documented reason", () => {
    const r = report([
      { name: "react-router", severity: "high", via: [{ url: `https://github.com/advisories/${GHSA}` }] },
    ]);
    const { blocking, excused } = evaluate(r, allow, "2026-08-03");
    expect(blocking).toHaveLength(0);
    expect(excused[0].id).toBe(GHSA);
  });

  it("follows a package that is only affected THROUGH another", () => {
    /* react-router-dom's `via` is the bare string "react-router" — no id at
     * all. Reading only advisory objects would leave it unidentified and
     * block on the exact thing just excused one line above. */
    const r = report([
      { name: "react-router", severity: "high", via: [{ url: `https://github.com/advisories/${GHSA}` }] },
      { name: "react-router-dom", severity: "high", via: ["react-router"] },
    ]);
    const { blocking, excused } = evaluate(r, allow, "2026-08-03");
    expect(blocking).toHaveLength(0);
    expect(excused).toHaveLength(2);
  });

  it("survives a cycle in the dependency graph", () => {
    const r = report([
      { name: "a", severity: "high", via: ["b"] },
      { name: "b", severity: "high", via: ["a"] },
    ]);
    expect(() => evaluate(r, allow, "2026-08-03")).not.toThrow();
    expect(advisoryIds("a", r).size).toBe(0);
  });

  it("fails once an exception is past its review date, even when quiet", () => {
    /* The point of the expiry. An exception that cannot go stale is
     * indistinguishable from having deleted the check. */
    const stale = [{ ...allow[0], review_by: "2026-01-01" }];
    const { expired } = evaluate(report([]), stale, "2026-08-03");
    expect(expired).toHaveLength(1);
  });

  it("ignores severities below the bar", () => {
    const r = report([{ name: "postcss", severity: "moderate", via: [{ url: "x/GHSA-zzzz-zzzz-zzzz" }] }]);
    const { blocking, excused } = evaluate(r, allow, "2026-08-03");
    expect(blocking).toHaveLength(0);
    expect(excused).toHaveLength(0);
  });

  it("reports an allowlist entry that is no longer needed", () => {
    const { stale } = evaluate(report([]), allow, "2026-08-03");
    expect(stale.map((s) => s.id)).toEqual([GHSA]);
  });
});
