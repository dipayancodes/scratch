from __future__ import annotations

import discord
from discord.ext import commands

from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


SHOP_ITEMS = {
    "theme_pack": 50,
    "focus_badge": 100,
    "vip_study_role": 250,
}


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.group(name="room", invoke_without_command=True)
    async def room(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Group Study Commands", description="Use `-room create/join/leave`.", color=INFO)

    @room.command(name="create")
    async def room_create(self, ctx: commands.Context, *, name: str) -> None:
        channel = await ctx.guild.create_voice_channel(f"Study | {name}")
        room_id = self.bot.db.create_room(ctx.guild.id, name, channel.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Study Room Created",
            description=f"Your study room is ready: {channel.mention}",
            color=SUCCESS,
            fields=[("Room ID", str(room_id), True), ("Name", name, True)],
        )

    @room.command(name="join")
    async def room_join(self, ctx: commands.Context, *, name: str) -> None:
        room = self.bot.db.get_room_by_name(ctx.guild.id, name)
        if not room:
            await reply_embed(ctx, title="Room Not Found", description=f"No active study room exists for `{name}`.", color=ERROR)
            return
        channel = ctx.guild.get_channel(room["channel_id"])
        if not isinstance(channel, discord.VoiceChannel):
            await reply_embed(ctx, title="Room Missing", description="The room channel no longer exists.", color=ERROR)
            return
        if ctx.author.voice:
            await ctx.author.move_to(channel)
            await reply_embed(ctx, title="Joined Study Room", description=f"You were moved to **{channel.name}**.", color=SUCCESS)
            return
        await reply_embed(ctx, title="Study Room Located", description=f"Join **{channel.name}** from the voice channel list.", color=INFO)

    @room.command(name="leave")
    async def room_leave(self, ctx: commands.Context) -> None:
        if not ctx.author.voice or not ctx.author.voice.channel:
            await reply_embed(ctx, title="Not in Voice", description="You are not currently in a voice channel.", color=WARNING)
            return
        await ctx.author.move_to(None)
        await reply_embed(ctx, title="Left Study Room", description="You disconnected from the current voice room.", color=SUCCESS)

    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx: commands.Context) -> None:
        rows = self.bot.db.coin_leaderboard(ctx.guild.id)
        if not rows:
            await reply_embed(ctx, title="Leaderboard Empty", description="No coin data exists yet.", color=INFO)
            return
        lines = []
        for index, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else str(row["user_id"])
            lines.append(f"{index}. {name} | `{row['coins']}` coins | `{row['total_focus_minutes']}` focus min")
        await reply_embed(ctx, title="Study Coin Leaderboard", description="\n".join(lines), color=INFO)

    @commands.command(name="balance")
    async def balance(self, ctx: commands.Context) -> None:
        stats = self.bot.db.get_user_stats(ctx.guild.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Study Coin Balance",
            description="Your current reward balance.",
            color=INFO,
            fields=[("Coins", f"`{stats['coins']}`", True)],
        )

    @commands.command(name="reward")
    @commands.has_permissions(manage_guild=True)
    async def reward(self, ctx: commands.Context, member: discord.Member, coins: int) -> None:
        coins = max(1, min(coins, 1000))
        self.bot.db.add_coins(ctx.guild.id, member.id, coins)
        await reply_embed(ctx, title="Reward Sent", description=f"{member.mention} received `{coins}` study coins.", color=SUCCESS)

    @commands.command(name="shop")
    async def shop(self, ctx: commands.Context, item: str = "") -> None:
        if not item:
            value = "\n".join(f"- `{name}`: `{price}` coins" for name, price in SHOP_ITEMS.items())
            await reply_embed(ctx, title="Reward Shop", description=value, color=INFO)
            return
        price = SHOP_ITEMS.get(item)
        if price is None:
            await reply_embed(ctx, title="Item Not Found", description=f"`{item}` is not available in the shop.", color=ERROR)
            return
        if not self.bot.db.spend_coins(ctx.guild.id, ctx.author.id, price):
            await reply_embed(ctx, title="Not Enough Coins", description=f"You need `{price}` coins to buy `{item}`.", color=WARNING)
            return
        await reply_embed(ctx, title="Purchase Complete", description=f"You bought `{item}` for `{price}` coins.", color=SUCCESS)

    @commands.command(name="analytics")
    async def analytics(self, ctx: commands.Context) -> None:
        summary = self.bot.db.analytics_summary(ctx.guild.id, ctx.author.id)
        subjects_text = ", ".join(f"{row['subject']} ({row['hours']}h)" for row in summary["top_subjects"]) or "No weekly subject data"
        exams_text = ", ".join(f"{row['subject']} on {row['exam_date']}" for row in summary["upcoming_exams"]) or "No exams saved"
        await reply_embed(
            ctx,
            title="Personal Study Analytics",
            description="A quick snapshot of your productivity trends.",
            color=INFO,
            fields=[
                ("Total Hours", f"`{summary['total_logged_hours']}`", True),
                ("Today vs Goal", f"`{summary['today_hours']}` / `{summary['daily_goal_hours']}`", True),
                ("Streak", f"`{summary['streak']}` days", True),
                ("Focus Minutes", f"`{summary['focus_minutes']}`", True),
                ("Voice Minutes", f"`{summary['voice_minutes']}`", True),
                ("Pending Tasks", f"`{summary['pending_tasks']}`", True),
                ("Top Subjects", subjects_text, False),
                ("Upcoming Exams", exams_text, False),
            ],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Community(bot))
