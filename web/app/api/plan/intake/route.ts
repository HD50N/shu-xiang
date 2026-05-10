import { voiceEnv } from "../../voice/env";

export const runtime = "nodejs";

const MAX_TURNS = 12;

const REQUIRED_PROFILE_FIELDS = [
  "entity_name",
  "business_type",
  "sole_owner",
  "plans_to_hire",
  "sells_food",
] as const;

const MISSING_FIELD_QUESTIONS: Record<string, Record<string, string>> = {
  en: {
    entity_name: "What is the company name?",
    business_type: "What type of business are you starting?",
    sole_owner: "Are you the only owner?",
    plans_to_hire: "Do you plan to hire employees?",
    sells_food: "Will this business sell food?",
  },
  zh: {
    entity_name: "公司叫什么名字？",
    business_type: "你要做什么类型的生意？",
    sole_owner: "你是唯一所有者吗？",
    plans_to_hire: "你打算雇员工吗？",
    sells_food: "这个生意会卖食品吗？",
  },
  ko: {
    entity_name: "회사 이름은 무엇인가요?",
    business_type: "어떤 종류의 사업을 시작하시나요?",
    sole_owner: "본인이 유일한 소유자인가요?",
    plans_to_hire: "직원을 고용할 계획인가요?",
    sells_food: "이 사업에서 음식을 판매하나요?",
  },
  es: {
    entity_name: "¿Cuál es el nombre de la compañía?",
    business_type: "¿Qué tipo de negocio estás empezando?",
    sole_owner: "¿Eres la única persona dueña?",
    plans_to_hire: "¿Planeas contratar empleados?",
    sells_food: "¿Este negocio venderá comida?",
  },
};

const FIXED_SCRIPT_QUESTIONS: Record<string, string[]> = {
  en: [
    "Hi! Tell me about your business — what do you do, and what is the company called?",
    "Where is your shop located? An address or approximate location is fine.",
    "Are you the only owner? Do you plan to hire employees?",
    "What does the restaurant sell? Just food, or alcohol too?",
  ],
  zh: [
    "你好！告诉我你的生意 — 你做什么，公司叫什么名字？",
    "你的店开在哪里？地址或者大概的位置都可以。",
    "你是唯一的所有者吗？打算雇人吗？",
    "餐厁卖什么？只卖食物，还是也卖酒？",
  ],
  ko: [
    "안녕하세요! 시작하려는 사업에 대해 말씀해 주세요. 무엇을 하시고, 회사 이름은 무엇인가요?",
    "가게는 어디에 있나요? 주소나 대략적인 위치도 괜찮습니다.",
    "본인이 유일한 소유자인가요? 직원을 고용할 계획인가요?",
    "식당에서는 무엇을 판매하나요? 음식만 판매하나요, 아니면 술도 판매하나요?",
  ],
  es: [
    "Hola. Cuéntame sobre tu negocio: ¿qué haces y cómo se llama la compañía?",
    "¿Dónde estará ubicado tu local? Una dirección o ubicación aproximada está bien.",
    "¿Eres la única persona dueña? ¿Planeas contratar empleados?",
    "¿Qué venderá el restaurante? ¿Solo comida o también alcohol?",
  ],
};

const INTAKE_SYSTEM_PROMPT = `You are Shu Xiang, a multilingual AI consultant helping an immigrant business owner file an Illinois LLC. The user just unmuted their mic and is talking to you.

Your job: in 3-6 short conversational turns, gather a structured business profile so the system can generate a personalized compliance checklist. Do not front-load filing minutiae; later form steps will ask for missing filing details when needed.

REQUIRED slots (must all be filled before you FINISH):
- entity_name — the business name (string)
- business_type — restaurant / retail / salon / services / online / etc.
- city — city name in English (e.g. 芝加哥 → "Chicago")
- sole_owner — boolean
- plans_to_hire — boolean
- sells_food — boolean (matters for licensing in Illinois)

OPTIONAL slots (fill if the user volunteers them — do NOT probe):
- principal_address, principal_city, principal_zip
- organizer_name, organizer_email, organizer_phone
- registered_agent_name, registered_agent_address
- sells_alcohol — only ask if business_type=restaurant AND user might serve alcohol
- online_only — boolean (no physical location)
- different_dba — boolean (operating under a different name than entity_name)
- state — defaults to "IL"

DECISION RULES:
1. Each turn, you receive (a) the running profile and (b) the user's latest utterance.
2. Extract any slots the user just answered. If their answer was vague, leave that slot empty.
3. If a REQUIRED slot is empty OR the last answer was ambiguous → next_action="ASK", write ONE short question in the requested target conversation language for the most-important missing/ambiguous slot.
4. If all REQUIRED slots are filled clearly → next_action="FINISH".
5. Hard cap: turn_num >= 12 → FINISH regardless.

QUESTION STYLE (when ASK):
- Short, conversational, not formal.
- Use the requested target conversation language.
- ONE focus per question, but naturally-paired slots can combine: "你是唯一的所有者吗？打算雇人吗？" or "卖食物吗？也卖酒吗？" is fine.
- Don't ask about something you already heard. If the user said "我自己开" then sole_owner is true — move on.
- Clarify when vague: user says "我开店" → ask "什么样的店？餐厁还是零售？"

EXTRACTION HEURISTICS:
- If the user gives a brand name without "LLC" suffix, fill entity_name with the brand only — the system appends "LLC" later.
- City names: 芝加哥 → "Chicago", 纽约 → "New York", etc.
- If the user gives a business street address and city, also fill principal_city with that city.
- If the user says the registered agent address is the same as the business address, fill registered_agent_address with the business address.
- Do not invent organizer_name, organizer_email, organizer_phone, street address, ZIP code, or registered agent info.
- "我自己开" / "我一个人" → sole_owner=true
- "雇人" / "请人" / "找人帮忙" → plans_to_hire=true; "我自己做" / "不雇" → plans_to_hire=false
- "餐厁" / "饭店" / "卖吃的" → business_type="restaurant", sells_food=true
- Don't fabricate. Empty/missing values stay empty.

Always return your decision via the intake_turn tool. Never write prose.`;

const INTAKE_TURN_TOOL = {
  name: "intake_turn",
  description: "Process one conversational turn. Return profile updates and the next action.",
  input_schema: {
    type: "object",
    properties: {
      profile_updates: {
        type: "object",
        description:
          "Slots extracted from the user's latest utterance. Include ONLY slots you actually heard the user answer this turn — don't re-echo prior values. Use null/omit for slots not heard.",
        properties: {
          entity_name: { type: "string" },
          business_type: { type: "string" },
          city: { type: "string" },
          state: { type: "string" },
          principal_address: { type: "string" },
          principal_city: { type: "string" },
          principal_zip: { type: "string" },
          organizer_name: { type: "string" },
          organizer_email: { type: "string" },
          organizer_phone: { type: "string" },
          registered_agent_name: { type: "string" },
          registered_agent_address: { type: "string" },
          sole_owner: { type: "boolean" },
          plans_to_hire: { type: "boolean" },
          sells_food: { type: "boolean" },
          sells_alcohol: { type: "boolean" },
          online_only: { type: "boolean" },
          different_dba: { type: "boolean" },
        },
      },
      next_action: {
        type: "string",
        enum: ["ASK", "FINISH"],
        description: "ASK = ask another question; FINISH = all required slots filled, move to Phase 2.",
      },
      question_zh: {
        type: "string",
        description:
          "If next_action=ASK, the next question in the requested target language. Empty string if FINISH.",
      },
      reasoning: {
        type: "string",
        description: "One short sentence explaining why you picked this action.",
      },
    },
    required: ["profile_updates", "next_action", "question_zh", "reasoning"],
  },
};

type IntakeProfile = Record<string, string | boolean | null | undefined>;
type IntakeDecision = {
  profile_updates?: IntakeProfile;
  next_action?: "ASK" | "FINISH";
  question_zh?: string;
  reasoning?: string;
};

function mergeProfile(profile: IntakeProfile, updates: IntakeProfile) {
  const next = { ...profile };
  for (const [key, value] of Object.entries(updates)) {
    if (value !== null && value !== undefined && value !== "") next[key] = value;
  }
  return next;
}

function missingRequiredFields(profile: IntakeProfile) {
  return REQUIRED_PROFILE_FIELDS.filter((key) => profile[key] === null || profile[key] === undefined || profile[key] === "");
}

function questionForMissingField(field: string, language: string) {
  const lang = language.toLowerCase();
  const questions = MISSING_FIELD_QUESTIONS[lang] ?? MISSING_FIELD_QUESTIONS.en;
  return questions[field] ?? "Please provide the missing required information.";
}

async function callAnthropic({
  transcript,
  profile,
  turnNum,
  language,
}: {
  transcript: string;
  profile: IntakeProfile;
  turnNum: number;
  language: string;
}): Promise<IntakeDecision> {
  const apiKey = voiceEnv("ANTHROPIC_API_KEY");
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY not configured");

  const userMessage = [
    `Turn ${turnNum}/${MAX_TURNS}.`,
    `Running profile (JSON): ${JSON.stringify(profile)}`,
    `Target conversation language: ${language}`,
    `User just said: "${transcript}"`,
    "",
    "Extract any slots they just filled, then decide ASK or FINISH. If ASK, write ONE short question in the target conversation language for the most-important missing slot.",
  ].join("\n");

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-6",
      max_tokens: 512,
      system: INTAKE_SYSTEM_PROMPT,
      tools: [INTAKE_TURN_TOOL],
      tool_choice: { type: "tool", name: "intake_turn" },
      messages: [{ role: "user", content: userMessage }],
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    console.error("Anthropic intake failed", response.status, detail);
    throw new Error("Anthropic intake failed");
  }

  const body = (await response.json()) as {
    content?: Array<{ type: string; name?: string; input?: IntakeDecision }>;
  };
  const toolUse = body.content?.find((block) => block.type === "tool_use" && block.name === "intake_turn");
  if (!toolUse?.input) throw new Error("Anthropic did not call intake_turn");
  return toolUse.input;
}

function fixedScriptFallback(turnNum: number, language: string) {
  const questions = FIXED_SCRIPT_QUESTIONS[language.toLowerCase()] ?? FIXED_SCRIPT_QUESTIONS.en;
  const nextQuestion = questions[turnNum] ?? "";
  return {
    profile_updates: {},
    next_action: nextQuestion ? "ASK" : "FINISH",
    question_zh: nextQuestion,
    reasoning: "Fallback fixed-script intake.",
  } satisfies IntakeDecision;
}

export async function POST(request: Request) {
  try {
    const { transcript, profile = {}, turnNum = 1, language = "en" } = (await request.json()) as {
      transcript?: string;
      profile?: IntakeProfile;
      turnNum?: number;
      language?: string;
    };

    if (!transcript?.trim()) {
      return Response.json({ error: "Missing transcript." }, { status: 400 });
    }

    let decision: IntakeDecision;
    try {
      decision = await callAnthropic({
        transcript: transcript.trim(),
        profile,
        turnNum,
        language,
      });
    } catch (error) {
      console.error("Dynamic intake failed; using fixed-script fallback", error);
      decision = fixedScriptFallback(turnNum, language);
    }

    const nextProfile = mergeProfile(profile, decision.profile_updates ?? {});
    const missing = missingRequiredFields(nextProfile);
    let action = decision.next_action ?? "ASK";
    let question = decision.question_zh?.trim() ?? "";

    if (missing.length > 0) {
      action = "ASK";
      if (!question || decision.next_action === "FINISH") {
        question = questionForMissingField(missing[0], language);
      }
    }

    if ((action === "FINISH" && missing.length === 0) || turnNum >= MAX_TURNS || !question) {
      action = "FINISH";
      question = "";
    }

    return Response.json({
      profile: nextProfile,
      nextAction: action,
      question,
      missing,
      reasoning: decision.reasoning ?? "",
    });
  } catch (error) {
    console.error("Plan intake route failed", error);
    return Response.json({ error: "Plan intake failed." }, { status: 500 });
  }
}
