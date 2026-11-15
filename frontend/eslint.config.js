// Linting: recommended rules for JavaScript and TypeScript plus the rules of hooks for React.
// Run with `npm run lint` (needs Node 20.19+ like the other dev tools, see .nvmrc).
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig(
  { ignores: ["dist/", "services/api/schema.d.ts"] },
  js.configs.recommended,
  tseslint.configs.recommended,
  reactHooks.configs.flat["recommended-latest"],
  { languageOptions: { globals: globals.browser } },
  { files: ["vite.config.ts", "eslint.config.js"], languageOptions: { globals: globals.node } },
);
