from __future__ import annotations

from datetime import timedelta

import discord
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="focus")
    async def focus(self, ctx: commands.Context, state: str) -> None:
        state = state.lower()
        if state not in {"on", "off"}:
            await reply_embed(ctx, title="Invalid Focus Option", description="Use `-focus on` or `-focus off`.", color=ERROR)
            return
        enabled = state == "on"
        self.bot.db.set_focus_mode(ctx.guild.id, ctx.author.id, enabled)
        await reply_embed(
            ctx,
            title="Focus Mode Updated",
            description="Focus mode enabled. Off-topic chat will trigger warnings." if enabled else "Focus mode disabled. Normal chatting is allowed again.",
            color=SUCCESS if enabled else INFO,
        )

    @commands.command(name="warn")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        warning_id = self.bot.db.add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        await reply_embed(
            ctx,
            title="User Warned",
            description=f"{member.mention} has been warned.",
            color=WARNING,
            fields=[("Warning ID", str(warning_id), True), ("Reason", reason[:300], False)],
        )

    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, minutes: int = 10, *, reason: str = "Focus reset") -> None:
        until = discord.utils.utcnow() + timedelta(minutes=max(1, minutes))
        await member.timeout(until, reason=reason)
        await reply_embed(
            ctx,
            title="User Muted",
            description=f"{member.mention} has been timed out.",
            color=WARNING,
            fields=[("Duration", f"`{minutes}` minutes", True), ("Reason", reason[:300], False)],
        )

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member) -> None:
        await member.timeout(None)
        await reply_embed(ctx, title="User Unmuted", description=f"{member.mention} can speak again.", color=SUCCESS)

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        await member.kick(reason=reason)
        await reply_embed(ctx, title="User Kicked", description=f"{member.mention} was removed from the server.", color=WARNING, fields=[("Reason", reason[:300], False)])

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        await member.ban(reason=reason)
        await reply_embed(ctx, title="User Banned", description=f"{member.mention} was banned from the server.", color=ERROR, fields=[("Reason", reason[:300], False)])

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, messages: int) -> None:
        limit = max(1, min(messages, 100))
        deleted = await ctx.channel.purge(limit=limit + 1, check=lambda message: message.id != ctx.message.id)
        await reply_embed(
            ctx,
            title="Messages Cleared",
            description="Recent messages were removed from the channel.",
            color=SUCCESS,
            fields=[("Deleted", f"`{len(deleted)}`", True)],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
