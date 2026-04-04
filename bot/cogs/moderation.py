from __future__ import annotations

from datetime import timedelta
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


STAFF_ROLE_IDS = {1453305075740053645, 1453304133506564278}


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _ensure_staff_access(self, ctx: commands.Context) -> bool:
        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if member is None:
            await reply_embed(ctx, title="Member Not Found", description="Could not verify your server roles.", color=ERROR)
            return False
        if any(role.id in STAFF_ROLE_IDS for role in member.roles):
            return True
        await reply_embed(
            ctx,
            title="Permission Error",
            description="Only members with the Staff or Administrator server roles can use that moderation command.",
            color=WARNING,
        )
        return False

    @commands.hybrid_command(name="focus", description="Turn focus mode on or off.")
    @app_commands.describe(state="Choose whether focus mode should be on or off.")
    async def focus(self, ctx: commands.Context, state: Literal["on", "off"]) -> None:
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

    @commands.hybrid_command(name="warn", description="Warn a user for breaking study-server rules.")
    @app_commands.describe(member="The user you want to warn.", reason="Why you are warning the user.")
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        if not await self._ensure_staff_access(ctx):
            return
        warning_id = self.bot.db.add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        await reply_embed(
            ctx,
            title="User Warned",
            description=f"{member.mention} has been warned.",
            color=WARNING,
            fields=[("Warning ID", str(warning_id), True), ("Reason", reason[:300], False)],
        )

    @commands.hybrid_command(name="mute", description="Temporarily mute a user.")
    @app_commands.describe(member="The user you want to mute.", minutes="How long the mute should last.", reason="Why you are muting the user.")
    async def mute(self, ctx: commands.Context, member: discord.Member, minutes: int = 10, *, reason: str = "Focus reset") -> None:
        if not await self._ensure_staff_access(ctx):
            return
        until = discord.utils.utcnow() + timedelta(minutes=max(1, minutes))
        await member.timeout(until, reason=reason)
        await reply_embed(
            ctx,
            title="User Muted",
            description=f"{member.mention} has been timed out.",
            color=WARNING,
            fields=[("Duration", f"`{minutes}` minutes", True), ("Reason", reason[:300], False)],
        )

    @commands.hybrid_command(name="unmute", description="Remove a user's mute.")
    @app_commands.describe(member="The user you want to unmute.")
    async def unmute(self, ctx: commands.Context, member: discord.Member) -> None:
        if not await self._ensure_staff_access(ctx):
            return
        await member.timeout(None)
        await reply_embed(ctx, title="User Unmuted", description=f"{member.mention} can speak again.", color=SUCCESS)

    @commands.hybrid_command(name="kick", description="Kick a user from the server.")
    @app_commands.describe(member="The user you want to kick.", reason="Why you are kicking the user.")
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        if not await self._ensure_staff_access(ctx):
            return
        await member.kick(reason=reason)
        await reply_embed(ctx, title="User Kicked", description=f"{member.mention} was removed from the server.", color=WARNING, fields=[("Reason", reason[:300], False)])

    @commands.hybrid_command(name="ban", description="Ban a user from the server.")
    @app_commands.describe(member="The user you want to ban.", reason="Why you are banning the user.")
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        if not await self._ensure_staff_access(ctx):
            return
        await member.ban(reason=reason)
        await reply_embed(ctx, title="User Banned", description=f"{member.mention} was banned from the server.", color=ERROR, fields=[("Reason", reason[:300], False)])

    @commands.hybrid_command(name="clear", description="Delete a number of recent messages.")
    @app_commands.describe(messages="How many recent messages to delete.")
    async def clear(self, ctx: commands.Context, messages: int) -> None:
        if not await self._ensure_staff_access(ctx):
            return
        limit = max(1, min(messages, 100))
        command_message_id = ctx.message.id if ctx.message is not None else 0
        deleted = await ctx.channel.purge(
            limit=limit + 1,
            check=lambda message: command_message_id == 0 or message.id != command_message_id,
        )
        await reply_embed(
            ctx,
            title="Messages Cleared",
            description="Recent messages were removed from the channel.",
            color=SUCCESS,
            fields=[("Deleted", f"`{len(deleted)}`", True)],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
