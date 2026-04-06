from __future__ import annotations

from datetime import UTC, datetime, timedelta

from discord import app_commands
from discord.ext import commands

from bot.bot import StudyTimer
from bot.cog_helpers import parse_daily_time, parse_duration, parse_exam_date, next_weekday_date, resolve_subject, saved_plan_autocomplete
from bot.subjects import DAYS_OF_WEEK, subject_autocomplete
from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


class Study(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="study", description="Run focus and break timers.", invoke_without_command=True)
    async def study(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Study Timer Commands", description="Use `/study start`, `/study break`, `/study stop`, or `/study status`.", color=INFO)

    @study.command(name="start", description="Start a focused study session.")
    @app_commands.describe(minutes="Optional study minutes.", hours="Optional study hours.")
    async def study_start(self, ctx: commands.Context, minutes: int = 0, hours: int = 0) -> None:
        total_minutes = max(0, minutes) + (max(0, hours) * 60)
        if total_minutes <= 0:
            await reply_embed(ctx, title="Invalid Duration", description="Provide minutes, hours, or both.", color=ERROR)
            return
        total_minutes = min(total_minutes, 720)
        key = (ctx.guild.id, ctx.author.id)
        if self.bot.active_timers.get(key):
            await reply_embed(ctx, title="Timer Already Running", description="Stop the current timer before starting a new one.", color=WARNING)
            return
        ends_at = datetime.now(UTC) + timedelta(minutes=total_minutes)
        response = await reply_embed(
            ctx,
            title="Focus Session Started",
            description=f"Your study timer is active for `{total_minutes}` minutes.",
            color=SUCCESS,
            fields=[("Ends", f"<t:{int(ends_at.timestamp())}:R>", True)],
        )
        self.bot.active_timers[key] = StudyTimer(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            source_message_id=response.id,
            minutes=total_minutes,
            session_type="focus",
            ends_at=ends_at,
        )

    @study.command(name="break", description="Start a short break timer.")
    @app_commands.describe(minutes="How many minutes the break should last.")
    async def study_break(self, ctx: commands.Context, minutes: int) -> None:
        minutes = max(1, min(minutes, 60))
        key = (ctx.guild.id, ctx.author.id)
        ends_at = datetime.now(UTC) + timedelta(minutes=minutes)
        response = await reply_embed(
            ctx,
            title="Break Timer Started",
            description=f"Your break timer is active for `{minutes}` minutes.",
            color=INFO,
            fields=[("Ends", f"<t:{int(ends_at.timestamp())}:R>", True)],
        )
        self.bot.active_timers[key] = StudyTimer(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            source_message_id=response.id,
            minutes=minutes,
            session_type="break",
            ends_at=ends_at,
        )

    @study.command(name="stop", description="Stop your current study or break timer.")
    async def study_stop(self, ctx: commands.Context) -> None:
        removed = self.bot.active_timers.pop((ctx.guild.id, ctx.author.id), None)
        if not removed:
            await reply_embed(ctx, title="No Active Timer", description="You do not have a running timer.", color=WARNING)
            return
        await reply_embed(ctx, title="Timer Stopped", description="Your current timer has been stopped.", color=SUCCESS)

    @study.command(name="status", description="Check the remaining time on your current timer.")
    async def study_status(self, ctx: commands.Context) -> None:
        timer = self.bot.active_timers.get((ctx.guild.id, ctx.author.id))
        if not timer:
            await reply_embed(ctx, title="No Active Timer", description="Start one with `/study start`.", color=WARNING)
            return
        remaining = max(0, int((timer.ends_at - datetime.now(UTC)).total_seconds() // 60))
        await reply_embed(ctx, title="Current Timer Status", description=f"Your `{timer.session_type}` timer is running.", color=INFO, fields=[("Remaining", f"`{remaining}` minutes", True)])

    @commands.hybrid_group(name="plan", description="Create and review day-based study plans.", invoke_without_command=True)
    async def plan(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Plan Commands", description="Use `/plan set`, `/plan view`, `/plan today`, or `/plan smart`.", color=INFO)

    @plan.command(name="set", description="Save your study plan for the next occurrence of a weekday.")
    @app_commands.describe(day="Choose the day you want to plan for.", tasks="The study tasks for that day.")
    @app_commands.choices(day=[app_commands.Choice(name=day.title(), value=day) for day in DAYS_OF_WEEK])
    async def plan_set(self, ctx: commands.Context, day: str, *, tasks: str) -> None:
        target_date = next_weekday_date(day)
        self.bot.db.set_plan(ctx.guild.id, ctx.author.id, day, target_date, tasks)
        self.bot.db.add_xp(ctx.guild.id, ctx.author.id, 8)
        await reply_embed(ctx, title="Plan Saved", description=f"Your `{day.title()}` plan has been saved.", color=SUCCESS, fields=[("Date", target_date, True), ("Tasks", tasks[:500], False)])

    @plan.command(name="view", description="View one of your saved plans.")
    @app_commands.describe(day="Pick one of your saved plan days.")
    @app_commands.autocomplete(day=saved_plan_autocomplete)
    async def plan_view(self, ctx: commands.Context, day: str) -> None:
        plan = self.bot.db.get_plan_by_date(ctx.guild.id, ctx.author.id, day)
        if not plan:
            await reply_embed(ctx, title="Plan Not Found", description="No saved plan exists for that date.", color=WARNING)
            return
        await reply_embed(ctx, title=f"Plan: {plan['day'].title()} {plan['target_date']}", description=plan["tasks"][:3500], color=INFO)

    @plan.command(name="today", description="Show the plan for today's exact date.")
    async def plan_today(self, ctx: commands.Context) -> None:
        target_date = datetime.now(UTC).date().isoformat()
        plan = self.bot.db.get_plan_by_date(ctx.guild.id, ctx.author.id, target_date)
        if not plan:
            await reply_embed(ctx, title="No Plan For Today", description="You have no saved plan for today's date.", color=WARNING)
            return
        await reply_embed(ctx, title=f"Today's Plan: {plan['day'].title()} {plan['target_date']}", description=plan["tasks"][:3500], color=INFO)

    @plan.command(name="smart", description="Generate a smart AI study plan for an exam.")
    async def plan_smart(self, ctx: commands.Context, exam: str, days: int) -> None:
        if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        result = await self.bot.ai.generate_plan(exam, days)
        await reply_embed(ctx, title="Smart Study Plan", description=result[:3500], color=INFO)

    @commands.hybrid_group(name="remind", description="Create and manage study reminders.", invoke_without_command=True)
    async def remind(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Reminder Commands", description="Use `/remind me`, `/remind daily`, `/remind list`, or `/remind delete`.", color=INFO)

    @remind.command(name="me", description="Create a one-time reminder.")
    async def remind_me(self, ctx: commands.Context, duration: str, *, task: str) -> None:
        try:
            delta = parse_duration(duration)
        except (ValueError, IndexError):
            await reply_embed(ctx, title="Invalid Duration", description="Use a duration like `30m`, `2h`, or `1d`.", color=ERROR)
            return
        remind_at = datetime.now(UTC) + delta
        reminder_id = self.bot.db.add_reminder(ctx.guild.id, ctx.channel.id, ctx.author.id, task, remind_at, 0)
        response = await reply_embed(ctx, title="Reminder Created", description="Your reminder has been scheduled and will arrive in your DM.", color=SUCCESS, fields=[("Reminder ID", str(reminder_id), True), ("When", f"<t:{int(remind_at.timestamp())}:R>", True)])
        self.bot.db.update_reminder_source(reminder_id, response.id)

    @remind.command(name="daily", description="Create a reminder that repeats every day.")
    async def remind_daily(self, ctx: commands.Context, time: str, *, task: str = "Daily study reminder") -> None:
        try:
            hour, minute = parse_daily_time(time)
        except ValueError:
            await reply_embed(ctx, title="Invalid Time", description="Use 24-hour time like `07:30` or `21:15`.", color=ERROR)
            return
        now = datetime.now(UTC)
        remind_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if remind_at <= now:
            remind_at += timedelta(days=1)
        reminder_id = self.bot.db.add_reminder(ctx.guild.id, ctx.channel.id, ctx.author.id, task, remind_at, 0, recurring="daily", daily_time=time)
        response = await reply_embed(ctx, title="Daily Reminder Created", description="Your daily reminder will be sent by DM.", color=SUCCESS, fields=[("Reminder ID", str(reminder_id), True), ("Next Run", f"<t:{int(remind_at.timestamp())}:R>", True)])
        self.bot.db.update_reminder_source(reminder_id, response.id)

    @remind.command(name="list", description="List your active reminders with reminder IDs.")
    async def remind_list(self, ctx: commands.Context) -> None:
        reminders = self.bot.db.list_reminders(ctx.guild.id, ctx.author.id)
        if not reminders:
            await reply_embed(ctx, title="No Reminders", description="You have no active reminders.", color=INFO)
            return
        lines = [f"`{row['id']}` {row['message']} -> <t:{int(row['remind_at'].timestamp())}:R> ({row['recurring']})" for row in reminders[:15]]
        await reply_embed(ctx, title="Your Reminders", description="\n".join(lines), color=INFO)

    @remind.command(name="delete", description="Delete one of your reminders by ID.")
    async def remind_delete(self, ctx: commands.Context, reminder_id: int) -> None:
        if not self.bot.db.delete_reminder_for_user(ctx.guild.id, ctx.author.id, reminder_id):
            await reply_embed(ctx, title="Reminder Not Found", description=f"No reminder exists with ID `{reminder_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Reminder Deleted", description=f"Removed reminder `{reminder_id}`.", color=SUCCESS)

    @commands.hybrid_group(name="exam", description="Track exams and countdowns.", invoke_without_command=True)
    async def exam(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Exam Commands", description="Use `/exam add`, `/exam list`, or `/exam countdown`.", color=INFO)

    @exam.command(name="add", description="Add an upcoming exam.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def exam_add(self, ctx: commands.Context, subject: str, date: str, custom_subject: str = "") -> None:
        try:
            resolved_subject = resolve_subject(ctx, subject, custom_subject)
            exam_date = parse_exam_date(date)
        except ValueError as exc:
            await reply_embed(ctx, title="Invalid Exam Input", description=str(exc), color=ERROR)
            return
        exam_id = self.bot.db.add_exam(ctx.guild.id, ctx.author.id, resolved_subject, exam_date)
        self.bot.db.add_xp(ctx.guild.id, ctx.author.id, 8)
        self.bot.db.sync_achievements(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Exam Added", description=f"Saved `{resolved_subject}` for `{exam_date}`.", color=SUCCESS, fields=[("Exam ID", str(exam_id), True)])

    @exam.command(name="list", description="List all of your upcoming exams.")
    async def exam_list(self, ctx: commands.Context) -> None:
        exams = self.bot.db.list_exams(ctx.guild.id, ctx.author.id)
        if not exams:
            await reply_embed(ctx, title="No Exams Saved", description="Add one with `/exam add`.", color=INFO)
            return
        value = "\n".join(f"`{row['id']}` {row['subject']} - `{row['exam_date']}`" for row in exams[:20])
        await reply_embed(ctx, title="Upcoming Exams", description=value, color=INFO)

    @exam.command(name="countdown", description="Show how many days are left until your exams.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def exam_countdown(self, ctx: commands.Context, subject: str = "", custom_subject: str = "") -> None:
        resolved_subject = ""
        if subject:
            try:
                resolved_subject = resolve_subject(ctx, subject, custom_subject)
            except ValueError as exc:
                await reply_embed(ctx, title="Invalid Subject", description=str(exc), color=ERROR)
                return
        exams = self.bot.db.list_exams(ctx.guild.id, ctx.author.id, resolved_subject)
        if not exams:
            await reply_embed(ctx, title="No Exams Found", description="There are no matching upcoming exams.", color=INFO)
            return
        today = datetime.now(UTC).date()
        value = [f"{row['subject']}: `{(datetime.fromisoformat(row['exam_date']).date() - today).days}` days left" for row in exams[:20]]
        await reply_embed(ctx, title="Exam Countdown", description="\n".join(value), color=INFO)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Study(bot))
