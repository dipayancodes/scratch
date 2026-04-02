from __future__ import annotations

from collections import Counter
import re


class StudyAI:
    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def ask(self, question: str) -> str:
        if self.enabled:
            result, error = await self._call_openai(
                "You are a concise study assistant. Explain clearly for students.\n"
                f"Question: {question}"
            )
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()
        return (
            "AI API is not configured, so here is a study-first fallback:\n"
            f"1. Restate the topic: {question}\n"
            "2. Break it into definition, formula/rule, example, and common mistake.\n"
            "3. Turn the answer into 3 flashcards after you understand it."
        )

    async def summarize(self, text: str) -> str:
        if self.enabled:
            result, error = await self._call_openai(
                "Summarize the following for a student in short bullet points.\n"
                f"Text:\n{text}"
            )
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()

        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
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
        if self.enabled:
            result, error = await self._call_openai(
                "Extract key points, likely exam topics, and revision tips from this study material.\n"
                f"Content:\n{text}"
            )
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()
        keywords = self._keywords(text)
        lines = text.strip().splitlines()
        useful_lines = [line.strip() for line in lines if line.strip()][:5]
        result = ["Key points:"]
        for line in useful_lines:
            result.append(f"- {line[:160]}")
        if keywords:
            result.append(f"High-signal terms: {', '.join(keywords[:8])}")
        result.append("Revision tip: turn each key point into a question-answer flashcard.")
        return "\n".join(result)

    async def generate_plan(self, exam: str, days: int) -> str:
        if self.enabled:
            result, error = await self._call_openai(
                "Create a day-by-day study plan for a student preparing for an exam.\n"
                f"Exam: {exam}\nDays available: {days}"
            )
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()

        days = max(1, min(days, 30))
        lines = [f"Study plan for {exam} ({days} days):"]
        for day in range(1, days + 1):
            if day < days * 0.6:
                phase = "learn core concepts and make notes"
            elif day < days:
                phase = "practice questions and active recall"
            else:
                phase = "final revision, weak-topic review, and mock test"
            lines.append(f"- Day {day}: {phase}")
        return "\n".join(lines)

    async def _call_openai(self, prompt: str) -> tuple[str | None, str | None]:
        if not self.api_key:
            return None, None
        try:
            from openai import AsyncOpenAI, AuthenticationError

            client = AsyncOpenAI(api_key=self.api_key)
            response = await client.responses.create(
                model=self.model,
                input=prompt,
            )
            return response.output_text.strip(), None
        except AuthenticationError:
            return None, "auth"
        except Exception as exc:
            if getattr(exc, "status_code", None) == 401:
                return None, "auth"
            return None, "other"

    def _auth_error_message(self) -> str:
        return (
            "OpenAI authentication failed. Your `OPENAI_API_KEY` in `.env` is missing, invalid, expired, or from the wrong project.\n"
            "Update the key, save `.env`, and restart the bot."
        )

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
