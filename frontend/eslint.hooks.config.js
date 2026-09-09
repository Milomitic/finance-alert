import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

/* CI gate for TWO rules: react-hooks/rules-of-hooks and
 * react-hooks/static-components.
 *
 * Why a second config instead of putting `npm run lint` in the pipeline. The
 * full config reports 60 findings (measured 2026-09-09), nearly all of them
 * rules that arrived with eslint-plugin-react-hooks v7: only-export-components
 * 21, exhaustive-deps 15, set-state-in-effect 13, refs 5, purity 5,
 * immutability 1. Gating on all of them would block every deploy for reasons
 * unrelated to the change being deployed, so it would be switched off within a
 * week. Cleaning them up is worth doing, and is a separate job.
 *
 * `@typescript-eslint/no-unused-vars` reached ZERO on 2026-09-09 and is
 * deliberately NOT gated here, which is worth recording because the temptation
 * was real. Nine of its findings were placeholders the codebase already marks
 * with a leading underscore (`_`, `_band`, `_opts`) and the fix was to
 * configure the rule to read that convention, not to rename the code. But an
 * unused variable breaks nothing a user can feel, and that is the second half
 * of the bar below. Being at zero earns a rule consideration, not entry.
 *
 * rules-of-hooks is not in that category. A hook called conditionally is not a
 * style opinion: React identifies hooks by call order, so the violation throws
 * during render, and a throw during render with no boundary above it unmounts
 * the entire app. That is exactly what happened — `useIsPhone()` sat after an
 * early return in RunProgressToast and the dashboard went blank whenever a scan
 * started or finished.
 *
 * The rule was installed and enabled the whole time. It simply never ran
 * anywhere that could stop a merge. Nothing else catches it: it typechecks, it
 * builds, and a test only sees it if it renders the component in BOTH branch
 * states (see RunProgressToast.test.tsx).
 *
 * static-components was added on 2026-09-08, and the bar it had to clear was
 * the one in the paragraph above: NO NOISE. It reported 7 violations, 6 of
 * them a real defect and 1 a false positive, and it now reports 0 — so a red
 * result here still means something is genuinely broken, which is the only
 * property that keeps a gate switched on.
 *
 * It is not a style rule either. A component declared inside another
 * component's body is a new TYPE every render, and React reconciles by type:
 * it destroys the subtree and builds a new one. The pixels are identical, so a
 * mouse sees nothing. Focus lives on a node, and the node is gone — tab to a
 * tool in DrawingToolbar, press Enter, and you are on <body>. The two
 * offenders (DrawingToolbar, CalendarPage's ViewToggle) were both toggle
 * groups, i.e. controls whose whole job is to be pressed, so the remount was
 * triggered by the very click it punished.
 *
 * The false positive is worth knowing before adding the next disable:
 * `const Icon = getSectorIcon(x)` is a LOOKUP into a module-level map, so the
 * reference is stable, but the rule sees a capitalized local const used as JSX
 * and cannot tell. There is exactly one such disable, in SectorDetailPage.
 *
 * Keep this list short, and add to it only on the same terms: the rule must be
 * at zero when you gate it, and a violation must break something a user can
 * feel. The other v7 rules (exhaustive-deps, set-state-in-effect, purity) are
 * still ~50 findings and still a separate job.
 */
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [tseslint.configs.base],
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/static-components': 'error',
    },
    plugins: { 'react-hooks': reactHooks },
    // The `eslint-disable` comments scattered around the codebase target rules
    // this config does not enable, so eslint would flag every one of them as
    // unused — ~10 warnings that mean nothing here and would train everyone to
    // ignore this gate's output. The full config still checks them.
    linterOptions: { reportUnusedDisableDirectives: 'off' },
  },
])
