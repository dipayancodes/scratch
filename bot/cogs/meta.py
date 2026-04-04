from __future__ import annotations

from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

from bot.command_catalog import COMMAND_DOCS, COMMAND_LOOKUP
from bot.ui import INFO, SUCCESS, WARNING, make_embed, reply_embed


class Meta(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show a categorized list of all available commands.")
    async def help_command(self, ctx: commands.Context) -> None:
        grouped: dict[str, list[str]] = defaultdict(list)
        for doc in COMMAND_DOCS:
            grouped[doc.category].append(f"`{doc.usage}`")
        fields = [(category, "\n".join(commands_list), False) for category, commands_list in sorted(grouped.items())]
        embed = make_embed(
            user=ctx.author,
            title="Study OS Command Center",
            description="Every command below is organized by function.",
            color=INFO,
            fields=fields,
        )
        try:
            await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await reply_embed(
                ctx,
                title="DM Delivery Failed",
                description="I could not DM you the help menu. Turn on DMs for this server and try again.",
                color=WARNING,
            )
            return
        await reply_embed(
            ctx,
            title="Check Your DMs",
            description="I sent the full command guide to your DM so the chat stays clean.",
            color=SUCCESS,
        )

    @commands.hybrid_command(name="command", aliases=["commands", "cmds"], description="Show detailed information about a specific command.")
    @app_commands.describe(name="The command name you want details for.")
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

    @commands.hybrid_command(name="ping", description="Check the bot latency.")
    async def ping(self, ctx: commands.Context) -> None:
        await reply_embed(
            ctx,
            title="Bot Latency",
            description=f"Current latency: `{round(self.bot.latency * 1000)} ms`",
            color=SUCCESS,
        )

    @commands.hybrid_command(name="about", description="Show bot information and system status.")
    async def about(self, ctx: commands.Context) -> None:
        await reply_embed(
            ctx,
            title="About Study OS",
            description="A study-focused productivity and learning assistant designed for Discord communities.",
            color=INFO,
            fields=[
                ("Prefix", f"`{self.bot.settings.prefix}`", True),
                ("Command Style", "`Hybrid slash + prefix commands`", True),
                ("Experience", "`Embeds, replies, reminders, study tracking`", True),
            ],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Meta(bot))
