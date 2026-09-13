import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  /* ⚠️ `e2e/` gira in Node sotto Playwright e non contiene React.
   *
   * Playwright passa alle fixture una funzione chiamata `use`, che
   * `rules-of-hooks` legge come un hook React chiamato fuori da un
   * componente: un falso positivo STRUTTURALE, che si ripresenta a ogni nuova
   * fixture. `eslint.hooks.config.js` gia' escludeva la cartella; qui no,
   * quindi il conteggio totale portava un errore permanente sul nome della
   * regola piu' importante del gate — il modo piu' rapido per insegnare a
   * ignorarlo. Si esclude la cartella, non si silenzia la regola sul posto. */
  globalIgnores(['dist', 'e2e']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // The codebase already marks an intentionally unused binding with a
      // leading underscore -- `_`, `_band`, `_opts`, `_snap`. Nine findings
      // were all of that shape: correctly written code the linter had not been
      // told how to read. Configuring the rule is the fix; renaming the
      // placeholders to satisfy an unconfigured rule would have been the tail
      // wagging the dog.
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
      }],
    },
  },
])
