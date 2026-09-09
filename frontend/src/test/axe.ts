import axe, { type AxeResults, type RunOptions } from "axe-core";

/** Automated accessibility checks over a rendered subtree.
 *
 * ⚠️ **Read this before trusting a green result.** These run in jsdom, which
 * loads no stylesheet. Tailwind classes are inert strings there, so an entire
 * family of real defects is INVISIBLE to this harness:
 *
 *   - colour contrast, which needs computed styles
 *   - anything decided by `display:none` vs `sr-only`, which is exactly how
 *     the logout button lost its accessible name on phones
 *   - touch target size, which needs layout
 *   - focus visibility, which needs the focus ring to actually paint
 *
 * What it DOES catch is the half that is structural and that humans miss most
 * often: controls with no accessible name, invalid or orphaned ARIA, duplicate
 * ids, form fields with no label, images with no alt, broken heading order,
 * and required parent/child role relationships.
 *
 * So this is a floor, not a certification. A green run means "no structural
 * violation an automated tool can see in a DOM with no CSS". It is not WCAG
 * AA, and the audit's own note that no WCAG certification exists still stands.
 */

/** Rules switched off with a reason, never to make a report green.
 *
 * `color-contrast` cannot run without computed styles: in jsdom it returns
 * "incomplete" rather than a violation, so leaving it on adds noise that
 * teaches people to skim the output. Contrast is checked by hand against the
 * palette rules in CLAUDE.md instead.
 *
 * `region` requires every node to sit inside a landmark. That is a property of
 * the whole PAGE, and most tests here mount one component in a bare div, where
 * the rule would fail for a reason the component cannot fix.
 */
const DISABLED = ["color-contrast", "region"] as const;

export async function axeViolations(
  container: HTMLElement,
  options: RunOptions = {},
): Promise<AxeResults["violations"]> {
  const results = await axe.run(container, {
    rules: Object.fromEntries(DISABLED.map((id) => [id, { enabled: false }])),
    ...options,
  });
  return results.violations;
}

/** A failure message that names the element, not just the rule.
 *
 * axe's default output is a nested object; printed raw by a test runner it is
 * unreadable, and an unreadable failure is one people disable. */
export function describeViolations(violations: AxeResults["violations"]): string {
  if (violations.length === 0) return "nessuna violazione";
  return violations
    .map((v) => {
      const where = v.nodes.map((n) => n.html.slice(0, 120)).join("\n      ");
      return `  [${v.impact ?? "?"}] ${v.id}: ${v.help}\n      ${where}`;
    })
    .join("\n");
}
