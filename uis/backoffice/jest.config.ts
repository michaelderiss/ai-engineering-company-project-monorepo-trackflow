import type { Config } from "jest";

/**
 * Jest configuration for the TrackFlow backoffice app (FE-019).
 *
 * rootDir is the monorepo root so both `uis/backoffice/lib` and the shared
 * `packages/shared/http.ts` client can be instrumented for coverage using
 * natural paths. Tests live in `uis/backoffice/__tests__/`.
 */
const config: Config = {
  testEnvironment: "node",
  rootDir: "../..",
  roots: ["<rootDir>/uis/backoffice", "<rootDir>/packages"],
  testMatch: ["**/__tests__/**/*.test.ts"],
  moduleFileExtensions: ["ts", "tsx", "js", "json"],
  moduleDirectories: ["node_modules", "uis/backoffice/node_modules"],
  transform: {
    "^.+\\.tsx?$": [
      "<rootDir>/uis/backoffice/node_modules/ts-jest",
      {
        tsconfig: {
          module: "commonjs",
          esModuleInterop: true,
          allowJs: true,
          types: ["jest", "node"],
        },
      },
    ],
  },
  collectCoverageFrom: [
    "uis/backoffice/lib/auth.ts",
    "uis/backoffice/lib/incidents.ts",
    "packages/shared/http.ts",
  ],
  clearMocks: true,
};

export default config;