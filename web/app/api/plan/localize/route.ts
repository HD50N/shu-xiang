import { voiceEnv } from "../../voice/env";

export const runtime = "nodejs";

const LOCALIZE_TOOL = {
  name: "localized_ui_copy",
  description: "Return translated UI copy for the planning page.",
  input_schema: {
    type: "object",
    properties: {
      copy: {
        type: "object",
        description: "Translated sourceCopy object. Keep the same keys and nested shape.",
      },
      greeting: {
        type: "string",
        description: "Translated sourceGreeting.",
      },
    },
    required: ["copy", "greeting"],
  },
};

export async function POST(request: Request) {
  try {
    const { targetLanguage, sourceCopy, sourceGreeting } = (await request.json()) as {
      targetLanguage?: string;
      sourceCopy?: unknown;
      sourceGreeting?: string;
    };

    const apiKey = voiceEnv("ANTHROPIC_API_KEY");
    if (!apiKey) return Response.json({ error: "ANTHROPIC_API_KEY is not configured." }, { status: 500 });
    if (!targetLanguage || !sourceCopy || !sourceGreeting) {
      return Response.json({ error: "Missing localization inputs." }, { status: 400 });
    }

    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-6",
        max_tokens: 2200,
        system:
          "Translate UI copy for a multilingual business filing assistant. Preserve product names like Shu-Xiang, legal terms like LLC when appropriate, and all JSON keys. Use the localized_ui_copy tool only.",
        tools: [LOCALIZE_TOOL],
        tool_choice: { type: "tool", name: "localized_ui_copy" },
        messages: [
          {
            role: "user",
            content: JSON.stringify({
              targetLanguage,
              sourceCopy,
              sourceGreeting,
            }),
          },
        ],
      }),
    });

    if (!response.ok) {
      const detail = await response.text();
      console.error("Localization failed", response.status, detail);
      return Response.json({ error: "Localization failed." }, { status: response.status });
    }

    const body = (await response.json()) as {
      content?: Array<{ type: string; name?: string; input?: { copy?: unknown; greeting?: unknown } }>;
    };
    const toolUse = body.content?.find((block) => block.type === "tool_use" && block.name === "localized_ui_copy");
    if (!toolUse?.input?.copy || typeof toolUse.input.greeting !== "string") {
      throw new Error("Localization response did not include tool output.");
    }

    return Response.json({ copy: toolUse.input.copy, greeting: toolUse.input.greeting });
  } catch (error) {
    console.error("Plan localization route failed", error);
    return Response.json({ error: "Localization failed." }, { status: 500 });
  }
}
