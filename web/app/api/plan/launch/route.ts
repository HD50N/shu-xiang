import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { voiceEnv } from "../../voice/env";

export const runtime = "nodejs";

const projectRoot = resolve(process.cwd(), "..");

function pythonExecutable() {
  const venvPython = resolve(projectRoot, ".venv", "bin", "python");
  return existsSync(venvPython) ? venvPython : "python";
}

export async function POST(request: Request) {
  try {
    const { profile, language = "en" } = (await request.json()) as {
      profile?: Record<string, unknown>;
      language?: string;
    };

    if (!profile || typeof profile !== "object") {
      return Response.json({ error: "Missing profile." }, { status: 400 });
    }

    const child = spawn(pythonExecutable(), ["main.py"], {
      cwd: projectRoot,
      detached: true,
      stdio: "ignore",
      env: {
        ...process.env,
        ANTHROPIC_API_KEY: voiceEnv("ANTHROPIC_API_KEY") ?? "",
        ELEVENLABS_API_KEY: voiceEnv("ELEVENLABS_API_KEY") ?? "",
        ELEVENLABS_VOICE_ID: voiceEnv("ELEVENLABS_VOICE_ID") ?? "",
        TARGET_ENV: "live",
        DEMO_MODE: "live_walkthrough",
        LIVE_VOICE: "true",
        SHUXIANG_LANGUAGE: language,
        SHUXIANG_WEB_HANDOFF_JSON: JSON.stringify({
          workflow: "Illinois LLC filing",
          fields: profile,
        }),
      },
    });

    child.unref();
    return Response.json({ ok: true });
  } catch (error) {
    console.error("Plan launch route failed", error);
    return Response.json({ error: "Could not launch filing flow." }, { status: 500 });
  }
}
