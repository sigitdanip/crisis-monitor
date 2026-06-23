// safe: this file is the ESLint rule definition itself; toLocale appears
// as a regex pattern in a string literal, not as an actual call.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.property.name=/^toLocale/]",
          message:
            "toLocale*() methods (toLocaleString, toLocaleDateString, etc.) cause " +
            "hydration mismatches because Node SSR and browser may use different locales. " +
            "Use locale-independent helpers from src/lib/datetime.ts instead.",
        },
        {
          selector: "MemberExpression[object.name='Intl']",
          message:
            "Intl API (Intl.DateTimeFormat, Intl.NumberFormat, etc.) causes hydration " +
            "mismatches because Node SSR and browser may use different locales. " +
            "Use locale-independent helpers from src/lib/datetime.ts instead.",
        },
      ],
    },
  },
]);

export default eslintConfig;
