from __future__ import annotations

from collections import Counter
import re


SYSTEM_PROMPT = (
    "You are a concise study assistant for students. "
    "Explain clearly, stay practical, and structure answers so they help revision and retention."
)


class StudyAI:
    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.client = None
        if api_key:
            try:
                from groq import AsyncGroq

                self.client = AsyncGroq(api_key=api_key)
            except Exception:
                self.client = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.client is not None)

    async def ask(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "Ask a clear study question and I will help you break it down."
        if self.enabled:
            result, error = await self._call_groq(question)
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()
        return (
            "AI is not available right now, so here is a study-first fallback:\n"
            f"1. Restate the topic: {question}\n"
            "2. Break it into definition, rule or formula, example, and common mistake.\n"
            "3. Turn the answer into 3 flashcards after you understand it."
        )

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
        exam = (exam or "").strip()
        if not exam:
            return "Give me the exam name and the number of days available."
        days = max(1, min(int(days), 30))
        if self.enabled:
            prompt = f"Create a day-by-day study plan for a student preparing for an exam.\nExam: {exam}\nDays available: {days}"
            result, error = await self._call_groq(prompt)
            if result:
                return result
            if error == "auth":
                return self._auth_error_message()

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

    async def _call_groq(self, prompt: str) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, None
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=1400,
                top_p=0.9,
            )
            content = response.choices[0].message.content if response.choices else ""
            clean = (content or "").strip()
            return (clean or "I could not generate a complete response for that request."), None
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            class_name = exc.__class__.__name__.lower()
            if status_code == 401 or "auth" in class_name:
                return None, "auth"
            return None, "other"

    def _auth_error_message(self) -> str:
        return (
            "Groq authentication failed. Your `GROQ_API_KEY` in `.env` is missing, invalid, or expired.\n"
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
