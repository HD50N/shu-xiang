import { voiceEnv } from "../env";

export const runtime = "nodejs";

const STT_LANGUAGE_CODES: Record<string, string> = {
  "zh": "zho",
  "zh-cn": "zho",
  "zh_cn": "zho",
  "chinese": "zho",
  "mandarin": "zho",
  "中文": "zho",
  "en": "eng",
  "en-us": "eng",
  "en_us": "eng",
  "english": "eng",
  "es": "spa",
  "spanish": "spa",
  "español": "spa",
  "fr": "fra",
  "french": "fra",
  "de": "deu",
  "german": "deu",
  "ja": "jpn",
  "japanese": "jpn",
  "ko": "kor",
  "ko-kr": "kor",
  "korean": "kor",
  "ar": "ara",
  "arabic": "ara",
  "hi": "hin",
  "hindi": "hin",
  "ru": "rus",
  "russian": "rus",
  "pt": "por",
  "portuguese": "por",
  "it": "ita",
  "italian": "ita",
  "vi": "vie",
  "vietnamese": "vie",
  "th": "tha",
  "thai": "tha",
  "tr": "tur",
  "turkish": "tur",
  "nl": "nld",
  "dutch": "nld",
  "pl": "pol",
  "polish": "pol",
};

function sttLanguageCode(language: FormDataEntryValue | null) {
  const override = voiceEnv("ELEVENLABS_STT_LANGUAGE_CODE")?.trim();
  if (override) return override;
  const value = language?.toString().trim().toLowerCase();
  if (!value) return "eng";
  return STT_LANGUAGE_CODES[value] ?? undefined;
}

export async function POST(request: Request) {
  const apiKey = voiceEnv("ELEVENLABS_API_KEY");
  if (!apiKey) {
    return Response.json({ error: "ELEVENLABS_API_KEY is not configured." }, { status: 500 });
  }

  try {
    const incoming = await request.formData();
    const audio = incoming.get("audio");
    if (!(audio instanceof Blob)) {
      return Response.json({ error: "Missing audio file." }, { status: 400 });
    }

    const formData = new FormData();
    formData.set("file", audio, "answer.webm");
    formData.set("model_id", "scribe_v1");
    formData.set("diarize", "false");
    formData.set("timestamps_granularity", "word");

    const languageCode = sttLanguageCode(incoming.get("language"));
    if (languageCode) formData.set("language_code", languageCode);

    const response = await fetch("https://api.elevenlabs.io/v1/speech-to-text", {
      method: "POST",
      headers: { "xi-api-key": apiKey },
      body: formData,
    });

    if (!response.ok) {
      const detail = await response.text();
      console.error("ElevenLabs STT failed", response.status, detail);
      return Response.json({ error: "Speech transcription failed." }, { status: response.status });
    }

    const body = (await response.json()) as { text?: string };
    return Response.json({ text: body.text?.trim() ?? "" });
  } catch (error) {
    console.error("Voice STT route failed", error);
    return Response.json({ error: "Speech transcription failed." }, { status: 500 });
  }
}
