from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from discord import app_commands
from discord.ext import commands

from bot.bot import StudyTimer
from bot.subjects import DAYS_OF_WEEK, finalize_subject, is_custom_subject, subject_autocomplete
from bot.ui import ERROR, INFO, SUCCESS, WARNING, reply_embed


def parse_duration(value: str) -> timedelta:
    units = {"m": 60, "h": 3600, "d": 86400}
    suffix = value[-1].lower()
    if suffix not in units:
        raise ValueError("Unsupported duration suffix.")
    return timedelta(seconds=int(value[:-1]) * units[suffix])


def parse_exam_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def parse_daily_time(value: str) -> tuple[int, int]:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour, parsed.minute


def next_weekday_date(day_name: str) -> str:
    day_index = DAYS_OF_WEEK.index(day_name.lower())
    today = datetime.now().date()
    delta = (day_index - today.weekday()) % 7
    target = today + timedelta(days=delta)
    return target.isoformat()


async def saved_plan_autocomplete(interaction, current: str) -> list[app_commands.Choice[str]]:
    db = interaction.client.db
    plans = db.list_plans(interaction.guild_id, interaction.user.id)
    current_lower = current.lower().strip()
    choices = []
    for plan in plans:
        label = f"{plan['day'].title()} - {plan['target_date']}"
        if current_lower and current_lower not in label.lower():
            continue
        choices.append(app_commands.Choice(name=label[:100], value=plan["target_date"]))
    return choices[:25]


class Study(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _resolve_subject(self, ctx: commands.Context, subject: str, custom_subject: str = "") -> str:
        resolved = finalize_subject(subject, custom_subject).strip()
        if subject.lower() == "others" and not custom_subject.strip():
            raise ValueError("Custom subject is required when you choose others.")
        if is_custom_subject(resolved):
            self.bot.db.add_custom_subject(ctx.guild.id, ctx.author.id, resolved)
        return resolved

    @commands.hybrid_group(name="task", description="Manage your study tasks.", invoke_without_command=True)
    async def task(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Task Commands", description="Use `/task add`, `/task list`, `/task done`, `/task delete`, or `/task clear`.", color=INFO)

    @task.command(name="add", description="Add a new study task.")
    @app_commands.describe(task="The task you want to add.")
    async def task_add(self, ctx: commands.Context, *, task: str) -> None:
        task_id = self.bot.db.add_task(ctx.guild.id, ctx.author.id, task)
        await reply_embed(ctx, title="Task Added", description="Your study task has been saved.", color=SUCCESS, fields=[("Task ID", str(task_id), True), ("Task", task, False)])

    @task.command(name="list", description="Show all your pending study tasks.")
    async def task_list(self, ctx: commands.Context) -> None:
        tasks = self.bot.db.list_tasks(ctx.guild.id, ctx.author.id)
        if not tasks:
            await reply_embed(ctx, title="No Pending Tasks", description="You have no pending tasks right now.", color=INFO)
            return
        value = "\n".join(f"`{row['id']}` {row['content']}" for row in tasks[:20])
        await reply_embed(ctx, title="Pending Tasks", description=value, color=INFO)

    @task.command(name="done", description="Mark one of your tasks as completed.")
    @app_commands.describe(task_id="The task ID you want to mark as done.")
    async def task_done(self, ctx: commands.Context, task_id: int) -> None:
        if not self.bot.db.complete_task(ctx.guild.id, ctx.author.id, task_id):
            await reply_embed(ctx, title="Task Not Found", description=f"No pending task exists with ID `{task_id}`.", color=ERROR)
            return
        self.bot.db.add_coins(ctx.guild.id, ctx.author.id, 10)
        await reply_embed(ctx, title="Task Completed", description=f"Task `{task_id}` marked complete.", color=SUCCESS, fields=[("Reward", "`10 study coins`", True)])

    @task.command(name="delete", description="Delete one of your saved tasks.")
    @app_commands.describe(task_id="The task ID you want to delete.")
    async def task_delete(self, ctx: commands.Context, task_id: int) -> None:
        if not self.bot.db.delete_task(ctx.guild.id, ctx.author.id, task_id):
            await reply_embed(ctx, title="Task Not Found", description=f"No task exists with ID `{task_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Task Deleted", description=f"Task `{task_id}` has been removed.", color=SUCCESS)

    @task.command(name="clear", description="Clear all tasks or just one task by ID.")
    @app_commands.describe(task_id="Optional task ID. Leave empty to clear all your tasks.")
    async def task_clear(self, ctx: commands.Context, task_id: int | None = None) -> None:
        if task_id is not None:
            if not self.bot.db.delete_task(ctx.guild.id, ctx.author.id, task_id):
                await reply_embed(ctx, title="Task Not Found", description=f"No task exists with ID `{task_id}`.", color=ERROR)
                return
            await reply_embed(ctx, title="Task Cleared", description=f"Removed task `{task_id}`.", color=SUCCESS)
            return
        count = self.bot.db.clear_tasks(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Tasks Cleared", description=f"Removed `{count}` tasks from your list.", color=SUCCESS)

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
        response = await reply_embed(ctx, title="Focus Session Started", description=f"Your study timer is active for `{total_minutes}` minutes.", color=SUCCESS, fields=[("Ends", f"<t:{int(ends_at.timestamp())}:R>", True)])
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
        response = await reply_embed(ctx, title="Break Timer Started", description=f"Your break timer is active for `{minutes}` minutes.", color=INFO, fields=[("Ends", f"<t:{int(ends_at.timestamp())}:R>", True)])
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

    @commands.hybrid_group(name="notes", description="Save and review study notes.", invoke_without_command=True)
    async def notes(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Notes Commands", description="Use `/notes add`, `/notes list`, `/notes view`, or `/notes delete`.", color=INFO)

    @notes.command(name="add", description="Save a new note.")
    @app_commands.describe(title="The note title.", content="The full content of the note.")
    async def notes_add(self, ctx: commands.Context, title: str, *, content: str) -> None:
        note_id = self.bot.db.save_note(ctx.guild.id, ctx.author.id, title, content)
        await reply_embed(ctx, title="Note Saved", description="Your note has been stored.", color=SUCCESS, fields=[("Note ID", str(note_id), True), ("Title", title, True)])

    @notes.command(name="list", description="List your saved notes with note IDs.")
    async def notes_list(self, ctx: commands.Context) -> None:
        notes = self.bot.db.list_notes(ctx.guild.id, ctx.author.id)
        if not notes:
            await reply_embed(ctx, title="No Notes Saved", description="Add one with `/notes add`.", color=INFO)
            return
        lines = [f"`{row['id']}` {row['title']}" for row in notes[:20]]
        await reply_embed(ctx, title="Your Notes", description="\n".join(lines), color=INFO)

    @notes.command(name="view", description="View one of your saved notes by ID.")
    @app_commands.describe(note_id="The note ID shown by `/notes list`.")
    async def notes_view(self, ctx: commands.Context, note_id: int) -> None:
        note = self.bot.db.get_note_by_id(ctx.guild.id, ctx.author.id, note_id)
        if not note:
            await reply_embed(ctx, title="Note Not Found", description=f"No note exists with ID `{note_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title=f"Note: {note['title']}", description=note["content"][:3500], color=INFO, fields=[("Note ID", str(note_id), True)])

    @notes.command(name="delete", description="Delete one of your saved notes by ID.")
    @app_commands.describe(note_id="The note ID shown by `/notes list`.")
    async def notes_delete(self, ctx: commands.Context, note_id: int) -> None:
        if not self.bot.db.delete_note_by_id(ctx.guild.id, ctx.author.id, note_id):
            await reply_embed(ctx, title="Note Not Found", description=f"No note exists with ID `{note_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Note Deleted", description=f"Removed note `{note_id}`.", color=SUCCESS)

    @commands.hybrid_group(name="plan", description="Create and review day-based study plans.", invoke_without_command=True)
    async def plan(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Plan Commands", description="Use `/plan set`, `/plan view`, or `/plan today`.", color=INFO)

    @plan.command(name="set", description="Save your study plan for the next occurrence of a weekday.")
    @app_commands.describe(day="Choose the day you want to plan for.", tasks="The study tasks for that day.")
    @app_commands.choices(day=[app_commands.Choice(name=day.title(), value=day) for day in DAYS_OF_WEEK])
    async def plan_set(self, ctx: commands.Context, day: str, *, tasks: str) -> None:
        target_date = next_weekday_date(day)
        self.bot.db.set_plan(ctx.guild.id, ctx.author.id, day, target_date, tasks)
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
        target_date = datetime.now().date().isoformat()
        plan = self.bot.db.get_plan_by_date(ctx.guild.id, ctx.author.id, target_date)
        if not plan:
            await reply_embed(ctx, title="No Plan For Today", description="You have no saved plan for today's date.", color=WARNING)
            return
        await reply_embed(ctx, title=f"Today's Plan: {plan['day'].title()} {plan['target_date']}", description=plan["tasks"][:3500], color=INFO)

    # Reserved for future AI study plan generation.
    # @plan.command(name="generate", description="Generate an AI study plan for an exam.")

    @commands.hybrid_group(name="progress", description="Log and review study progress.", invoke_without_command=True)
    async def progress(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Progress Commands", description="Use `/progress add`, `/progress stats`, `/progress weekly`, or `/progress leaderboard`.", color=INFO)

    @progress.command(name="add", description="Log study hours for a subject.")
    @app_commands.describe(subject="Choose a subject or select others.", hours="How many hours you studied.", custom_subject="If you choose others, type your own subject here.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def progress_add(self, ctx: commands.Context, subject: str, hours: float, custom_subject: str = "") -> None:
        try:
            resolved_subject = self._resolve_subject(ctx, subject, custom_subject)
        except ValueError as exc:
            await reply_embed(ctx, title="Subject Needed", description=str(exc), color=ERROR)
            return
        hours = max(0.25, min(hours, 24.0))
        self.bot.db.add_progress(ctx.guild.id, ctx.author.id, resolved_subject, hours)
        await reply_embed(ctx, title="Study Hours Logged", description=f"Recorded `{hours}` hours for `{resolved_subject}`.", color=SUCCESS, fields=[("Coin Reward", f"`{int(hours * 20)}`", True)])

    @progress.command(name="stats", description="Show your total logged study hours.")
    async def progress_stats(self, ctx: commands.Context) -> None:
        totals = self.bot.db.get_progress_totals(ctx.guild.id, ctx.author.id)
        streak = self.bot.db.refresh_streak(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Progress Stats", description="Your overall study summary.", color=INFO, fields=[("Total Hours", f"`{totals['logged_hours']}`", True), ("Entries", f"`{totals['entries']}`", True), ("Current Streak", f"`{streak['streak']}` days", True)])

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

    @commands.hybrid_command(name="streak", description="Check or reset your study streak.")
    @app_commands.describe(action="Choose reset if you want to reset your streak.")
    @app_commands.choices(action=[app_commands.Choice(name="reset", value="reset")])
    async def streak(self, ctx: commands.Context, action: str = "") -> None:
        if action.lower() == "reset":
            self.bot.db.reset_streak(ctx.guild.id, ctx.author.id)
            await reply_embed(ctx, title="Streak Reset", description="Your study streak has been reset.", color=WARNING)
            return
        stats = self.bot.db.refresh_streak(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Study Streak", description="Consistency stats for your study habit.", color=INFO, fields=[("Current", f"`{stats['streak']}` days", True), ("Longest", f"`{stats['longest_streak']}` days", True)])

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
        await reply_embed(ctx, title="Goal Status", description="Here is your current goal progress.", color=INFO, fields=[("Today's Hours", f"`{summary['today_hours']}`", True), ("Daily Goal", f"`{summary['daily_goal_hours']}`", True), ("Pending Tasks", f"`{summary['pending_tasks']}`", True)])

    @commands.hybrid_group(name="remind", description="Create and manage study reminders.", invoke_without_command=True)
    async def remind(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Reminder Commands", description="Use `/remind me`, `/remind daily`, `/remind list`, or `/remind delete`.", color=INFO)

    @remind.command(name="me", description="Create a one-time reminder.")
    @app_commands.describe(duration="Time like 30m, 2h, or 1d.", task="What you want to be reminded about.")
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
    @app_commands.describe(time="24-hour time like 07:30 or 21:15.", task="The daily reminder text.")
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
    @app_commands.describe(reminder_id="The reminder ID shown by `/remind list`.")
    async def remind_delete(self, ctx: commands.Context, reminder_id: int) -> None:
        if not self.bot.db.delete_reminder_for_user(ctx.guild.id, ctx.author.id, reminder_id):
            await reply_embed(ctx, title="Reminder Not Found", description=f"No reminder exists with ID `{reminder_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Reminder Deleted", description=f"Removed reminder `{reminder_id}`.", color=SUCCESS)

    @commands.hybrid_group(name="exam", description="Track exams and countdowns.", invoke_without_command=True)
    async def exam(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Exam Commands", description="Use `/exam add`, `/exam list`, or `/exam countdown`.", color=INFO)

    @exam.command(name="add", description="Add an upcoming exam.")
    @app_commands.describe(subject="Choose a subject or select others.", date="Exam date in YYYY-MM-DD format.", custom_subject="If you choose others, type your own subject here.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def exam_add(self, ctx: commands.Context, subject: str, date: str, custom_subject: str = "") -> None:
        try:
            resolved_subject = self._resolve_subject(ctx, subject, custom_subject)
            exam_date = parse_exam_date(date)
        except ValueError as exc:
            await reply_embed(ctx, title="Invalid Exam Input", description=str(exc), color=ERROR)
            return
        exam_id = self.bot.db.add_exam(ctx.guild.id, ctx.author.id, resolved_subject, exam_date)
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
    @app_commands.describe(subject="Optional subject filter.", custom_subject="If you choose others, type your own subject here.")
    @app_commands.autocomplete(subject=subject_autocomplete)
    async def exam_countdown(self, ctx: commands.Context, subject: str = "", custom_subject: str = "") -> None:
        resolved_subject = ""
        if subject:
            try:
                resolved_subject = self._resolve_subject(ctx, subject, custom_subject)
            except ValueError as exc:
                await reply_embed(ctx, title="Invalid Subject", description=str(exc), color=ERROR)
                return
        exams = self.bot.db.list_exams(ctx.guild.id, ctx.author.id, resolved_subject)
        if not exams:
            await reply_embed(ctx, title="No Exams Found", description="There are no matching upcoming exams.", color=INFO)
            return
        today = datetime.now().date()
        value = [f"{row['subject']}: `{(datetime.fromisoformat(row['exam_date']).date() - today).days}` days left" for row in exams[:20]]
        await reply_embed(ctx, title="Exam Countdown", description="\n".join(value), color=INFO)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Study(bot))
