"""
Small localization layer for the demo UI.

Chinese remains the source copy. `SHUXIANG_LANGUAGE` can be set to a language
name or code such as "en", "es", "Spanish", "ar", or "Arabic". Known Chinese
and English strings are deterministic; other languages are translated at runtime
with Anthropic when `ANTHROPIC_API_KEY` is available, then cached in-process.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any
import json

from corpus.il_llc_corpus import SIDEBAR_LABELS_ZH, FieldSpec
from corpus.requirements import Requirement

Language = str


_LANG_ALIASES = {
    "zh": "zh",
    "zh-cn": "zh",
    "zh_cn": "zh",
    "chinese": "zh",
    "mandarin": "zh",
    "中文": "zh",
    "en": "en",
    "en-us": "en",
    "en_us": "en",
    "english": "en",
    "ko": "ko",
    "ko-kr": "ko",
    "ko_kr": "ko",
    "korean": "ko",
    "한국어": "ko",
    "한국말": "ko",
    "es": "Spanish",
    "spanish": "Spanish",
    "español": "Spanish",
    "fr": "French",
    "french": "French",
    "de": "German",
    "german": "German",
    "ja": "Japanese",
    "japanese": "Japanese",
    "日本語": "Japanese",
    "ar": "Arabic",
    "arabic": "Arabic",
    "hi": "Hindi",
    "hindi": "Hindi",
    "ru": "Russian",
    "russian": "Russian",
    "pt": "Portuguese",
    "portuguese": "Portuguese",
    "it": "Italian",
    "italian": "Italian",
    "vi": "Vietnamese",
    "vietnamese": "Vietnamese",
    "th": "Thai",
    "thai": "Thai",
}


_STRINGS_ZH: dict[str, str] = {
    "language_prompt": "你想使用哪种语言？请点击麦克风，说出语言名称，比如韩语、西班牙语或普通话。",
    "language_selected": "语言已设置为 {selected_language}。",
    "opening_prompt": "麦克风已开启。请用一句话告诉我你要开的生意。",
    "demo_sentence": "我想在芝加哥开一家四川餐厅，叫 Shu Xiang，我是唯一所有者。",
    "live_voice_toast": "请点击麦克风，用自己的话告诉我你的生意。",
    "listening": "正在聆听…",
    "checklist_header": "为你的餐厅定制的清单",
    "checklist_subtitle": "{count} 项, 按顺序处理",
    "checklist_summary": "我会按顺序处理这些事项，并在每一步解释为什么需要它。",
    "next_step_toast": "LLC 已提交。下一步是申请 EIN。",
    "pdf_generating": "正在生成双语 PDF 摘要…",
    "pdf_done": "PDF 已生成: {filename}",
    "closing_message": "12 项义务已识别 · 1 项已提交 · 1 项等待 EIN · 剩余 10 项使用同一套架构",
    "stage_error": "阶段失败: {stage}",
    "real_site_payment_stop": "已到达付款页面 ($150) — 演示在此停止",
    "real_site_submit_stop": "已到达提交确认页面 — 演示在此停止 (避免真实付款)",
    "real_site_unknown_stop": "到达未映射的页面 — 演示停止",
    "overlay_listening": "正在聆听…",
    "overlay_thinking": "正在思考…",
    "overlay_recorded": "已记录",
    "overlay_retry": "请再说一次",
    "overlay_recognizing": "识别中…",
    "overlay_transcript": "实时转写",
    "overlay_extracted_fields": "提取字段",
    "overlay_empty_value": "—",
    "overlay_mic_ready": "麦克风已开启 · 请说话",
    "overlay_mic_idle": "点击录音",
    "overlay_mic_recording": "录音中 · 点击停止",
    "overlay_checklist_eyebrow": "你的合规清单 · OBLIGATIONS MAP",
    "overlay_checklist_title": "为你的餐厅定制的清单",
    "overlay_checklist_subtitle": "{count} 项, 按顺序处理",
    "overlay_citation": "引用 →",
    "overlay_hour": "约 {n} 小时",
    "overlay_minute": "约 {n} 分钟",
    "overlay_free": "免费",
    # REG-1 (wow #3 — dependency-recognition beat)
    "reg1_transition_toast": "下一步:伊利诺伊州税务登记 — 同一个代理人,不同的表格",
    "reg1_navigating_toast": "正在打开 MyTax Illinois…",
    "reg1_form_started_toast": "REG-1 表已打开 — 自动填入你的公司信息",
    "reg1_fein_pause_question": "联邦税号 (Federal EIN)",
    "reg1_fein_pause_explanation": "你的 LLC 提交后会收到这个号码,通常 1-2 周。收到后我会自动完成这份登记 — 同样的代理人,同样的流程。",
    "reg1_paused_status": "代理人已暂停 · 等你完成 LLC 提交,我会自动继续",
    "reg1_closing_message": "12 项义务已识别 · 1 项已提交 · 1 项等待 EIN · 剩余 10 项使用同一套架构",
    # Validation guardrail — spoken when parsed answer doesn't look right
    "normalize_retry_hint": "我没听清楚 — 能再说一遍吗？",
}


_STRINGS_EN: dict[str, str] = {
    "language_prompt": "What language would you like to use? Click the microphone and say a language, for example Korean, Spanish, or Mandarin.",
    "language_selected": "Language set to {selected_language}.",
    "opening_prompt": "Microphone is on. Tell me about the business you want to start.",
    "demo_sentence": "I want to open a Sichuan restaurant in Chicago called Shu Xiang. I am the only owner.",
    "live_voice_toast": "Click the microphone and describe your business in your own words.",
    "listening": "Listening...",
    "checklist_header": "Checklist tailored to your restaurant",
    "checklist_subtitle": "{count} items, handled in order",
    "checklist_summary": "I will handle these in order and explain why each step matters.",
    "next_step_toast": "LLC submitted. Next step: apply for an EIN.",
    "pdf_generating": "Generating bilingual PDF summary...",
    "pdf_done": "PDF generated: {filename}",
    "closing_message": "12 obligations identified · 1 filed · 1 awaiting EIN · same architecture for the remaining 10",
    "stage_error": "Stage failed: {stage}",
    "real_site_payment_stop": "Reached the payment page ($150). Demo stops here.",
    "real_site_submit_stop": "Reached the submission confirmation page. Demo stops here to avoid real payment.",
    "real_site_unknown_stop": "Reached an unmapped page. Demo stopped.",
    "overlay_listening": "Listening...",
    "overlay_thinking": "Thinking...",
    "overlay_recorded": "Recorded",
    "overlay_retry": "Please try again",
    "overlay_recognizing": "Recognizing...",
    "overlay_transcript": "Transcript",
    "overlay_extracted_fields": "Extracted fields",
    "overlay_empty_value": "—",
    "overlay_mic_ready": "Microphone is on · please speak",
    "overlay_mic_idle": "Tap to record",
    "overlay_mic_recording": "Recording · tap to stop",
    "overlay_checklist_eyebrow": "Your Compliance Checklist · OBLIGATIONS MAP",
    "overlay_checklist_title": "Checklist tailored to your restaurant",
    "overlay_checklist_subtitle": "{count} items, handled in order",
    "overlay_citation": "Source →",
    "overlay_hour": "about {n} hour(s)",
    "overlay_minute": "about {n} minute(s)",
    "overlay_free": "free",
    # REG-1 (wow #3 — dependency-recognition beat)
    "reg1_transition_toast": "Next: Illinois business registration — same agent, different form",
    "reg1_navigating_toast": "Opening MyTax Illinois...",
    "reg1_form_started_toast": "REG-1 opened — filling in your company info",
    "reg1_fein_pause_question": "Federal EIN",
    "reg1_fein_pause_explanation": "Your LLC's federal EIN arrives 1-2 weeks after submission. I'll finish this registration automatically once you have it — same agent, same flow.",
    "reg1_paused_status": "Agent paused · will auto-continue once your LLC is submitted",
    "reg1_closing_message": "12 obligations identified · 1 filed · 1 awaiting EIN · same architecture for the remaining 10",
    # Validation guardrail — spoken when parsed answer doesn't look right
    "normalize_retry_hint": "I didn't quite catch that — could you say it again?",
}


_STRINGS_KO: dict[str, str] = {
    "language_prompt": "어떤 언어로 진행할까요? 마이크를 클릭하고 한국어, 스페인어, 중국어처럼 원하는 언어를 말씀해 주세요.",
    "language_selected": "언어가 {selected_language}(으)로 설정되었습니다.",
    "opening_prompt": "마이크가 켜져 있습니다. 시작하려는 사업을 한 문장으로 설명해 주세요.",
    "demo_sentence": "시카고에서 Shu Xiang이라는 쓰촨 음식점을 열고 싶습니다. 저는 단독 소유자입니다.",
    "live_voice_toast": "마이크를 클릭하고 본인의 말로 사업을 설명해 주세요.",
    "listening": "듣는 중...",
    "checklist_header": "식당에 맞춘 체크리스트",
    "checklist_subtitle": "{count}개 항목, 순서대로 진행",
    "checklist_summary": "이 항목들을 순서대로 처리하고 각 단계가 왜 필요한지 설명하겠습니다.",
    "next_step_toast": "LLC 제출 완료. 다음 단계는 EIN 신청입니다.",
    "pdf_generating": "이중 언어 PDF 요약을 생성하는 중...",
    "pdf_done": "PDF 생성 완료: {filename}",
    "closing_message": "12개 의무 식별 · 1개 제출 완료 · 1개 EIN 대기 중 · 나머지 10개도 동일한 아키텍처",
    "stage_error": "단계 실패: {stage}",
    "real_site_payment_stop": "결제 페이지($150)에 도착했습니다. 데모는 여기서 중지합니다.",
    "real_site_submit_stop": "제출 확인 페이지에 도착했습니다. 실제 결제를 피하기 위해 데모를 중지합니다.",
    "real_site_unknown_stop": "매핑되지 않은 페이지에 도착했습니다. 데모를 중지합니다.",
    "overlay_listening": "듣는 중...",
    "overlay_thinking": "생각하는 중...",
    "overlay_recorded": "기록됨",
    "overlay_retry": "다시 말씀해 주세요",
    "overlay_recognizing": "인식 중...",
    "overlay_transcript": "실시간 자막",
    "overlay_extracted_fields": "추출된 필드",
    "overlay_empty_value": "—",
    "overlay_mic_ready": "마이크가 켜져 있습니다 · 말씀해 주세요",
    "overlay_mic_idle": "녹음하려면 클릭",
    "overlay_mic_recording": "녹음 중 · 중지하려면 클릭",
    "overlay_checklist_eyebrow": "나의 컴플라이언스 체크리스트 · OBLIGATIONS MAP",
    "overlay_checklist_title": "식당에 맞춘 체크리스트",
    "overlay_checklist_subtitle": "{count}개 항목, 순서대로 진행",
    "overlay_citation": "출처 →",
    "overlay_hour": "약 {n}시간",
    "overlay_minute": "약 {n}분",
    "overlay_free": "무료",
    # REG-1 (wow #3 — dependency-recognition beat)
    "reg1_transition_toast": "다음: 일리노이주 사업자 등록 — 같은 에이전트, 다른 양식",
    "reg1_navigating_toast": "MyTax Illinois를 여는 중…",
    "reg1_form_started_toast": "REG-1 열림 — 회사 정보를 자동으로 입력 중",
    "reg1_fein_pause_question": "연방 세금 ID (EIN)",
    "reg1_fein_pause_explanation": "LLC 제출 후 1-2주 안에 EIN을 받게 됩니다. EIN을 받으시면 같은 에이전트, 같은 흐름으로 이 등록을 자동으로 완료합니다.",
    "reg1_paused_status": "에이전트 일시 중지 · LLC 제출 후 자동으로 계속됩니다",
    "reg1_closing_message": "12개 의무 식별 · 1개 제출 완료 · 1개 EIN 대기 중 · 나머지 10개도 동일한 아키텍처",
    # Validation guardrail — spoken when parsed answer doesn't look right
    "normalize_retry_hint": "잘 들리지 않았어요 — 다시 말씀해 주시겠어요?",
}


_BUILTIN_STRINGS: dict[str, dict[str, str]] = {
    "zh": _STRINGS_ZH,
    "en": _STRINGS_EN,
    "ko": _STRINGS_KO,
}


def _normalize_language(raw: str | None) -> Language:
    value = (raw or "").strip()
    if not value:
        return "zh"
    return _LANG_ALIASES.get(value.lower(), value)


_LANGUAGE_UTTERANCE_MARKERS: tuple[tuple[str, str], ...] = (
    ("ko", "korean"),
    ("ko", "한국어"),
    ("ko", "한국말"),
    ("ko", "조선말"),
    ("en", "english"),
    ("en", "영어"),
    ("zh", "mandarin"),
    ("zh", "chinese"),
    ("zh", "中文"),
    ("zh", "普通话"),
    ("Spanish", "spanish"),
    ("Spanish", "español"),
    ("Spanish", "espanol"),
    ("Spanish", "스페인어"),
    ("French", "french"),
    ("French", "français"),
    ("French", "프랑스어"),
    ("German", "german"),
    ("German", "deutsch"),
    ("German", "독일어"),
    ("Japanese", "japanese"),
    ("Japanese", "日本語"),
    ("Japanese", "일본어"),
    ("Arabic", "arabic"),
    ("Arabic", "العربية"),
    ("Hindi", "hindi"),
    ("Russian", "russian"),
    ("Portuguese", "portuguese"),
    ("Italian", "italian"),
    ("Vietnamese", "vietnamese"),
    ("Thai", "thai"),
)


def language_from_utterance(transcript: str, fallback: Language = "en") -> Language:
    """Infer the requested language from the first spoken answer."""
    text = (transcript or "").strip().lower()
    if not text:
        return fallback
    for language, marker in _LANGUAGE_UTTERANCE_MARKERS:
        if marker.lower() in text:
            return _normalize_language(language)
    # If Scribe transcribed only the bare language code/name, normalize it.
    normalized = _normalize_language(text)
    if normalized != text or normalized in _BUILTIN_STRINGS:
        return normalized
    return fallback


def language_display_name(language: Language) -> str:
    lang = _normalize_language(language)
    return {
        "zh": "中文",
        "en": "English",
        "ko": "한국어",
    }.get(lang, str(language))


def language_from_env() -> Language:
    """Return the requested UI language. Defaults to Chinese for the demo."""
    for key in ("SHUXIANG_LANGUAGE", "DEMO_LANGUAGE", "APP_LANGUAGE"):
        if os.environ.get(key):
            return _normalize_language(os.environ[key])
    return "zh"


def _base_strings(language: Language) -> dict[str, str]:
    return _BUILTIN_STRINGS.get(_normalize_language(language), _STRINGS_ZH)


def _translation_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    from anthropic import Anthropic

    return Anthropic(api_key=api_key)


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return stripped[start : end + 1]
    return stripped


@lru_cache(maxsize=512)
def _translate(text: str, target_language: Language, source_language: str = "Chinese") -> str:
    target = _normalize_language(target_language)
    if not text or target == "zh":
        return text
    if target in _BUILTIN_STRINGS and text in _STRINGS_ZH.values():
        builtin = _BUILTIN_STRINGS[target]
        for key, value in _STRINGS_ZH.items():
            if value == text:
                return builtin.get(key, text)

    client = _translation_client()
    if client is None:
        return text

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=(
                "Translate UI copy for a legal/business filing assistant. "
                "Preserve company names, URLs, dollar amounts, enum values, and placeholders like {count}. "
                "Return only the translated text."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Source language: {source_language}\n"
                        f"Target language: {target_language}\n\n"
                        f"{text}"
                    ),
                }
            ],
        )
        for block in msg.content:
            if block.type == "text":
                return block.text.strip()
    except Exception:
        return text
    return text


@lru_cache(maxsize=128)
def _translate_mapping(items_json: str, target_language: Language, source_language: str = "Chinese") -> dict[str, str]:
    """Translate a dict of UI strings in one model call."""
    target = _normalize_language(target_language)
    items = json.loads(items_json)
    if target == "zh":
        return dict(items)

    client = _translation_client()
    if client is None:
        return dict(items)

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            system=(
                "Translate UI copy for a legal/business filing assistant. "
                "Return only a JSON object with exactly the same keys. "
                "Preserve company names, URLs, dollar amounts, enum values, and placeholders like {count} or {n}."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Source language: {source_language}\n"
                        f"Target language: {target_language}\n\n"
                        f"{items_json}"
                    ),
                }
            ],
        )
        for block in msg.content:
            if block.type == "text":
                parsed = json.loads(_extract_json_object(block.text))
                return {
                    key: str(parsed.get(key, value))
                    for key, value in items.items()
                }
    except Exception:
        return dict(items)
    return dict(items)


def localize(text: str | None, language: Language, source_language: str = "Chinese") -> str:
    if text is None:
        return ""
    lang = _normalize_language(language)
    if lang == "zh":
        return text
    return _translate(text, lang, source_language)


def localize_mapping(items: dict[str, str], language: Language, source_language: str = "Chinese") -> dict[str, str]:
    """Translate a group of related strings in one request when needed."""
    lang = _normalize_language(language)
    if lang == "zh":
        return dict(items)
    if lang in _BUILTIN_STRINGS:
        return {
            key: localize(value, lang, source_language)
            for key, value in items.items()
        }
    return _translate_mapping(
        json.dumps(items, ensure_ascii=False, sort_keys=True),
        lang,
        source_language,
    )


def t(key: str, language: Language, **kwargs: Any) -> str:
    lang = _normalize_language(language)
    if lang in _BUILTIN_STRINGS:
        template = _BUILTIN_STRINGS[lang].get(key, _STRINGS_ZH.get(key, key))
    else:
        template = _translate(_STRINGS_ZH.get(key, key), lang)
    if not kwargs:
        return template
    return template.format(**kwargs)


def sidebar_label(schema_key: str, fallback: str, language: Language) -> str:
    return localize(SIDEBAR_LABELS_ZH.get(schema_key, fallback), language)


_SIDEBAR_LABELS_EN = {
    "entity_name": "Company name",
    "principal_address": "Address",
    "principal_city": "City",
    "principal_zip": "ZIP code",
    "management_structure": "Management structure",
    "duration": "Duration",
    "registered_agent_name": "Registered agent",
    "registered_agent_address": "Agent address",
    "organizer_name": "Organizer",
    "organizer_email": "Email",
    "organizer_phone": "Phone",
}

_SIDEBAR_LABELS_KO = {
    "entity_name": "회사명",
    "principal_address": "주소",
    "principal_city": "도시",
    "principal_zip": "우편번호",
    "management_structure": "관리 구조",
    "duration": "존속 기간",
    "registered_agent_name": "등록 대리인",
    "registered_agent_address": "대리인 주소",
    "organizer_name": "신청자",
    "organizer_email": "이메일",
    "organizer_phone": "전화번호",
}


def sidebar_labels(schema_keys: list[tuple[str, str]], language: Language) -> dict[str, str]:
    """Return localized sidebar labels for many fields with batched translation."""
    lang = _normalize_language(language)
    if lang == "en":
        return {
            schema_key: _SIDEBAR_LABELS_EN.get(schema_key, fallback)
            for schema_key, fallback in schema_keys
        }
    if lang == "ko":
        return {
            schema_key: _SIDEBAR_LABELS_KO.get(schema_key, fallback)
            for schema_key, fallback in schema_keys
        }
    source = {
        schema_key: SIDEBAR_LABELS_ZH.get(schema_key, fallback)
        for schema_key, fallback in schema_keys
    }
    return localize_mapping(source, language)


def field_question(field: FieldSpec, language: Language) -> str:
    return localize(field.question_zh, language)


def field_explanation(field: FieldSpec, language: Language) -> str:
    return localize(field.explanation_zh, language)


def requirement_item(requirement: Requirement, language: Language) -> dict[str, Any]:
    return {
        "id": requirement.id,
        "titleZh": localize(requirement.title_zh, language),
        "titleEn": requirement.title_en,
        "jurisdiction": requirement.jurisdiction,
        "descZh": localize(requirement.description_zh, language),
        "citationUrl": requirement.citation_url,
        "timeMin": requirement.estimated_time_minutes,
        "costUsd": requirement.estimated_cost_usd,
    }


def requirement_items(requirements: list[Requirement], language: Language) -> list[dict[str, Any]]:
    """Return localized checklist items, batching translation for non-built-in languages."""
    strings: dict[str, str] = {}
    for requirement in requirements:
        strings[f"{requirement.id}.title"] = requirement.title_zh
        strings[f"{requirement.id}.desc"] = requirement.description_zh

    translated = localize_mapping(strings, language)
    return [
        {
            "id": requirement.id,
            "titleZh": translated.get(f"{requirement.id}.title", requirement.title_zh),
            "titleEn": requirement.title_en,
            "jurisdiction": requirement.jurisdiction,
            "descZh": translated.get(f"{requirement.id}.desc", requirement.description_zh),
            "citationUrl": requirement.citation_url,
            "timeMin": requirement.estimated_time_minutes,
            "costUsd": requirement.estimated_cost_usd,
        }
        for requirement in requirements
    ]


def overlay_copy(language: Language) -> dict[str, str]:
    """Labels consumed by overlay/inject.js. Values may contain {count} or {n}."""
    keys = {
        "listening": "overlay_listening",
        "thinking": "overlay_thinking",
        "recorded": "overlay_recorded",
        "retry": "overlay_retry",
        "recognizing": "overlay_recognizing",
        "transcript": "overlay_transcript",
        "extractedFields": "overlay_extracted_fields",
        "emptyValue": "overlay_empty_value",
        "micReady": "overlay_mic_ready",
        "micIdle": "overlay_mic_idle",
        "micRecording": "overlay_mic_recording",
        "checklistEyebrow": "overlay_checklist_eyebrow",
        "checklistTitle": "overlay_checklist_title",
        "checklistSubtitle": "overlay_checklist_subtitle",
        "citation": "overlay_citation",
        "hour": "overlay_hour",
        "minute": "overlay_minute",
        "free": "overlay_free",
    }
    lang = _normalize_language(language)
    source = {copy_key: _STRINGS_ZH[string_key] for copy_key, string_key in keys.items()}
    if lang == "zh":
        return source
    if lang in _BUILTIN_STRINGS:
        strings = _BUILTIN_STRINGS[lang]
        return {copy_key: strings[string_key] for copy_key, string_key in keys.items()}
    return _translate_mapping(
        json.dumps(source, ensure_ascii=False, sort_keys=True),
        lang,
    )
