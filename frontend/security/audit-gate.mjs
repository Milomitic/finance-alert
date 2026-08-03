#!/usr/bin/env node
/**
 * npm audit as a gate that can stay green honestly.
 *
 * `npm audit --audit-level=high` is all-or-nothing: it cannot express "this
 * one has been read and does not apply", so a single unfixable advisory pins
 * CI red forever. A permanently red pipeline is not a strict pipeline — it is
 * an ignored one, and this repo has the receipt: a genuinely broken backend
 * gate sat unnoticed among the usual red because nobody reads a signal that
 * is always on.
 *
 * Two deliberate narrowings, both about what actually ships:
 *
 * 1. PRODUCTION TREE ONLY. The caller passes `--omit=dev` output. The build
 *    toolchain — eslint, vite, typescript — never reaches the browser or the
 *    image. A DoS in a linter's argument parser is not a user-facing risk,
 *    and treating it as one is how the noise starts.
 * 2. AN ALLOWLIST WITH AN EXPIRY DATE. Entries carry a reason and a
 *    `review_by`; past that date the gate fails on the entry itself. An
 *    exception that cannot expire is indistinguishable from blindness.
 *
 * Anything else at high or critical fails the build, which is the point.
 *
 * Reads the audit report rather than running it, so this file spawns nothing
 * and can be exercised against a fixture:
 *
 *   npm audit --json --omit=dev > audit.json || true
 *   node security/audit-gate.mjs audit.json
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const BLOCKING = new Set(["high", "critical"]);

/**
 * GHSA ids for a package. Humans recognise these; npm only exposes them
 * inside the advisory URL.
 *
 * `via` is heterogeneous, and that is the whole difficulty: a directly
 * affected package carries advisory OBJECTS, while a package that is only
 * affected through a dependency carries the dependency's NAME as a bare
 * string. react-router-dom is exactly this — `via: ["react-router"]`, no id
 * anywhere — so a resolver that only reads objects would report it as an
 * unknown advisory and block on the very thing that was just excused.
 * Follow the names, with a seen-set because the graph can loop.
 */
export function advisoryIds(name, report, seen = new Set()) {
  const out = new Set();
  if (seen.has(name)) return out;
  seen.add(name);
  for (const v of report.vulnerabilities?.[name]?.via ?? []) {
    if (typeof v === "string") {
      for (const id of advisoryIds(v, report, seen)) out.add(id);
    } else if (v?.url) {
      const m = /GHSA-[a-z0-9-]+/i.exec(v.url);
      if (m) out.add(m[0]);
    }
  }
  return out;
}

export function evaluate(report, allowlist, today) {
  const allowById = new Map(allowlist.map((a) => [a.id, a]));
  const blocking = [];
  const excused = [];
  for (const v of Object.values(report.vulnerabilities ?? {})) {
    if (!BLOCKING.has(v.severity)) continue;
    const ids = [...advisoryIds(v.name, report)];
    const hit = ids.find((id) => allowById.has(id));
    if (hit) excused.push({ pkg: v.name, id: hit, entry: allowById.get(hit) });
    else blocking.push({ pkg: v.name, severity: v.severity, ids });
  }
  // An allowlist entry past its review date fails the build even when the
  // advisory itself is quiet — that IS the reminder to look again.
  const expired = allowlist.filter((a) => a.review_by < today);
  const seen = new Set(excused.map((e) => e.id));
  const stale = allowlist.filter((a) => !seen.has(a.id));
  return { blocking, excused, expired, stale };
}

// ── CLI ──────────────────────────────────────────────────────────────────
if (process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/").split("/").pop())) {
  const src = process.argv[2];
  if (!src) {
    console.error("usage: audit-gate.mjs <npm-audit-json>");
    process.exit(2);
  }
  const report = JSON.parse(readFileSync(src, "utf8"));
  const allowlist = JSON.parse(
    readFileSync(join(HERE, "audit-allowlist.json"), "utf8"),
  ).allow;
  const today = new Date().toISOString().slice(0, 10);
  const { blocking, excused, expired, stale } = evaluate(report, allowlist, today);

  for (const e of excused) {
    console.log(`· excused  ${e.pkg}  ${e.id}  (review by ${e.entry.review_by})`);
  }
  for (const a of stale) {
    console.log(`· stale    ${a.package}  ${a.id} no longer reported — drop it`);
  }

  if (expired.length) {
    console.error("\nAllowlist entries are past their review date:");
    for (const a of expired) {
      console.error(`  ${a.package}  ${a.id}  review_by=${a.review_by}`);
    }
    console.error(
      "Re-read the advisory: either upgrade, or renew the entry with a fresh " +
        "reason and date. Silence by default is what this file exists to prevent.",
    );
  }
  if (blocking.length) {
    console.error("\nUnreviewed high/critical advisories in the PRODUCTION tree:");
    for (const b of blocking) {
      console.error(`  ${b.pkg}  [${b.severity}]  ${b.ids.join(", ") || "(no GHSA id)"}`);
    }
    console.error(
      "\nFix them, or — only after reading the advisory and establishing it " +
        "cannot apply here — add an entry to security/audit-allowlist.json " +
        "with a reason and a review date.",
    );
  }
  if (expired.length || blocking.length) process.exit(1);
  console.log(
    `\nnpm audit gate: clean (${excused.length} excused with a documented reason).`,
  );
}
