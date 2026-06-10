// @ts-nocheck
import { config as loadEnv } from "dotenv";
import { defineConfig } from "prisma/config";

declare const process: {
  env: Record<string, string | undefined>;
};

loadEnv({ path: "../.env" });

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
  },
  datasource: {
    url: process.env["DATABASE_URL"],
  },
});
