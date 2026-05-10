"use client";

import Link from "next/link";
import { useRef, useState } from "react";

type IntakeProfile = Record<string, string | boolean | null | undefined>;
type FlowStage = "language" | "intake" | "complete";
type MicStatusKey =
  | "idle"
  | "speechUnavailable"
  | "openingBrowser"
  | "browserOpened"
  | "launchFailed"
  | "intakeFailed"
  | "processing"
  | "typeInstead"
  | "micBlocked"
  | "recording"
  | "didntCatch"
  | "thinking"
  | "transcriptionFailed"
  | "planningComplete";
type UICopy = {
  navBadge: string;
  readyBadge: string;
  readyToFileBadge: string;
  micOnBadge: string;
  helperLanguage: string;
  helperIntake: string;
  helperComplete: string;
  recordingHint: string;
  editHint: string;
  checklistEyebrow: string;
  readyToFile: string;
  planningComplete: string;
  captured: string;
  upNext: string;
  startFiling: string;
  continue: string;
  openingQuestion: string;
  finalMessage: string;
  status: Record<MicStatusKey, string>;
  steps: Record<string, { label: string; description: string }>;
};

const LANGUAGE_PROMPT =
  "What language would you like to use? Click the microphone and say a language, for example Korean, Spanish, or Mandarin.";

const GREETING_BY_LANGUAGE: Record<string, string> = {
  en: "Hi! Tell me about your business — what do you do, and what is the company called?",
  zh: "你好！告诉我你的生意 — 你做什么，公司叫什么名字？",
  ko: "안녕하세요! 시작하려는 사업에 대해 말씀해 주세요. 무엇을 하시고, 회사 이름은 무엇인가요?",
  es: "Hola. Cuéntame sobre tu negocio: ¿qué haces y cómo se llama la compañía?",
  fr: "Bonjour. Parlez-moi de votre entreprise : que faites-vous et comment s'appelle la société ?",
  pt: "Olá. Conte-me sobre o seu negócio: o que você faz e qual é o nome da empresa?",
  hi: "नमस्ते। मुझे अपने व्यवसाय के बारे में बताइए: आप क्या करते हैं और कंपनी का नाम क्या है?",
  ar: "مرحبا. أخبرني عن عملك: ماذا تفعل وما اسم الشركة؟",
};

const FLOW_STEPS = [
  { key: "language" },
  { key: "business" },
  { key: "location" },
  { key: "ownership" },
  { key: "food" },
];

const UI_COPY: Record<string, UICopy> = {
  en: {
    navBadge: "Voice planning room",
    readyBadge: "Microphone ready",
    readyToFileBadge: "Ready to file",
    micOnBadge: "Microphone is on",
    helperLanguage: "Click the microphone and say a language, for example Korean, Spanish, or Mandarin.",
    helperIntake: "Answer the question naturally. Shu-Xiang will ask only what is still missing.",
    helperComplete: "If a popup was blocked, use the Start filing button below.",
    recordingHint: "Speak naturally, then click the microphone again to send.",
    editHint: "You can edit the transcript before continuing.",
    checklistEyebrow: "Intake Checklist",
    readyToFile: "Ready to file",
    planningComplete: "Planning complete",
    captured: "Captured",
    upNext: "Up next",
    startFiling: "Start filing",
    continue: "Continue",
    openingQuestion: "Opening the filing flow.",
    finalMessage: "Great. I have the planning details. I am opening the filing browser now.",
    status: {
      idle: "Click to record",
      speechUnavailable: "Speech unavailable",
      openingBrowser: "Opening filing browser...",
      browserOpened: "Filing browser opened",
      launchFailed: "Could not launch filing flow",
      intakeFailed: "Intake failed",
      processing: "Processing...",
      typeInstead: "Type instead",
      micBlocked: "Mic blocked",
      recording: "Recording · click stop",
      didntCatch: "Didn't catch that",
      thinking: "Thinking...",
      transcriptionFailed: "Transcription failed",
      planningComplete: "Planning complete",
    },
    steps: {
      language: { label: "Language", description: "Choose the conversation language" },
      business: { label: "Business", description: "What you do and company name" },
      location: { label: "Location", description: "City or business location" },
      ownership: { label: "Ownership", description: "Owner and hiring details" },
      food: { label: "Food", description: "Food or alcohol if relevant" },
    },
  },
  zh: {
    navBadge: "语音规划室",
    readyBadge: "麦克风已准备好",
    readyToFileBadge: "准备开始申请",
    micOnBadge: "麦克风已开启",
    helperLanguage: "点击麦克风，说出语言名称，比如韩语、西班牙语或普通话。",
    helperIntake: "自然回答问题即可。Shu-Xiang 只会继续询问缺少的信息。",
    helperComplete: "如果弹窗被拦截，请点击下面的开始申请按钮。",
    recordingHint: "请自然说话，然后再次点击麦克风发送。",
    editHint: "继续之前可以修改转写内容。",
    checklistEyebrow: "信息清单",
    readyToFile: "准备申请",
    planningComplete: "规划完成",
    captured: "已记录",
    upNext: "下一项",
    startFiling: "开始申请",
    continue: "继续",
    openingQuestion: "正在打开申请流程。",
    finalMessage: "很好。我已经有了规划信息，现在打开申请浏览器。",
    status: {
      idle: "点击录音",
      speechUnavailable: "语音不可用",
      openingBrowser: "正在打开申请浏览器...",
      browserOpened: "申请浏览器已打开",
      launchFailed: "无法启动申请流程",
      intakeFailed: "信息收集失败",
      processing: "处理中...",
      typeInstead: "请手动输入",
      micBlocked: "麦克风被阻止",
      recording: "录音中 · 点击停止",
      didntCatch: "没有听清",
      thinking: "正在思考...",
      transcriptionFailed: "转写失败",
      planningComplete: "规划完成",
    },
    steps: {
      language: { label: "语言", description: "选择对话语言" },
      business: { label: "生意", description: "业务内容和公司名称" },
      location: { label: "地点", description: "城市或营业地点" },
      ownership: { label: "所有权", description: "所有者和雇佣计划" },
      food: { label: "食品", description: "是否涉及食品或酒类" },
    },
  },
  ko: {
    navBadge: "음성 계획실",
    readyBadge: "마이크 준비됨",
    readyToFileBadge: "신청 준비 완료",
    micOnBadge: "마이크가 켜져 있습니다",
    helperLanguage: "마이크를 클릭하고 한국어, 스페인어, 중국어처럼 사용할 언어를 말해 주세요.",
    helperIntake: "자연스럽게 답하세요. Shu-Xiang은 부족한 정보만 이어서 질문합니다.",
    helperComplete: "팝업이 차단되었다면 아래의 신청 시작 버튼을 사용하세요.",
    recordingHint: "자연스럽게 말한 뒤 마이크를 다시 클릭해 보내세요.",
    editHint: "계속하기 전에 전사 내용을 수정할 수 있습니다.",
    checklistEyebrow: "정보 체크리스트",
    readyToFile: "신청 준비 완료",
    planningComplete: "계획 완료",
    captured: "기록됨",
    upNext: "다음",
    startFiling: "신청 시작",
    continue: "계속",
    openingQuestion: "신청 절차를 여는 중입니다.",
    finalMessage: "좋습니다. 계획 정보가 준비되었습니다. 이제 신청 브라우저를 열겠습니다.",
    status: {
      idle: "녹음하려면 클릭",
      speechUnavailable: "음성을 사용할 수 없음",
      openingBrowser: "신청 브라우저를 여는 중...",
      browserOpened: "신청 브라우저가 열렸습니다",
      launchFailed: "신청 절차를 시작할 수 없습니다",
      intakeFailed: "정보 수집 실패",
      processing: "처리 중...",
      typeInstead: "직접 입력",
      micBlocked: "마이크 차단됨",
      recording: "녹음 중 · 클릭해서 중지",
      didntCatch: "잘 듣지 못했습니다",
      thinking: "생각 중...",
      transcriptionFailed: "전사 실패",
      planningComplete: "계획 완료",
    },
    steps: {
      language: { label: "언어", description: "대화 언어 선택" },
      business: { label: "사업", description: "하는 일과 회사 이름" },
      location: { label: "위치", description: "도시 또는 사업장 위치" },
      ownership: { label: "소유권", description: "소유자와 고용 계획" },
      food: { label: "음식", description: "음식 또는 주류 관련 여부" },
    },
  },
  es: {
    navBadge: "Sala de planificación por voz",
    readyBadge: "Micrófono listo",
    readyToFileBadge: "Listo para presentar",
    micOnBadge: "Micrófono encendido",
    helperLanguage: "Haz clic en el micrófono y di un idioma, por ejemplo coreano, español o mandarín.",
    helperIntake: "Responde de forma natural. Shu-Xiang solo preguntará lo que todavía falte.",
    helperComplete: "Si se bloqueó una ventana emergente, usa el botón para iniciar la presentación.",
    recordingHint: "Habla de forma natural y vuelve a hacer clic en el micrófono para enviar.",
    editHint: "Puedes editar la transcripción antes de continuar.",
    checklistEyebrow: "Lista de información",
    readyToFile: "Listo para presentar",
    planningComplete: "Planificación completa",
    captured: "Capturado",
    upNext: "Siguiente",
    startFiling: "Iniciar presentación",
    continue: "Continuar",
    openingQuestion: "Abriendo el flujo de presentación.",
    finalMessage: "Perfecto. Ya tengo los detalles de planificación. Ahora abriré el navegador de presentación.",
    status: {
      idle: "Haz clic para grabar",
      speechUnavailable: "Voz no disponible",
      openingBrowser: "Abriendo navegador de presentación...",
      browserOpened: "Navegador de presentación abierto",
      launchFailed: "No se pudo iniciar el flujo",
      intakeFailed: "Falló la recopilación",
      processing: "Procesando...",
      typeInstead: "Escribe la respuesta",
      micBlocked: "Micrófono bloqueado",
      recording: "Grabando · clic para detener",
      didntCatch: "No entendí eso",
      thinking: "Pensando...",
      transcriptionFailed: "Falló la transcripción",
      planningComplete: "Planificación completa",
    },
    steps: {
      language: { label: "Idioma", description: "Elegir el idioma de la conversación" },
      business: { label: "Negocio", description: "Qué haces y nombre de la compañía" },
      location: { label: "Ubicación", description: "Ciudad o ubicación del negocio" },
      ownership: { label: "Propiedad", description: "Dueño y planes de contratación" },
      food: { label: "Comida", description: "Comida o alcohol si aplica" },
    },
  },
};

const languageAliases: Record<string, { code: string; label: string; speechLang: string }> = {
  english: { code: "en", label: "English", speechLang: "en-US" },
  mandarin: { code: "zh", label: "中文", speechLang: "zh-CN" },
  chinese: { code: "zh", label: "中文", speechLang: "zh-CN" },
  中文: { code: "zh", label: "中文", speechLang: "zh-CN" },
  korean: { code: "ko", label: "한국어", speechLang: "ko-KR" },
  한국어: { code: "ko", label: "한국어", speechLang: "ko-KR" },
  spanish: { code: "es", label: "Español", speechLang: "es-ES" },
  español: { code: "es", label: "Español", speechLang: "es-ES" },
  espanol: { code: "es", label: "Español", speechLang: "es-ES" },
  french: { code: "fr", label: "Français", speechLang: "fr-FR" },
  german: { code: "de", label: "Deutsch", speechLang: "de-DE" },
  deutsch: { code: "de", label: "Deutsch", speechLang: "de-DE" },
  portuguese: { code: "pt", label: "Português", speechLang: "pt-BR" },
  hindi: { code: "hi", label: "हिन्दी", speechLang: "hi-IN" },
  arabic: { code: "ar", label: "العربية", speechLang: "ar-SA" },
};

function normalizeLanguage(answer: string) {
  const lower = answer.trim().toLowerCase();
  for (const [marker, language] of Object.entries(languageAliases)) {
    if (lower.includes(marker.toLowerCase())) return language;
  }
  const label = answer.trim() || "English";
  const code = label.toLowerCase().replace(/[^a-z-]+/g, "-").replace(/^-|-$/g, "") || "en";
  return { code, label, speechLang: code };
}

function greetingForLanguage(language: string) {
  return GREETING_BY_LANGUAGE[language] ?? GREETING_BY_LANGUAGE.en;
}

function mergeCopy(base: UICopy, override?: Partial<UICopy>): UICopy {
  return {
    ...base,
    ...(override ?? {}),
    status: {
      ...base.status,
      ...(override?.status ?? {}),
    },
    steps: {
      language: { ...base.steps.language, ...(override?.steps?.language ?? {}) },
      business: { ...base.steps.business, ...(override?.steps?.business ?? {}) },
      location: { ...base.steps.location, ...(override?.steps?.location ?? {}) },
      ownership: { ...base.steps.ownership, ...(override?.steps?.ownership ?? {}) },
      food: { ...base.steps.food, ...(override?.steps?.food ?? {}) },
    },
  };
}

function finalizeProfile(profile: IntakeProfile) {
  const next = { ...profile };
  const name = typeof next.entity_name === "string" ? next.entity_name.trim() : "";
  if (name && !name.toUpperCase().endsWith("LLC") && !name.toUpperCase().endsWith("L.L.C.")) {
    next.entity_name = `${name} LLC`;
  }
  if (next.city && !next.principal_city) next.principal_city = next.city;
  if (!next.state) next.state = "IL";
  return next;
}

export default function PlanClient() {
  const [profile, setProfile] = useState<IntakeProfile>({});
  const [stage, setStage] = useState<FlowStage>("language");
  const [turnNum, setTurnNum] = useState(1);
  const [question, setQuestion] = useState(LANGUAGE_PROMPT);
  const [languageCode, setLanguageCode] = useState("en");
  const [languageLabel, setLanguageLabel] = useState("English");
  const [dynamicCopy, setDynamicCopy] = useState<UICopy | null>(null);
  const [transcript, setTranscript] = useState("");
  const [recording, setRecording] = useState(false);
  const [micStatusKey, setMicStatusKey] = useState<MicStatusKey>("idle");
  const [speechLang, setSpeechLang] = useState("en-US");
  const [launching, setLaunching] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const latestTranscriptRef = useRef("");
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);

  const complete = stage === "complete";
  const copy = mergeCopy(UI_COPY.en, dynamicCopy ?? UI_COPY[languageCode]);
  const micStatus = copy.status[micStatusKey] ?? copy.status.idle;

  async function localizePageCopy(language: { code: string; label: string }) {
    const builtInCopy = UI_COPY[language.code];
    if (builtInCopy) {
      setDynamicCopy(null);
      return { copy: builtInCopy, greeting: greetingForLanguage(language.code) };
    }

    const response = await fetch("/api/plan/localize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        targetLanguage: language.label,
        sourceCopy: UI_COPY.en,
        sourceGreeting: GREETING_BY_LANGUAGE.en,
      }),
    });
    if (!response.ok) throw new Error("Localization failed");
    const localized = (await response.json()) as { copy?: Partial<UICopy>; greeting?: string };
    if (!localized.copy || !localized.greeting) throw new Error("Localization response incomplete");
    const nextCopy = mergeCopy(UI_COPY.en, localized.copy);
    setDynamicCopy(nextCopy);
    return { copy: nextCopy, greeting: localized.greeting };
  }

  async function speak(text: string) {
    activeAudioRef.current?.pause();
    activeAudioRef.current = null;

    try {
      const response = await fetch("/api/voice/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error("TTS request failed");

      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      activeAudioRef.current = audio;
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        if (activeAudioRef.current === audio) activeAudioRef.current = null;
      };
      await audio.play();
    } catch {
      setMicStatusKey("speechUnavailable");
    }
  }

  async function transcribeAudio(audioBlob: Blob) {
    const formData = new FormData();
    formData.set("audio", audioBlob, "answer.webm");
    formData.set("language", languageCode);

    const response = await fetch("/api/voice/stt", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error("STT request failed");
    const body = (await response.json()) as { text?: string };
    return body.text?.trim() ?? "";
  }

  async function persistAndOpen(nextProfile: IntakeProfile) {
    setLaunching(true);
    const finalProfile = finalizeProfile(nextProfile);
    window.localStorage.setItem(
      "shuxiang_plan",
      JSON.stringify({ workflow: "Illinois LLC filing", fields: finalProfile }),
    );
    setMicStatusKey("openingBrowser");

    try {
      const response = await fetch("/api/plan/launch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: finalProfile, language: languageCode }),
      });
      if (!response.ok) throw new Error("Launch failed");
      setMicStatusKey("browserOpened");
    } catch {
      setLaunching(false);
      setMicStatusKey("launchFailed");
    }
  }

  async function runIntakeTurn(answer: string) {
    const response = await fetch("/api/plan/intake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript: answer,
        profile,
        turnNum,
        language: languageLabel,
      }),
    });
    if (!response.ok) throw new Error("Plan intake failed");
    return (await response.json()) as {
      profile: IntakeProfile;
      nextAction: "ASK" | "FINISH";
      question: string;
    };
  }

  async function answerCurrentStep(rawAnswer: string) {
    const answer = rawAnswer.trim();
    if (!answer || complete) return;

    if (stage === "language") {
      const language = normalizeLanguage(answer);
      setLanguageCode(language.code);
      setLanguageLabel(language.label);
      setSpeechLang(language.speechLang);
      setMicStatusKey("thinking");
      let nextQuestion = greetingForLanguage(language.code);
      try {
        const localized = await localizePageCopy(language);
        nextQuestion = localized.greeting;
      } catch {
        setDynamicCopy(null);
      }
      setStage("intake");
      setTurnNum(1);
      setQuestion(nextQuestion);
      setTranscript("");
      setMicStatusKey("idle");
      void speak(nextQuestion);
      return;
    }

    setMicStatusKey("thinking");
    try {
      const result = await runIntakeTurn(answer);
      const nextProfile = result.profile;
      setProfile(nextProfile);
      setTurnNum((current) => current + 1);

      if (result.nextAction === "FINISH" || !result.question) {
        const finalProfile = finalizeProfile(nextProfile);
        setProfile(finalProfile);
        setStage("complete");
        setTranscript("");
        setQuestion(copy.openingQuestion);
        setMicStatusKey("planningComplete");
        void speak(copy.finalMessage);
        window.setTimeout(() => void persistAndOpen(finalProfile), 350);
        return;
      }

      setQuestion(result.question);
      setTranscript("");
      setMicStatusKey("idle");
      void speak(result.question);
    } catch {
      setMicStatusKey("intakeFailed");
    }
  }

  function openCurrentPlan() {
    const finalProfile = finalizeProfile(profile);
    setProfile(finalProfile);
    window.localStorage.setItem(
      "shuxiang_plan",
      JSON.stringify({ workflow: "Illinois LLC filing", fields: finalProfile }),
    );
    void persistAndOpen(finalProfile);
  }

  async function toggleRecording() {
    if (complete || launching) return;

    if (recording) {
      setMicStatusKey("processing");
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        mediaRecorderRef.current = null;
        setRecording(false);
        setMicStatusKey("idle");
      }
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !("MediaRecorder" in window)) {
      setMicStatusKey("typeInstead");
      return;
    }

    activeAudioRef.current?.pause();
    activeAudioRef.current = null;
    audioChunksRef.current = [];
    latestTranscriptRef.current = "";
    setTranscript("");

    try {
      mediaStreamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setRecording(false);
      setMicStatusKey("micBlocked");
      return;
    }

    setRecording(true);
    setMicStatusKey("recording");

    const preferredMimeType = "audio/webm;codecs=opus";
    const mediaRecorder = new MediaRecorder(
      mediaStreamRef.current,
      MediaRecorder.isTypeSupported(preferredMimeType) ? { mimeType: preferredMimeType } : undefined,
    );
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunksRef.current.push(event.data);
    };
    mediaRecorder.onstop = async () => {
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
      mediaRecorderRef.current = null;
      setRecording(false);

      const audioBlob = new Blob(audioChunksRef.current, { type: mediaRecorder.mimeType || "audio/webm" });
      if (!audioBlob.size) {
        setMicStatusKey("idle");
        return;
      }

      try {
        const finalText = await transcribeAudio(audioBlob);
        if (!finalText) {
          setMicStatusKey("didntCatch");
          return;
        }
        latestTranscriptRef.current = finalText;
        setTranscript(finalText);
        setMicStatusKey("thinking");
        window.setTimeout(() => answerCurrentStep(finalText), 650);
      } catch {
        setMicStatusKey("transcriptionFailed");
      }
    };
    mediaRecorderRef.current = mediaRecorder;
    mediaRecorder.start();
  }

  const helper = complete
    ? copy.helperComplete
    : stage === "language"
      ? copy.helperLanguage
      : copy.helperIntake;
  const activeStepIndex = complete ? FLOW_STEPS.length - 1 : stage === "language" ? 0 : Math.min(turnNum, FLOW_STEPS.length - 1);
  const progress = Math.min(activeStepIndex + 1, FLOW_STEPS.length);

  return (
    <div className="min-h-screen relative overflow-hidden" style={{ background: "var(--bg)" }}>
      <div
        className="fixed top-0 left-1/2 -translate-x-1/2 w-[980px] h-[520px] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center top, rgba(201,164,71,0.10) 0%, transparent 68%)",
        }}
      />
      <div
        className="fixed -bottom-48 -right-40 w-[540px] h-[540px] rounded-full pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(201,164,71,0.09), transparent 68%)",
        }}
      />

      <nav
        className="relative z-10 flex items-center justify-between px-8 py-5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <Link href="/" className="font-display text-xl italic" style={{ color: "var(--cream)" }}>
          Shu-Xiang
        </Link>
        <div
          className="hidden sm:flex text-xs tracking-widest uppercase px-3 py-1 rounded-full"
          style={{
            color: "var(--gold)",
            border: "1px solid var(--gold-border)",
            background: "var(--gold-glow)",
          }}
        >
          {copy.navBadge}
        </div>
      </nav>

      <button
        aria-pressed={recording}
        className={`sx-mic-btn ${recording ? "sx-mic-btn--listening" : ""}`}
        onClick={toggleRecording}
        type="button"
      >
        <span className="sx-mic-icon" aria-hidden="true">
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
          >
            <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
            <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
            <line x1="12" x2="12" y1="19" y2="23" />
            <line x1="8" x2="16" y1="23" y2="23" />
          </svg>
        </span>
        <span>{micStatus}</span>
      </button>

      <main className="relative z-10 min-h-[calc(100vh-73px)] px-6 py-10 lg:px-8">
        <section className="mx-auto grid min-h-[calc(100vh-150px)] max-w-7xl grid-cols-1 items-center gap-8 lg:grid-cols-[minmax(0,1fr)_330px]">
          <section className="flex justify-center">
            <div
              className="relative w-full max-w-3xl overflow-hidden rounded-[2rem] p-6 sm:p-8 lg:p-10"
              style={{
                border: "1px solid var(--border-bright)",
                background:
                  "linear-gradient(145deg, rgba(26,21,12,0.96), rgba(12,10,7,0.92) 62%, rgba(201,164,71,0.08))",
                boxShadow: "0 30px 90px rgba(0,0,0,0.34)",
              }}
            >
              <div
                className="absolute -right-20 -top-20 h-56 w-56 rounded-full"
                style={{ background: "radial-gradient(circle, rgba(201,164,71,0.16), transparent 70%)" }}
              />

              <div className="relative">
                <div className="mb-9 flex flex-wrap items-center justify-between gap-4">
                  <div
                    className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs tracking-widest uppercase"
                    style={{
                      color: "var(--gold)",
                      border: "1px solid var(--gold-border)",
                      background: "rgba(201,164,71,0.06)",
                    }}
                  >
                    <span className="sx-opening-mic-dot" />
                    <span>{recording ? copy.micOnBadge : complete ? copy.readyToFileBadge : copy.readyBadge}</span>
                  </div>
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {complete ? copy.planningComplete : `${progress} / ${FLOW_STEPS.length} · ${languageLabel}`}
                  </span>
                </div>

                <h2 className="font-display text-[clamp(1.9rem,3.6vw,3.25rem)] leading-[1.08] mb-7" style={{ color: "var(--cream)" }}>
                  {question}
                </h2>

                <textarea
                  value={transcript}
                  onChange={(event) => {
                    latestTranscriptRef.current = event.target.value;
                    setTranscript(event.target.value);
                  }}
                  onKeyDown={(event) => {
                    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                      event.preventDefault();
                      answerCurrentStep(transcript);
                    }
                  }}
                  placeholder={recording ? "" : helper}
                  rows={4}
                  className="sx-plan-textarea"
                />

                <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
                  <span className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>
                    {recording ? copy.recordingHint : copy.editHint}
                  </span>
                  <div className="flex gap-3">
              {complete && (
                <button
                  onClick={openCurrentPlan}
                  className="inline-flex items-center justify-center rounded-full px-5 py-3 text-sm font-medium"
                  style={{ border: "1px solid var(--border-bright)", color: "var(--text)", background: "var(--bg-card)" }}
                  type="button"
                >
                  {copy.startFiling}
                </button>
              )}
              {!complete && (
                <button
                  onClick={() => answerCurrentStep(transcript)}
                  disabled={!transcript.trim()}
                  className="relative inline-flex items-center justify-center rounded-full px-6 py-3 font-display text-lg italic overflow-hidden group"
                  style={{
                    border: 0,
                    background: "var(--gold)",
                    color: "var(--bg)",
                    cursor: transcript.trim() ? "pointer" : "not-allowed",
                    opacity: transcript.trim() ? 1 : 0.4,
                  }}
                  type="button"
                >
                  <span
                    className="absolute inset-0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700"
                    style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent)" }}
                  />
                  <span className="relative">{copy.continue}</span>
                </button>
              )}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <aside
            className="rounded-[1.75rem] p-5 lg:sticky lg:top-28"
            style={{
              border: "1px solid var(--border-bright)",
              background: "linear-gradient(180deg, rgba(19,16,8,0.88), rgba(12,10,7,0.82))",
              boxShadow: "0 24px 70px rgba(0,0,0,0.24)",
            }}
          >
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs tracking-[0.25em] uppercase" style={{ color: "var(--gold)" }}>
                  {copy.checklistEyebrow}
                </div>
                  <div className="mt-1 font-display text-xl" style={{ color: "var(--cream)" }}>
                  {complete ? copy.readyToFile : `${progress} / ${FLOW_STEPS.length}`}
                </div>
              </div>
              <div
                className="rounded-full px-3 py-1 text-xs"
                style={{ color: "var(--gold)", border: "1px solid var(--gold-border)", background: "var(--gold-glow)" }}
              >
                {languageLabel}
              </div>
            </div>

            <div className="space-y-3">
              {FLOW_STEPS.map((step, index) => {
                const active = index === activeStepIndex && !complete;
                const done = index < activeStepIndex || complete;
                return (
                  <div
                    key={step.key}
                    className="flex items-start gap-3 rounded-2xl px-3 py-3"
                    style={{
                      border: `1px solid ${active ? "var(--gold-border)" : "var(--border)"}`,
                      background: active ? "var(--gold-glow)" : "rgba(12,10,7,0.36)",
                    }}
                  >
                    <span
                      className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs"
                      style={{
                        color: done ? "var(--bg)" : active ? "var(--gold)" : "var(--text-muted)",
                        background: done ? "var(--gold)" : "transparent",
                        border: `1px solid ${done || active ? "var(--gold-border)" : "var(--border-bright)"}`,
                      }}
                    >
                      {done ? "✓" : index + 1}
                    </span>
                    <div>
                      <div className="font-display text-base leading-none" style={{ color: active ? "var(--cream)" : "var(--text)" }}>
                        {copy.steps[step.key].label}
                      </div>
                      <div className="mt-1 text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>
                        {done ? copy.captured : active ? copy.steps[step.key].description : copy.upNext}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </aside>
        </section>
      </main>
    </div>
  );
}
