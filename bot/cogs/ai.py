from __future__ import annotations

import discord
from discord.ext import commands

from bot.ui import ERROR, INFO, reply_embed


class AITools(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="ask", description="Ask the AI study assistant a question.")
    async def ask(self, ctx: commands.Context, *, question: str) -> None:
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        answer = await self.bot.ai.ask(question)
        await reply_embed(ctx, title="AI Study Assistant", description=answer[:3500], color=INFO)

    @commands.hybrid_command(name="summary", aliases=["summery"], description="Summarize a block of study text.")
    async def summary(self, ctx: commands.Context, *, text: str) -> None:
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        result = await self.bot.ai.summarize(text)
        await reply_embed(ctx, title="Summary", description=result[:3500], color=INFO)

    @commands.hybrid_command(name="analyze", description="Analyze an attached study file and extract key points.")
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
        await reply_embed(ctx, title="Study Material Analysis", description=result[:3500], color=INFO, fields=[("File", attachment.filename, True)])

    @commands.hybrid_command(name="suggest", description="Get a suggestion for what to study next.")
    async def suggest(self, ctx: commands.Context) -> None:
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        weak = self.bot.db.get_weak_subjects(ctx.guild.id, ctx.author.id, limit=3)
        exams = self.bot.db.list_exams(ctx.guild.id, ctx.author.id)[:3]
        question = "Suggest what I should study next."
        if weak:
            question += " Weak subjects: " + ", ".join(f"{row['subject']} ({row['hours']}h)" for row in weak)
        if exams:
            question += " Upcoming exams: " + ", ".join(f"{row['subject']} on {row['exam_date']}" for row in exams)
        answer = await self.bot.ai.ask(question)
        await reply_embed(ctx, title="Study Suggestion", description=answer[:3500], color=INFO)

    @commands.hybrid_command(name="weakness", description="Detect your weakest subjects from your study history.")
    async def weakness(self, ctx: commands.Context) -> None:
        weak = self.bot.db.get_weak_subjects(ctx.guild.id, ctx.author.id, limit=5)
        if not weak:
            await reply_embed(ctx, title="No Weakness Data Yet", description="Log some study hours first so I can detect weaker subjects.", color=INFO)
            return
        lines = [f"- {row['subject']}: `{row['hours']}h` logged" for row in weak]
        await reply_embed(ctx, title="Weak Subject Detection", description="\n".join(lines), color=INFO)

    @commands.hybrid_command(name="revise", description="Suggest revision topics based on your history.")
    async def revise(self, ctx: commands.Context) -> None:
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        topics = self.bot.db.get_revision_topics(ctx.guild.id, ctx.author.id, limit=5)
        if not topics:
            await reply_embed(ctx, title="No Revision Data Yet", description="Log some subject progress first and I will suggest revision topics.", color=INFO)
            return
        prompt = "Suggest revision priorities for these subjects: " + ", ".join(f"{row['subject']} ({row['hours']}h total)" for row in topics)
        answer = await self.bot.ai.ask(prompt)
        await reply_embed(ctx, title="Revision Suggestions", description=answer[:3500], color=INFO)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AITools(bot))
