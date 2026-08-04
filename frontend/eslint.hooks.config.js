import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

/* CI gate for ONE rule: react-hooks/rules-of-hooks.
 *
 * Why a second config instead of putting `npm run lint` in the pipeline. The
 * full config currently reports ~57 errors, nearly all of them stylistic rules
 * that arrived with eslint-plugin-react-hooks v7 (exhaustive-deps,
 * set-state-in-effect, static-components, purity). Gating on all of them would
 * block every deploy for reasons unrelated to the change being deployed, so it
 * would be switched off within a week. Cleaning them up is worth doing, and is
 * a separate job.
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
 * Keep this list at one rule. Its value is that it never produces noise, so a
 * red result always means something is genuinely broken.
 */
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [tseslint.configs.base],
    rules: {
      'react-hooks/rules-of-hooks': 'error',
    },
    plugins: { 'react-hooks': reactHooks },
    // The `eslint-disable` comments scattered around the codebase target rules
    // this config does not enable, so eslint would flag every one of them as
    // unused — ~10 warnings that mean nothing here and would train everyone to
    // ignore this gate's output. The full config still checks them.
    linterOptions: { reportUnusedDisableDirectives: 'off' },
  },
])
