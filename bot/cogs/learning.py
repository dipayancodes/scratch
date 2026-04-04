from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.subjects import finalize_subject, is_custom_subject, subject_autocomplete
from bot.ui import ERROR, INFO, SUCCESS, reply_embed


class Learning(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _resolve_subject(self, ctx: commands.Context, subject: str, custom_subject: str = "") -> str:
        resolved = finalize_subject(subject, custom_subject).strip()
        if subject.lower() == "others" and not custom_subject.strip():
            raise ValueError("Custom subject is required when you choose others.")
        if is_custom_subject(resolved):
            self.bot.db.add_custom_subject(ctx.guild.id, ctx.author.id, resolved)
        return resolved

    # Flashcards and quiz commands are intentionally disabled for now.

    @commands.hybrid_group(
        name="resources",
        aliases=["resource"],
        description="Share and browse study resources.",
        invoke_without_command=True,
    )
    async def resources(self, ctx: commands.Context) -> None:
        await reply_embed(
            ctx,
            title="Resources Commands",
            description="Use `/resources add`, `/resources list`, or `/resources delete`.",
            color=INFO,
        )

    @resources.command(name="add", description="Add a study resource link for a subject.")
    @app_commands.describe(
        subject="Choose a subject or select others.",
        link="The resource URL.",
        description="A short note about the resource.",
        custom_subject="If you choose others, type your own subject here.",
    )
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def resources_add(self, ctx: commands.Context, subject: str, link: str, description: str = "Shared resource", custom_subject: str = "") -> None:
        try:
            resolved_subject = self._resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        resource_id = self.bot.db.add_resource(ctx.guild.id, ctx.author.id, resolved_subject, link, description)
        await reply_embed(
            ctx,
            title="Resource Added",
            description=f"Saved a resource for `{resolved_subject}`.",
            color=SUCCESS,
            fields=[("Resource ID", str(resource_id), True), ("Link", link[:300], False)],
        )

    @resources.command(name="list", description="List shared resources for a subject with resource IDs.")
    @app_commands.describe(
        subject="Choose the subject you want resources for.",
        custom_subject="If you choose others, type your own subject here.",
    )
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def resources_list(self, ctx: commands.Context, subject: str, custom_subject: str = "") -> None:
        try:
            resolved_subject = self._resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        resources = self.bot.db.list_resources(ctx.guild.id, resolved_subject)
        if not resources:
            await reply_embed(
                ctx,
                title="No Resources Found",
                description=f"No resources exist for `{resolved_subject}` yet.",
                color=INFO,
            )
            return
        lines = []
        for row in resources[:15]:
            owner = ctx.guild.get_member(row["user_id"])
            owner_name = owner.display_name if owner else f"User {row['user_id']}"
            lines.append(f"`{row['id']}` {row['link']} | {row['description'][:80]} | by {owner_name}")
        await reply_embed(ctx, title=f"Resources: {resolved_subject}", description="\n".join(lines), color=INFO)

    @resources.command(name="delete", description="Delete one of your resources by subject and ID.")
    @app_commands.describe(
        subject="Choose the subject the resource belongs to.",
        resource_id="The resource ID shown by `/resources list`.",
        custom_subject="If you choose others, type your own subject here.",
    )
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def resources_delete(self, ctx: commands.Context, subject: str, resource_id: int, custom_subject: str = "") -> None:
        try:
            resolved_subject = self._resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        if not self.bot.db.delete_resource(ctx.guild.id, ctx.author.id, resolved_subject, resource_id):
            await reply_embed(
                ctx,
                title="Resource Not Found",
                description=f"No matching resource exists with ID `{resource_id}` under `{resolved_subject}` for your account.",
                color=ERROR,
            )
            return
        await reply_embed(ctx, title="Resource Deleted", description=f"Removed resource `{resource_id}` from `{resolved_subject}`.", color=SUCCESS)

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
