import js from "@eslint/js";
import tseslint from "typescript-eslint";
import svelte from "eslint-plugin-svelte";
import svelteParser from "svelte-eslint-parser";
import globals from "globals";

export default [
  {
    ignores: ["dist/**", "node_modules/**"],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ["**/*.svelte"],
    languageOptions: {
      parser: svelteParser,
      parserOptions: { parser: tseslint.parser },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      "no-useless-assignment": "off",
    },
  },

  ...svelte.configs.recommended,
];
