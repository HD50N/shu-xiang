import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

let parentEnv: Record<string, string> | null = null;

function cleanEnvValue(value: string | undefined) {
  if (value === undefined) return undefined;
  let cleaned = value.trim();

  const quote = cleaned[0];
  if ((quote === '"' || quote === "'") && cleaned.endsWith(quote)) {
    return cleaned.slice(1, -1).trim() || undefined;
  }

  cleaned = cleaned.replace(/\s+#.*$/, "").trim();
  return cleaned || undefined;
}

function readParentEnv() {
  if (parentEnv) return parentEnv;

  parentEnv = {};
  const envPath = resolve(process.cwd(), "..", ".env");
  if (!existsSync(envPath)) return parentEnv;

  const contents = readFileSync(envPath, "utf8");
  for (const rawLine of contents.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) continue;

    const [, key, rawValue] = match;
    const value = cleanEnvValue(rawValue);
    if (value !== undefined) parentEnv[key] = value;
  }

  return parentEnv;
}

export function voiceEnv(name: string) {
  return cleanEnvValue(process.env[name]) ?? readParentEnv()[name];
}
