// @ts-nocheck
import { config as loadEnv } from "dotenv";
import { defineConfig } from "prisma/config";

declare const process: {
  env: Record<string, string | undefined>;
};

loadEnv({ path: "../.env" });

function buildDatasourceUrl(): string | undefined {
  const directUrl = process.env["DATABASE_URL"];
  if (directUrl) {
    return directUrl;
  }

  const host = process.env["DB_HOST"];
  const database = process.env["DB_NAME"];
  const user = process.env["DB_USER"];
  const password = process.env["DB_PASSWORD"];
  const port = process.env["DB_PORT"] || "5432";
  const sslmode = process.env["DB_SSLMODE"];

  if (!host || !database || !user || !password) {
    return undefined;
  }

  const encodedUser = encodeURIComponent(user);
  const encodedPassword = encodeURIComponent(password);
  const baseUrl = `postgresql://${encodedUser}:${encodedPassword}@${host}:${port}/${database}`;

  return sslmode ? `${baseUrl}?sslmode=${encodeURIComponent(sslmode)}` : baseUrl;
}

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
  },
  datasource: {
    url: buildDatasourceUrl(),
  },
});
