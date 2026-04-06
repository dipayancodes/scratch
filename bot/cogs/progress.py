from __future__ import annotations

from discord import app_commands
from discord.ext import commands

from bot.cog_helpers import progress_bar, resolve_subject
from bot.subjects import subject_autocomplete
from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


class Progress(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="progress", description="Log and review study progress.", invoke_without_command=True)
    async def progress(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Progress Commands", description="Use `/progress add`, `/progress stats`, `/progress weekly`, or `/progress leaderboard`.", color=INFO)

    @progress.command(name="add", description="Log study hours for a subject.")
    @app_commands.describe(subject="Choose a subject or select others.", hours="How many hours you studied.", custom_subject="If you choose others, type your own subject here.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def progress_add(self, ctx: commands.Context, subject: str, hours: float, custom_subject: str = "") -> None:
        try:
            resolved_subject = resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        hours = max(0.25, min(hours, 24.0))
        self.bot.db.add_progress(ctx.guild.id, ctx.author.id, resolved_subject, hours)
        unlocked = self.bot.db.sync_achievements(ctx.guild.id, ctx.author.id)
        stats = self.bot.db.get_user_stats(ctx.guild.id, ctx.author.id)
        fields = [
            ("Coin Reward", f"`{int(hours * 20)}`", True),
            ("XP", f"`{stats.get('xp', 0)}`", True),
            ("Level", f"`{stats.get('level', 1)}`", True),
        ]
        if unlocked:
            fields.append(("Achievement", unlocked[0]["name"], False))
        await reply_embed(ctx, title="Study Hours Logged", description=f"Recorded `{hours}` hours for `{resolved_subject}`.", color=SUCCESS, fields=fields)

    @progress.command(name="stats", description="Show your total logged study hours.")
    async def progress_stats(self, ctx: commands.Context) -> None:
        totals = self.bot.db.get_progress_totals(ctx.guild.id, ctx.author.id)
        streak = self.bot.db.refresh_streak(ctx.guild.id, ctx.author.id)
        stats = self.bot.db.get_user_stats(ctx.guild.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Progress Stats",
            description="Your overall study summary.",
            color=INFO,
            fields=[
                ("Total Hours", f"`{totals['logged_hours']}`", True),
                ("Entries", f"`{totals['entries']}`", True),
                ("Current Streak", f"`{streak['streak']}` days", True),
                ("Coins", f"`{stats.get('coins', 0)}`", True),
                ("XP", f"`{stats.get('xp', 0)}`", True),
                ("Level", f"`{stats.get('level', 1)}`", True),
            ],
        )

    @progress.command(name="weekly", description="Show your weekly study breakdown.")
    async def progress_weekly(self, ctx: commands.Context) -> None:
        rows = self.bot.db.get_weekly_progress(ctx.guild.id, ctx.author.id)
        if not rows:
            await reply_embed(ctx, title="No Weekly Progress", description="Log some study hours first with `/progress add`.", color=WARNING)
            return
        value = "\n".join(f"- {row['subject']}: `{row['hours']}h`" for row in rows[:10])
        await reply_embed(ctx, title="Weekly Progress", description=value, color=INFO)

    @progress.command(name="leaderboard", description="Show the server leaderboard by study hours.")
    async def progress_leaderboard(self, ctx: commands.Context) -> None:
        rows = self.bot.db.progress_leaderboard(ctx.guild.id)
        if not rows:
            await reply_embed(ctx, title="Leaderboard Empty", description="No study progress has been logged yet.", color=WARNING)
            return
        value = []
        for index, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row["user_id"])
            value.append(f"{index}. {(member.display_name if member else row['user_id'])} - `{row['total_hours']}h`")
        await reply_embed(ctx, title="Study Hours Leaderboard", description="\n".join(value), color=INFO)

    @commands.hybrid_command(name="streak", description="Check, reset, or protect your study streak.")
    @app_commands.describe(action="Leave empty to view, or choose reset/protect.")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="reset", value="reset"),
            app_commands.Choice(name="protect", value="protect"),
        ]
    )
    async def streak(self, ctx: commands.Context, action: str = "") -> None:
        if action.lower() == "reset":
            self.bot.db.reset_streak(ctx.guild.id, ctx.author.id)
            await reply_embed(ctx, title="Streak Reset", description="Your study streak has been reset.", color=WARNING)
            return
        if action.lower() == "protect":
            result = self.bot.db.activate_streak_protection(ctx.guild.id, ctx.author.id)
            if not result["ok"]:
                await reply_embed(ctx, title="No Streak Protection", description="You do not have any streak protection charges left.", color=WARNING)
                return
            await reply_embed(
                ctx,
                title="Streak Protected",
                description="Your streak is protected for the next missed day.",
                color=SUCCESS,
                fields=[
                    ("Protected Until", result["protected_until"], True),
                    ("Remaining Charges", f"`{result['remaining']}`", True),
                ],
            )
            return
        stats = self.bot.db.refresh_streak(ctx.guild.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Study Streak",
            description="Consistency stats for your study habit.",
            color=INFO,
            fields=[
                ("Current", f"`{stats['streak']}` days", True),
                ("Longest", f"`{stats['longest_streak']}` days", True),
                ("Protections", f"`{stats.get('streak_protects', 0)}`", True),
            ],
        )

    @commands.hybrid_command(name="checkin", description="Complete your daily check-in for coins and XP.")
    async def checkin(self, ctx: commands.Context) -> None:
        result = self.bot.db.daily_checkin(ctx.guild.id, ctx.author.id)
        if not result["ok"]:
            await reply_embed(ctx, title="Already Checked In", description="You already completed today's check-in.", color=WARNING)
            return
        unlocked = self.bot.db.sync_achievements(ctx.guild.id, ctx.author.id)
        fields = [
            ("Coins", f"`+{result['reward']}`", True),
            ("Streak", f"`{result['stats']['streak']}` days", True),
            ("Level", f"`{result['xp']['level']}`", True),
        ]
        if unlocked:
            fields.append(("Achievement", unlocked[0]["name"], False))
        await reply_embed(ctx, title="Daily Check-In Complete", description="You checked in and kept your momentum going.", color=SUCCESS, fields=fields)

    @commands.hybrid_group(name="goal", description="Set and review your daily study goal.", invoke_without_command=True)
    async def goal(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Goal Commands", description="Use `/goal set` or `/goal status`.", color=INFO)

    @goal.command(name="set", description="Set your daily study goal in hours.")
    @app_commands.describe(hours="How many hours you want to study each day.")
    async def goal_set(self, ctx: commands.Context, hours: float) -> None:
        hours = max(0.5, min(hours, 16.0))
        self.bot.db.set_goal(ctx.guild.id, ctx.author.id, hours)
        await reply_embed(ctx, title="Goal Updated", description=f"Your daily study goal is now `{hours}` hours.", color=SUCCESS)

    @goal.command(name="status", description="Check how close you are to your daily study goal.")
    async def goal_status(self, ctx: commands.Context) -> None:
        summary = self.bot.db.analytics_summary(ctx.guild.id, ctx.author.id)
        bar = progress_bar(summary["today_hours"], summary["daily_goal_hours"])
        await reply_embed(
            ctx,
            title="Goal Status",
            description="Here is your current goal progress.",
            color=INFO,
            fields=[
                ("Today's Hours", f"`{summary['today_hours']}`", True),
                ("Daily Goal", f"`{summary['daily_goal_hours']}`", True),
                ("Progress", f"`{bar}`", False),
            ],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Progress(bot))
