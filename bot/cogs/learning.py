from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


QUIZ_BANK = {
    "math": [
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
}


class Learning(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="flash", description="Create and review flashcards.", invoke_without_command=True)
    async def flash(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Flashcard Commands", description="Use `-flash add/quiz/list/delete`.", color=INFO)

    @flash.command(name="add", description="Add a new flashcard.")
    @app_commands.describe(payload="Write it as: question | answer")
    async def flash_add(self, ctx: commands.Context, *, payload: str) -> None:
        if "|" not in payload:
            await reply_embed(ctx, title="Invalid Flashcard Format", description="Use `-flash add <question> | <answer>`.", color=ERROR)
            return
        question, answer = [part.strip() for part in payload.split("|", 1)]
        flashcard_id = self.bot.db.add_flashcard(ctx.guild.id, ctx.author.id, question, answer)
        await reply_embed(
            ctx,
            title="Flashcard Added",
            description="Your flashcard is ready for review.",
            color=SUCCESS,
            fields=[("ID", str(flashcard_id), True), ("Question", question[:200], False)],
        )

    @flash.command(name="quiz", description="Start a quiz using one of your flashcards.")
    async def flash_quiz(self, ctx: commands.Context) -> None:
        cards = self.bot.db.get_flashcards(ctx.guild.id, ctx.author.id)
        if not cards:
            await reply_embed(ctx, title="No Flashcards Found", description="Create one first with `-flash add`.", color=WARNING)
            return
        card = random.choice(cards)
        self.bot.quiz_sessions[(ctx.guild.id, ctx.author.id)] = {
            "type": "flash",
            "question": card["question"],
            "answer": card["answer"],
            "score": 0,
        }
        await reply_embed(
            ctx,
            title="Flashcard Quiz",
            description=card["question"],
            color=INFO,
            fields=[("How to Answer", "Reply with `-quiz answer <your answer>`.", False)],
        )

    @flash.command(name="list", description="List your saved flashcards.")
    async def flash_list(self, ctx: commands.Context) -> None:
        cards = self.bot.db.list_flashcards(ctx.guild.id, ctx.author.id)
        if not cards:
            await reply_embed(ctx, title="No Flashcards Saved", description="Add one with `-flash add`.", color=INFO)
            return
        value = "\n".join(f"`{card['id']}` {card['question'][:90]}" for card in cards[:15])
        await reply_embed(ctx, title="Your Flashcards", description=value, color=INFO)

    @flash.command(name="delete", description="Delete one of your flashcards.")
    @app_commands.describe(flashcard_id="The flashcard ID you want to delete.")
    async def flash_delete(self, ctx: commands.Context, flashcard_id: int) -> None:
        if not self.bot.db.delete_flashcard(ctx.guild.id, ctx.author.id, flashcard_id):
            await reply_embed(ctx, title="Flashcard Not Found", description=f"No flashcard exists with ID `{flashcard_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Flashcard Deleted", description=f"Removed flashcard `{flashcard_id}`.", color=SUCCESS)

    @commands.hybrid_group(name="quiz", description="Start and answer subject quizzes.", invoke_without_command=True)
    async def quiz(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Quiz Commands", description="Use `-quiz start/answer/score`.", color=INFO)

    @quiz.command(name="start", description="Start a quiz for a supported subject.")
    @app_commands.describe(subject="Pick the subject for the quiz.")
    @app_commands.choices(
        subject=[
            app_commands.Choice(name="math", value="math"),
            app_commands.Choice(name="physics", value="physics"),
            app_commands.Choice(name="biology", value="biology"),
        ]
    )
    async def quiz_start(self, ctx: commands.Context, subject: str) -> None:
        subject_key = subject.lower()
        questions = QUIZ_BANK.get(subject_key)
        if not questions:
            await reply_embed(
                ctx,
                title="Quiz Subject Not Found",
                description=f"No quiz bank exists for `{subject}`.",
                color=ERROR,
                fields=[("Available Subjects", ", ".join(sorted(QUIZ_BANK)), False)],
            )
            return
        question = random.choice(questions)
        self.bot.quiz_sessions[(ctx.guild.id, ctx.author.id)] = {
            "type": "subject",
            "subject": subject_key,
            "question": question["question"],
            "options": question["options"],
            "answer": question["answer"],
            "score": 0,
        }
        options = "\n".join(f"{label}. {text}" for label, text in zip(["A", "B", "C", "D"], question["options"]))
        await reply_embed(
            ctx,
            title=f"{subject_key.title()} Quiz",
            description=question["question"],
            color=INFO,
            fields=[("Options", options, False), ("How to Answer", "Use `-quiz answer <option>`.", False)],
        )

    @quiz.command(name="answer", description="Submit your answer for the active quiz.")
    @app_commands.describe(option="Your answer or option, such as A, B, C, or D.")
    async def quiz_answer(self, ctx: commands.Context, *, option: str) -> None:
        session = self.bot.quiz_sessions.get((ctx.guild.id, ctx.author.id))
        if not session:
            await reply_embed(ctx, title="No Active Quiz", description="Start one with `-quiz start <subject>` or `-flash quiz`.", color=WARNING)
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
            await reply_embed(
                ctx,
                title="Correct Answer",
                description="Well done. You earned study coins.",
                color=SUCCESS,
                fields=[("Reward", "`8 study coins`", True)],
            )
            return
        await reply_embed(
            ctx,
            title="Incorrect Answer",
            description=f"The correct answer was `{session['answer']}`.",
            color=WARNING,
        )

    @quiz.command(name="score", description="Show your current quiz score.")
    async def quiz_score(self, ctx: commands.Context) -> None:
        session = self.bot.quiz_sessions.get((ctx.guild.id, ctx.author.id))
        if not session:
            await reply_embed(ctx, title="No Quiz History", description="You have not started a quiz recently.", color=INFO)
            return
        await reply_embed(ctx, title="Quiz Score", description=f"Current score: `{session['score']}`", color=INFO)

    @commands.hybrid_group(name="resource", description="Share and browse study resources.", invoke_without_command=True)
    async def resource(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Resource Commands", description="Use `-resource add/list/delete`.", color=INFO)

    @resource.command(name="add", description="Add a study resource link.")
    @app_commands.describe(subject="The subject the resource belongs to.", link="The resource URL.", description="A short description of the resource.")
    async def resource_add(self, ctx: commands.Context, subject: str, link: str, *, description: str = "Shared resource") -> None:
        resource_id = self.bot.db.add_resource(ctx.guild.id, ctx.author.id, subject, link, description)
        await reply_embed(
            ctx,
            title="Resource Added",
            description=f"Saved a study resource for `{subject}`.",
            color=SUCCESS,
            fields=[("ID", str(resource_id), True), ("Link", link[:300], False)],
        )

    @resource.command(name="list", description="List all resources for a subject.")
    @app_commands.describe(subject="The subject you want resources for.")
    async def resource_list(self, ctx: commands.Context, subject: str) -> None:
        resources = self.bot.db.list_resources(ctx.guild.id, subject)
        if not resources:
            await reply_embed(ctx, title="No Resources Found", description=f"No resources exist for `{subject}`.", color=INFO)
            return
        value = "\n".join(f"`{row['id']}` {row['link']} | {row['description']}" for row in resources[:12])
        await reply_embed(ctx, title=f"Resources: {subject}", description=value, color=INFO)

    @resource.command(name="delete", description="Delete a shared study resource.")
    @app_commands.describe(resource_id="The resource ID you want to delete.")
    async def resource_delete(self, ctx: commands.Context, resource_id: int) -> None:
        if not self.bot.db.delete_resource(ctx.guild.id, resource_id):
            await reply_embed(ctx, title="Resource Not Found", description=f"No resource exists with ID `{resource_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Resource Deleted", description=f"Removed resource `{resource_id}`.", color=SUCCESS)

    @commands.hybrid_command(name="ask", description="Ask the AI study assistant a question.")
    @app_commands.describe(question="The concept or doubt you want explained.")
    async def ask(self, ctx: commands.Context, *, question: str) -> None:
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        answer = await self.bot.ai.ask(question)
        await reply_embed(ctx, title="AI Study Assistant", description=answer[:3500], color=INFO)

    @commands.hybrid_command(name="summary", aliases=["summery"], description="Summarize a block of study text.")
    @app_commands.describe(text="The text you want summarized.")
    async def summary(self, ctx: commands.Context, *, text: str) -> None:
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        result = await self.bot.ai.summarize(text)
        await reply_embed(ctx, title="Summary", description=result[:3500], color=INFO)

    @commands.hybrid_command(name="analyze", description="Analyze an attached study file and extract key points.")
    @app_commands.describe(attachment="The text file you want the bot to analyze.")
    async def analyze(self, ctx: commands.Context, attachment: discord.Attachment | None = None) -> None:
        if attachment is None and ctx.message is not None and ctx.message.attachments:
            attachment = ctx.message.attachments[0]
        if attachment is None:
            await reply_embed(ctx, title="No File Attached", description="Attach a text file and run `-analyze` again.", color=ERROR)
            return
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        raw = await attachment.read()
        text = raw.decode("utf-8", errors="ignore")[:8000]
        result = await self.bot.ai.analyze_text(text)
        await reply_embed(
            ctx,
            title="Study Material Analysis",
            description=result[:3500],
            color=INFO,
            fields=[("File", attachment.filename, True)],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Learning(bot))
