from __future__ import annotations

from collections import defaultdict

from discord.ext import commands

from bot.command_catalog import COMMAND_DOCS, COMMAND_LOOKUP
from bot.ui import INFO, SUCCESS, WARNING, reply_embed


class Meta(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context) -> None:
        grouped: dict[str, list[str]] = defaultdict(list)
        for doc in COMMAND_DOCS:
            grouped[doc.category].append(f"`{doc.usage}`")
        fields = [(category, "\n".join(commands_list), False) for category, commands_list in sorted(grouped.items())]
        await reply_embed(
            ctx,
            title="Study OS Command Center",
            description="Every command below uses reply-based embeds and is organized by function.",
            color=INFO,
            fields=fields,
        )

    @commands.command(name="command", aliases=["commands", "cmds"])
    async def command_detail(self, ctx: commands.Context, *, name: str) -> None:
        key = name.strip().lower()
        doc = COMMAND_LOOKUP.get(key)
        if doc is None:
            await reply_embed(
                ctx,
                title="Command Not Found",
                description=f"No command metadata found for `{name}`. Use `-help` to view all commands.",
                color=WARNING,
            )
            return
        await reply_embed(
            ctx,
            title=f"{doc.name.title()} Command",
            description=doc.description,
            color=INFO,
            fields=[
                ("Usage", f"`{doc.usage}`", False),
                ("Example", f"`{doc.example}`", False),
                ("Category", doc.category, False),
            ],
        )

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context) -> None:
        await reply_embed(
            ctx,
            title="Bot Latency",
            description=f"Current latency: `{round(self.bot.latency * 1000)} ms`",
            color=SUCCESS,
        )

    @commands.command(name="about")
    async def about(self, ctx: commands.Context) -> None:
        await reply_embed(
            ctx,
            title="About Study OS",
            description="A study-focused productivity and learning assistant designed for Discord communities.",
            color=INFO,
            fields=[
                ("Prefix", f"`{self.bot.settings.prefix}`", True),
                ("Storage", f"`MongoDB: {self.bot.settings.mongodb_database}`", True),
                ("AI Mode", "Enabled" if self.bot.ai.enabled else "Fallback mode", True),
            ],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Meta(bot))
