import eslint from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["build/**", "node_modules/**"],
  },

  {
    files: ["frontend/**/*.mjs"],
    extends: [eslint.configs.recommended],
    languageOptions: {
      globals: {
        process: "readonly",
      },
    },
  },

  {
    files: ["scripts/**/*.cjs"],
    extends: [eslint.configs.recommended],
    languageOptions: {
      sourceType: "commonjs",
      globals: {
        module: "readonly",
        process: "readonly",
        require: "readonly",
      },
    },
  },

  {
    files: ["frontend/**/*.ts", "vitest.config.ts"],
    ignores: ["frontend/src/workers/**/*.ts"],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
    ],
  },

  {
    files: ["frontend/src/workers/**/*.ts"],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
    ],
  },
);
