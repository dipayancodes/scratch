from __future__ import annotations

import random

from discord import app_commands
from discord.ext import commands

from bot.cog_helpers import resolve_subject
from bot.subjects import subject_autocomplete
from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


QUIZ_BANK = {
    "mathematics": [
        {"question": "What is the derivative of x^2?", "options": ["2x", "x", "x^3", "1"], "answer": "A"},
        {"question": "What is 12 x 8?", "options": ["88", "96", "108", "86"], "answer": "B"},
    ],
    "physics": [
        {"question": "SI unit of force?", "options": ["Joule", "Watt", "Newton", "Pascal"], "answer": "C"},
        {"question": "Speed of light is approximately?", "options": ["3x10^8 m/s", "300 m/s", "1500 m/s", "3x10^5 m/s"], "answer": "A"},
    ],
    "biology": [
        {"question": "Basic unit of life?", "options": ["Atom", "Cell", "Tissue", "Organ"], "answer": "B"},
        {"question": "DNA stands for?", "options": ["Deoxyribonucleic Acid", "Dynamic Neural Axis", "Dual Nitric Agent", "None"], "answer": "A"},
    ],
    "chemistry": [
        {"question": "Atomic number represents?", "options": ["Neutrons", "Protons", "Electrons only", "Mass"], "answer": "B"},
        {"question": "pH less than 7 means?", "options": ["Acidic", "Basic", "Neutral", "Salty"], "answer": "A"},
    ],
}


class Learning(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="flash", description="Create and review flashcards.", invoke_without_command=True)
    async def flash(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Flashcard Commands", description="Use `/flash add`, `/flash quiz`, `/flash list`, or `/flash delete`.", color=INFO)

    @flash.command(name="add", description="Add a new flashcard.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def flash_add(self, ctx: commands.Context, question: str, answer: str, subject: str = "others", custom_subject: str = "") -> None:
        try:
            resolved_subject = resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        flashcard_id = self.bot.db.add_flashcard(ctx.guild.id, ctx.author.id, question, answer, resolved_subject)
        self.bot.db.add_xp(ctx.guild.id, ctx.author.id, 10)
        await reply_embed(
            ctx,
            title="Flashcard Added",
            description="Your flashcard is ready for review.",
            color=SUCCESS,
            fields=[("ID", str(flashcard_id), True), ("Subject", resolved_subject, True)],
        )

    @flash.command(name="quiz", description="Start a quiz using one of your flashcards.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def flash_quiz(self, ctx: commands.Context, subject: str = "", custom_subject: str = "") -> None:
        resolved_subject = ""
        if subject:
            try:
                resolved_subject = resolve_subject(ctx, subject, custom_subject)
            except ValueError as exc:
                await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
                return
        cards = self.bot.db.get_flashcards(ctx.guild.id, ctx.author.id)
        if resolved_subject:
            cards = [card for card in cards if card.get("subject_key") == resolved_subject.lower()]
        if not cards:
            await reply_embed(ctx, title="No Flashcards Found", description="Create one first with `/flash add`.", color=WARNING)
            return
        card = random.choice(cards)
        self.bot.quiz_sessions[(ctx.guild.id, ctx.author.id)] = {
            "type": "flash",
            "question": card["question"],
            "answer": card["answer"],
            "score": 0,
        }
        await reply_embed(ctx, title="Flashcard Quiz", description=card["question"], color=INFO, fields=[("How to Answer", "Reply with `/quiz answer <your answer>`.", False)])

    @flash.command(name="list", description="List your saved flashcards.")
    async def flash_list(self, ctx: commands.Context) -> None:
        cards = self.bot.db.list_flashcards(ctx.guild.id, ctx.author.id)
        if not cards:
            await reply_embed(ctx, title="No Flashcards Saved", description="Add one with `/flash add`.", color=INFO)
            return
        value = "\n".join(f"`{card['id']}` {card['question'][:90]}" for card in cards[:15])
        await reply_embed(ctx, title="Your Flashcards", description=value, color=INFO)

    @flash.command(name="delete", description="Delete one of your flashcards.")
    async def flash_delete(self, ctx: commands.Context, flashcard_id: int) -> None:
        if not self.bot.db.delete_flashcard(ctx.guild.id, ctx.author.id, flashcard_id):
            await reply_embed(ctx, title="Flashcard Not Found", description=f"No flashcard exists with ID `{flashcard_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Flashcard Deleted", description=f"Removed flashcard `{flashcard_id}`.", color=SUCCESS)

    @commands.hybrid_group(name="quiz", description="Start and answer subject quizzes.", invoke_without_command=True)
    async def quiz(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Quiz Commands", description="Use `/quiz start`, `/quiz answer`, or `/quiz score`.", color=INFO)

    @quiz.command(name="start", description="Start a quiz for a supported subject.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def quiz_start(self, ctx: commands.Context, subject: str, custom_subject: str = "") -> None:
        try:
            resolved_subject = resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        questions = QUIZ_BANK.get(resolved_subject.lower())
        if not questions:
            await reply_embed(ctx, title="Quiz Subject Not Found", description=f"No quiz bank exists for `{resolved_subject}` yet.", color=ERROR)
            return
        question = random.choice(questions)
        self.bot.quiz_sessions[(ctx.guild.id, ctx.author.id)] = {
            "type": "subject",
            "subject": resolved_subject.lower(),
            "question": question["question"],
            "options": question["options"],
            "answer": question["answer"],
            "score": 0,
        }
        options = "\n".join(f"{label}. {text}" for label, text in zip(["A", "B", "C", "D"], question["options"]))
        await reply_embed(ctx, title=f"{resolved_subject.title()} Quiz", description=question["question"], color=INFO, fields=[("Options", options, False), ("How to Answer", "Use `/quiz answer <option>`.", False)])

    @quiz.command(name="answer", description="Submit your answer for the active quiz.")
    async def quiz_answer(self, ctx: commands.Context, *, option: str) -> None:
        session = self.bot.quiz_sessions.get((ctx.guild.id, ctx.author.id))
        if not session:
            await reply_embed(ctx, title="No Active Quiz", description="Start one with `/quiz start` or `/flash quiz`.", color=WARNING)
            return
        expected = session["answer"].strip().lower()
        actual = option.strip().lower()
        if session["type"] == "flash":
            correct = expected in actual or actual in expected
        else:
            correct = actual == expected
        session["score"] = 1 if correct else 0
        if correct:
            self.bot.db.add_coins(ctx.guild.id, ctx.author.id, 8)
            self.bot.db.add_xp(ctx.guild.id, ctx.author.id, 12)
            await reply_embed(ctx, title="Correct Answer", description="Well done. You earned study rewards.", color=SUCCESS, fields=[("Reward", "`8 study coins`", True)])
            return
        await reply_embed(ctx, title="Incorrect Answer", description=f"The correct answer was `{session['answer']}`.", color=WARNING)

    @quiz.command(name="score", description="Show your current quiz score.")
    async def quiz_score(self, ctx: commands.Context) -> None:
        session = self.bot.quiz_sessions.get((ctx.guild.id, ctx.author.id))
        if not session:
            await reply_embed(ctx, title="No Quiz History", description="You have not started a quiz recently.", color=INFO)
            return
        await reply_embed(ctx, title="Quiz Score", description=f"Current score: `{session['score']}`", color=INFO)

    @commands.hybrid_group(name="resources", aliases=["resource"], description="Share and browse study resources.", invoke_without_command=True)
    async def resources(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Resources Commands", description="Use `/resources add`, `/resources list`, or `/resources delete`.", color=INFO)

    @resources.command(name="add", description="Add a study resource link for a subject.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def resources_add(self, ctx: commands.Context, subject: str, link: str, description: str = "Shared resource", custom_subject: str = "") -> None:
        try:
            resolved_subject = resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        resource_id = self.bot.db.add_resource(ctx.guild.id, ctx.author.id, resolved_subject, link, description)
        self.bot.db.add_xp(ctx.guild.id, ctx.author.id, 6)
        await reply_embed(ctx, title="Resource Added", description=f"Saved a resource for `{resolved_subject}`.", color=SUCCESS, fields=[("Resource ID", str(resource_id), True), ("Link", link[:300], False)])

    @resources.command(name="list", description="List shared resources for a subject with resource IDs.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def resources_list(self, ctx: commands.Context, subject: str, custom_subject: str = "") -> None:
        try:
            resolved_subject = resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        resources = self.bot.db.list_resources(ctx.guild.id, resolved_subject)
        if not resources:
            await reply_embed(ctx, title="No Resources Found", description=f"No resources exist for `{resolved_subject}` yet.", color=INFO)
            return
        lines = []
        for row in resources[:15]:
            owner = ctx.guild.get_member(row["user_id"])
            owner_name = owner.display_name if owner else f"User {row['user_id']}"
            lines.append(f"`{row['id']}` {row['link']} | {row['description'][:80]} | by {owner_name}")
        await reply_embed(ctx, title=f"Resources: {resolved_subject}", description="\n".join(lines), color=INFO)

    @resources.command(name="delete", description="Delete one of your resources by subject and ID.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def resources_delete(self, ctx: commands.Context, subject: str, resource_id: int, custom_subject: str = "") -> None:
        try:
            resolved_subject = resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        if not self.bot.db.delete_resource(ctx.guild.id, ctx.author.id, resolved_subject, resource_id):
            await reply_embed(ctx, title="Resource Not Found", description=f"No matching resource exists with ID `{resource_id}` under `{resolved_subject}` for your account.", color=ERROR)
            return
        await reply_embed(ctx, title="Resource Deleted", description=f"Removed resource `{resource_id}` from `{resolved_subject}`.", color=SUCCESS)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Learning(bot))
