import { voiceEnv } from "../env";

export const runtime = "nodejs";

const DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB";

export async function POST(request: Request) {
  const apiKey = voiceEnv("ELEVENLABS_API_KEY");
  if (!apiKey) {
    return Response.json({ error: "ELEVENLABS_API_KEY is not configured." }, { status: 500 });
  }

  try {
    const { text } = (await request.json()) as { text?: string };
    const spokenText = text?.trim();
    if (!spokenText) {
      return Response.json({ error: "Missing text." }, { status: 400 });
    }

    const voiceId = voiceEnv("ELEVENLABS_VOICE_ID")?.trim() || DEFAULT_VOICE_ID;
    const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "xi-api-key": apiKey,
      },
      body: JSON.stringify({
        text: spokenText,
        model_id: "eleven_multilingual_v2",
        voice_settings: {
          stability: 0.5,
          similarity_boost: 0.75,
          style: 0,
          use_speaker_boost: true,
        },
      }),
    });

    if (!response.ok) {
      const detail = await response.text();
      console.error("ElevenLabs TTS failed", response.status, detail);
      return Response.json({ error: "Speech synthesis failed." }, { status: response.status });
    }

    return new Response(response.body, {
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "audio/mpeg",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("Voice TTS route failed", error);
    return Response.json({ error: "Speech synthesis failed." }, { status: 500 });
  }
}
