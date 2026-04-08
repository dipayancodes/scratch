from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
import json
import logging
import re


log = logging.getLogger(__name__)
FALLBACK_MODELS = (
    "llama3-8b-8192",
    "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile",
)

SYSTEM_PROMPT = (
    "You are a concise study assistant for students. "
    "Explain clearly, stay practical, and structure answers so they help revision and retention."
)
ASK_SYSTEM_PROMPT = (
    "You are a concise study assistant for students.\n"
    "Answer with the minimum useful help for the exact question.\n"
    "Default to 1 to 5 short sentences.\n"
    "Only go longer when the user explicitly asks for detail, steps, or examples.\n"
    "Avoid filler, repetition, and long intros."
)
MESSAGE_MODERATION_PROMPT = (
    "You are moderating one Discord message for a study server.\n"
    "Return exactly one line in this format: label|short reason\n"
    "Allowed labels:\n"
    "- allow\n"
    "- non_english\n"
    "- gibberish\n"
    "- explicit\n"
    "- abusive\n"
    "Use non_english when the message is mainly another language or romanized non-English.\n"
    "Use gibberish when it is unreadable, nonsense, or not meaningful English.\n"
    "Use explicit when it is sexual, vulgar, obscene, slur-heavy, or clearly inappropriate slang.\n"
    "Use abusive when it is insulting, harassing, baiting, demeaning, threatening, or hostile arguing.\n"
    "Treat short English slang like lol, bro, brb, lmao, ok, yup as allow unless it is vulgar or abusive.\n"
    "Treat harmless jokes as allow, but hostile jokes targeting a person as abusive.\n"
    "If unsure, choose allow.\n"
    "Do not add markdown or extra explanation."
)
PLAN_SYSTEM_PROMPT = (
    "You create short, practical study plans.\n"
    "Return only JSON.\n"
    "Make each day minimal but useful.\n"
    "Each day should have 1 to 3 short tasks, not long paragraphs."
)
SAFE_SHORT_ENGLISH = {
    "aight",
    "alr",
    "brb",
    "bro",
    "cool",
    "fine",
    "gg",
    "hi",
    "hmm",
    "k",
    "kk",
    "lmao",
    "lol",
    "nah",
    "nice",
    "nope",
    "ok",
    "okay",
    "pls",
    "sure",
    "thx",
    "ty",
    "wait",
    "what",
    "yep",
    "yo",
    "yup",
}
FALLBACK_EXPLICIT_WORDS = {
    "bastard",
    "bitch",
    "cock",
    "cunt",
    "damn",
    "dick",
    "fucker",
    "fucking",
    "fuck",
    "motherfucker",
    "nigger",
    "porn",
    "pornography",
    "pussy",
    "retard",
    "shit",
    "slut",
    "whore",
}
FALLBACK_ABUSIVE_MARKERS = (
    "are you stupid",
    "dumbass",
    "fuck you",
    "idiot",
    "kill yourself",
    "loser",
    "moron",
    "nobody likes you",
    "piece of shit",
    "shut up",
    "stfu",
    "screw you",
    "trash",
    "ugly rat",
    "you suck",
)
COMMON_ENGLISH_HINTS = {
    "about",
    "after",
    "because",
    "bro",
    "could",
    "exam",
    "have",
    "hello",
    "please",
    "study",
    "thanks",
    "there",
    "think",
    "what",
    "when",
    "where",
    "which",
    "why",
    "will",
    "would",
}


@dataclass(frozen=True, slots=True)
class ModerationDecision:
    label: str
    reason: str


class StudyAI:
    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.client = None
        self.last_error: str | None = None
        self.last_model: str | None = None
        self.status_reason = "missing_key" if not api_key else "ready"
        self._request_semaphore = asyncio.Semaphore(3)
        if api_key:
            try:
                from groq import AsyncGroq

                self.client = AsyncGroq(api_key=api_key)
            except Exception:
                self.client = None
                self.status_reason = "missing_dependency"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.client is not None)

    async def ask(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "Ask a clear study question and I will help you break it down."
        max_tokens = self._ask_token_budget(question)
        if self.enabled:
            result, error = await self._create_completion(
                system_prompt=ASK_SYSTEM_PROMPT,
                prompt=question,
                temperature=0.2,
                max_tokens=max_tokens,
                top_p=0.85,
            )
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()
            if error == "transport":
                return self._transport_error_message()
        return self._fallback_answer(question)

    async def summarize(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return "Send some study text and I will summarize it."
        if self.enabled:
            prompt = f"Summarize the following for a student in short bullet points.\n\nText:\n{text}"
            result, error = await self._call_groq(prompt)
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()
            if error == "transport":
                return self._transport_error_message()

        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = sentences[:3]
        keywords = self._keywords(text)
        lines = ["Summary:"]
        for sentence in summary:
            if sentence:
                lines.append(f"- {sentence.strip()}")
        if keywords:
            lines.append(f"Keywords: {', '.join(keywords[:6])}")
        return "\n".join(lines)

    async def analyze_text(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return "Upload a text file with usable study material and I will analyze it."
        if self.enabled:
            prompt = f"Extract key points, likely exam topics, and revision tips from this study material.\n\nContent:\n{text}"
            result, error = await self._call_groq(prompt)
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()
            if error == "transport":
                return self._transport_error_message()
        keywords = self._keywords(text)
        lines = text.splitlines()
        useful_lines = [line.strip() for line in lines if line.strip()][:5]
        result = ["Key points:"]
        for line in useful_lines:
            result.append(f"- {line[:160]}")
        if keywords:
            result.append(f"High-signal terms: {', '.join(keywords[:8])}")
        result.append("Revision tip: turn each key point into a question-answer flashcard.")
        return "\n".join(result)

    async def generate_plan(self, exam: str, days: int) -> str:
        entries = await self.generate_plan_entries(exam, days)
        exam = (exam or "").strip()
        if not exam:
            return "Give me the exam name and the number of days available."
        return self._format_plan_entries(exam, entries)

    async def generate_plan_entries(self, exam: str, days: int) -> list[dict[str, object]]:
        exam = (exam or "").strip()
        if not exam:
            return []
        days = max(1, min(int(days), 30))
        if self.enabled:
            prompt = (
                f"Exam: {exam}\n"
                f"Days available: {days}\n\n"
                f"Return a JSON array with exactly {days} objects.\n"
                "Each object must contain:\n"
                '- "day_title": a very short label for the day\n'
                '- "tasks": an array of 1 to 3 short study tasks\n'
                "Keep the workload realistic and concise."
            )
            result, error = await self._create_completion(
                system_prompt=PLAN_SYSTEM_PROMPT,
                prompt=prompt,
                temperature=0.3,
                max_tokens=min(2400, 140 * days + 200),
                top_p=0.9,
            )
            entries = self._parse_plan_entries(result, days)
            if entries:
                return entries
            if error == "auth":
                return self._fallback_plan_entries(exam, days)
            if error == "transport":
                return self._fallback_plan_entries(exam, days)

        return self._fallback_plan_entries(exam, days)

    async def classify_language(self, text: str) -> str | None:
        text = (text or "").strip()
        if not text:
            return "english"
        decision = await self.moderate_message(text)
        if decision.label in {"non_english", "gibberish"}:
            return "non-english"
        return "english"

    async def moderate_message(self, text: str) -> ModerationDecision:
        text = (text or "").strip()
        if not text:
            return ModerationDecision("allow", "empty message")
        if self.enabled:
            result, error = await self._create_completion(
                system_prompt=MESSAGE_MODERATION_PROMPT,
                prompt=f"Message:\n{text}",
                temperature=0.0,
                max_tokens=60,
                top_p=1.0,
            )
            decision = self._parse_moderation_decision(result)
            if decision is not None:
                return decision
            if error is not None:
                log.warning("Falling back to heuristic moderation after AI moderation failure: %s", error)
        return self._fallback_moderation(text)

    async def _call_groq(self, prompt: str) -> tuple[str | None, str | None]:
        return await self._create_completion(
            system_prompt=SYSTEM_PROMPT,
            prompt=prompt,
            temperature=0.4,
            max_tokens=1400,
            top_p=0.9,
        )

    async def _create_completion(
        self,
        *,
        system_prompt: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        top_p: float,
    ) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, None
        candidate_models = [self.model, *[model for model in FALLBACK_MODELS if model != self.model]]
        self.last_error = None
        for model_name in candidate_models:
            self.last_model = model_name
            try:
                async with self._request_semaphore:
                    response = await self.client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens,
                        top_p=top_p,
                    )
                content = response.choices[0].message.content if response.choices else ""
                clean = (content or "").strip()
                if model_name != self.model:
                    log.warning("Groq request used fallback model %s instead of configured model %s.", model_name, self.model)
                return (clean or "I could not generate a complete response for that request."), None
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                class_name = exc.__class__.__name__.lower()
                message = f"{exc.__class__.__name__}: {exc}"
                self.last_error = message
                if status_code == 401 or "auth" in class_name:
                    return None, "auth"
                lowered = str(exc).lower()
                if status_code in {400, 404} or "model" in lowered or "decommissioned" in lowered or "not found" in lowered:
                    log.warning("Groq model %s failed: %s", model_name, message)
                    continue
                log.warning("Groq request failed with model %s: %s", model_name, message)
                return None, "transport"
        return None, "transport"

    def _auth_error_message(self) -> str:
        return (
            "Groq authentication failed. Your `GROQ_API_KEY` in `.env` is missing, invalid, or expired.\n"
            "Update the key, save `.env`, and restart the bot."
        )

    def _transport_error_message(self) -> str:
        detail = f" Last error: {self.last_error}" if self.last_error else ""
        model = f" Model: {self.last_model or self.model}." if (self.last_model or self.model) else ""
        return f"Groq is configured, but the API request failed.{model} Check network access, deployment secrets, and the selected model.{detail}"

    def _unavailable_message(self) -> str:
        if self.status_reason == "missing_dependency":
            return "Groq is configured in code, but the `groq` Python package is not installed in this runtime."
        if self.status_reason == "missing_key":
            return "Groq is not configured because `GROQ_API_KEY` is missing from the environment."
        return "Groq AI is unavailable right now."

    def _ask_token_budget(self, question: str) -> int:
        lowered = question.lower()
        if any(phrase in lowered for phrase in ("step by step", "detailed", "in detail", "full answer", "full explanation", "examples")):
            return 600
        if len(question) <= 120:
            return 220
        return 320

    def _fallback_answer(self, question: str) -> str:
        compact = question.strip().rstrip("?")
        if not compact:
            return "Ask a clear study question and I will keep the answer short."
        return (
            f"{self._unavailable_message()}\n\n"
            f"Short fallback: focus on `{compact}` by learning the definition, one example, and one common mistake."
        )

    def _parse_moderation_decision(self, raw: str | None) -> ModerationDecision | None:
        if not raw:
            return None
        line = raw.strip().splitlines()[0]
        if "|" not in line:
            return None
        label, reason = line.split("|", 1)
        normalized = label.strip().lower().replace("-", "_")
        if normalized not in {"allow", "non_english", "gibberish", "explicit", "abusive"}:
            return None
        clean_reason = re.sub(r"\s+", " ", reason).strip()[:140] or self._default_reason(normalized)
        return ModerationDecision(normalized, clean_reason)

    def _default_reason(self, label: str) -> str:
        reasons = {
            "allow": "safe message",
            "non_english": "message was not mainly English",
            "gibberish": "message was not clear English",
            "explicit": "message contained vulgar or explicit language",
            "abusive": "message looked insulting or hostile",
        }
        return reasons.get(label, "message was flagged")

    def _fallback_moderation(self, text: str) -> ModerationDecision:
        lowered = text.lower()
        tokens = set(re.findall(r"[a-z0-9']+", lowered))
        if any(token in FALLBACK_EXPLICIT_WORDS for token in tokens):
            return ModerationDecision("explicit", "message contained vulgar or explicit language")
        if any(marker in lowered for marker in FALLBACK_ABUSIVE_MARKERS):
            return ModerationDecision("abusive", "message looked insulting or hostile")
        if self._looks_non_english(text):
            return ModerationDecision("non_english", "message was not mainly English")
        if self._looks_gibberish(text):
            return ModerationDecision("gibberish", "message was not clear English")
        return ModerationDecision("allow", "safe message")

    def _looks_non_english(self, text: str) -> bool:
        non_ascii_chars = [char for char in text if ord(char) > 127 and char.isprintable()]
        ascii_letters = sum(char.isascii() and char.isalpha() for char in text)
        if len(non_ascii_chars) >= 4 and ascii_letters <= len(non_ascii_chars):
            return True
        return False

    def _looks_gibberish(self, text: str) -> bool:
        cleaned = re.sub(r"[^a-z\s]", " ", text.lower())
        words = [word for word in cleaned.split() if word]
        if not words:
            return False
        if len(words) == 1 and words[0] in SAFE_SHORT_ENGLISH:
            return False
        letters = "".join(words)
        if len(letters) < 8:
            return False
        if any(len(word) >= 6 and len(set(word)) <= 2 for word in words):
            return True
        if set(words).intersection(COMMON_ENGLISH_HINTS):
            return False
        vowel_ratio = sum(char in "aeiou" for char in letters) / max(1, len(letters))
        return vowel_ratio < 0.22

    def _parse_plan_entries(self, raw: str | None, days: int) -> list[dict[str, object]] | None:
        if not raw:
            return None
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, list):
            return None
        entries: list[dict[str, object]] = []
        for index, row in enumerate(payload[:days], start=1):
            if not isinstance(row, dict):
                return None
            title = str(row.get("day_title") or row.get("title") or f"Day {index}").strip()
            tasks_value = row.get("tasks") or []
            if isinstance(tasks_value, str):
                tasks_value = [tasks_value]
            if not isinstance(tasks_value, list):
                return None
            tasks = [re.sub(r"\s+", " ", str(task)).strip()[:120] for task in tasks_value if str(task).strip()]
            tasks = tasks[:3]
            if not tasks:
                return None
            entries.append({"day_title": title[:60] or f"Day {index}", "tasks": tasks})
        if len(entries) != days:
            return None
        return entries

    def _fallback_plan_entries(self, exam: str, days: int) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for day in range(1, days + 1):
            if day == 1:
                tasks = [f"List the main topics for {exam}", "Pick the highest-priority chapter", "Start short revision notes"]
                title = "Start Strong"
            elif day < days * 0.6:
                tasks = ["Study one core topic", "Write quick notes", "Do a few recall questions"]
                title = "Core Learning"
            elif day < days:
                tasks = ["Practice mixed questions", "Review weak points", "Tighten summary notes"]
                title = "Practice Phase"
            else:
                tasks = ["Revise the hardest topics", "Run one quick self-test", "Prepare final checklist"]
                title = "Final Revision"
            entries.append({"day_title": title, "tasks": tasks[:3]})
        return entries

    def _format_plan_entries(self, exam: str, entries: list[dict[str, object]]) -> str:
        lines = [f"Study plan for {exam}:"]
        for index, row in enumerate(entries, start=1):
            title = str(row.get("day_title") or f"Day {index}")
            tasks = row.get("tasks") or []
            if isinstance(tasks, list):
                compact_tasks = "; ".join(str(task) for task in tasks if str(task).strip())
            else:
                compact_tasks = str(tasks)
            lines.append(f"{index}. {title}: {compact_tasks}")
        return "\n".join(lines)

    def _keywords(self, text: str) -> list[str]:
        words = re.findall(r"[A-Za-z]{4,}", text.lower())
        common = {
            "this",
            "that",
            "with",
            "from",
            "have",
            "will",
            "into",
            "your",
            "about",
            "there",
            "their",
            "which",
            "what",
        }
        counts = Counter(word for word in words if word not in common)
        return [word for word, _ in counts.most_common(10)]
