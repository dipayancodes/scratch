from __future__ import annotations

from datetime import UTC, datetime, timedelta

from discord.ext import commands

from bot.bot import StudyTimer
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


class Study(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.group(name="task", invoke_without_command=True)
    async def task(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Task Commands", description="Use `-task add/list/done/delete/clear`.", color=INFO)

    @task.command(name="add")
    async def task_add(self, ctx: commands.Context, *, task: str) -> None:
        task_id = self.bot.db.add_task(ctx.guild.id, ctx.author.id, task)
        await reply_embed(
            ctx,
            title="Task Added",
            description=f"Your study task has been saved.",
            color=SUCCESS,
            fields=[("Task ID", str(task_id), True), ("Task", task, False)],
        )

    @task.command(name="list")
    async def task_list(self, ctx: commands.Context) -> None:
        tasks = self.bot.db.list_tasks(ctx.guild.id, ctx.author.id)
        if not tasks:
            await reply_embed(ctx, title="No Pending Tasks", description="You are clear for now. Add a new task to stay organized.", color=INFO)
            return
        value = "\n".join(f"`{row['id']}` {row['content']}" for row in tasks[:15])
        await reply_embed(ctx, title="Pending Tasks", description="Here are your current study tasks.", color=INFO, fields=[("Tasks", value, False)])

    @task.command(name="done")
    async def task_done(self, ctx: commands.Context, task_id: int) -> None:
        if not self.bot.db.complete_task(ctx.guild.id, ctx.author.id, task_id):
            await reply_embed(ctx, title="Task Not Found", description=f"No pending task exists with ID `{task_id}`.", color=ERROR)
            return
        self.bot.db.add_coins(ctx.guild.id, ctx.author.id, 10)
        await reply_embed(
            ctx,
            title="Task Completed",
            description=f"Task `{task_id}` marked as complete.",
            color=SUCCESS,
            fields=[("Reward", "`10 study coins`", True)],
        )

    @task.command(name="delete")
    async def task_delete(self, ctx: commands.Context, task_id: int) -> None:
        if not self.bot.db.delete_task(ctx.guild.id, ctx.author.id, task_id):
            await reply_embed(ctx, title="Task Not Found", description=f"No task exists with ID `{task_id}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Task Deleted", description=f"Task `{task_id}` has been removed.", color=SUCCESS)

    @task.command(name="clear")
    async def task_clear(self, ctx: commands.Context) -> None:
        count = self.bot.db.clear_tasks(ctx.guild.id, ctx.author.id)
        await reply_embed(ctx, title="Tasks Cleared", description=f"Removed `{count}` tasks from your list.", color=SUCCESS)

    @commands.group(name="study", invoke_without_command=True)
    async def study(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Study Timer Commands", description="Use `-study start/break/stop/status`.", color=INFO)

    @study.command(name="start")
    async def study_start(self, ctx: commands.Context, minutes: int) -> None:
        minutes = max(1, min(minutes, 240))
        key = (ctx.guild.id, ctx.author.id)
        if self.bot.active_timers.get(key):
            await reply_embed(ctx, title="Timer Already Running", description="Stop the current session before starting a new one.", color=WARNING)
            return
        ends_at = datetime.now(UTC) + timedelta(minutes=minutes)
        self.bot.active_timers[key] = StudyTimer(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            source_message_id=ctx.message.id,
            minutes=minutes,
            session_type="focus",
            ends_at=ends_at,
        )
        await reply_embed(
            ctx,
            title="Focus Session Started",
            description=f"Your study timer is active for `{minutes}` minutes.",
            color=SUCCESS,
            fields=[("Ends", f"<t:{int(ends_at.timestamp())}:R>", True)],
        )

    @study.command(name="break")
    async def study_break(self, ctx: commands.Context, minutes: int) -> None:
        minutes = max(1, min(minutes, 60))
        key = (ctx.guild.id, ctx.author.id)
        ends_at = datetime.now(UTC) + timedelta(minutes=minutes)
        self.bot.active_timers[key] = StudyTimer(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            source_message_id=ctx.message.id,
            minutes=minutes,
            session_type="break",
            ends_at=ends_at,
        )
        await reply_embed(
            ctx,
            title="Break Timer Started",
            description=f"Your break timer is active for `{minutes}` minutes.",
            color=INFO,
            fields=[("Ends", f"<t:{int(ends_at.timestamp())}:R>", True)],
        )

    @study.command(name="stop")
    async def study_stop(self, ctx: commands.Context) -> None:
        removed = self.bot.active_timers.pop((ctx.guild.id, ctx.author.id), None)
        if not removed:
            await reply_embed(ctx, title="No Active Timer", description="You do not have a running focus or break session.", color=WARNING)
            return
        await reply_embed(ctx, title="Timer Stopped", description="Your current study timer has been stopped.", color=SUCCESS)

    @study.command(name="status")
    async def study_status(self, ctx: commands.Context) -> None:
        timer = self.bot.active_timers.get((ctx.guild.id, ctx.author.id))
        if not timer:
            await reply_embed(ctx, title="No Active Timer", description="Start one with `-study start <minutes>`.", color=WARNING)
            return
        remaining = max(0, int((timer.ends_at - datetime.now(UTC)).total_seconds() // 60))
        await reply_embed(
            ctx,
            title="Current Timer Status",
            description=f"Your `{timer.session_type}` timer is still running.",
            color=INFO,
            fields=[("Remaining", f"`{remaining}` minutes", True)],
        )

    @commands.group(name="notes", invoke_without_command=True)
    async def notes(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Notes Commands", description="Use `-notes add/view/list/delete`.", color=INFO)

    @notes.command(name="add")
    async def notes_add(self, ctx: commands.Context, *, payload: str) -> None:
        if "|" not in payload:
            await reply_embed(ctx, title="Invalid Notes Format", description="Use `-notes add <title> | <content>`.", color=ERROR)
            return
        title, content = [part.strip() for part in payload.split("|", 1)]
        self.bot.db.save_note(ctx.guild.id, ctx.author.id, title, content)
        await reply_embed(
            ctx,
            title="Note Saved",
            description=f"Your note `{title}` has been stored for revision.",
            color=SUCCESS,
            fields=[("Preview", content[:200], False)],
        )

    @notes.command(name="view")
    async def notes_view(self, ctx: commands.Context, *, title: str) -> None:
        note = self.bot.db.get_note(ctx.guild.id, ctx.author.id, title)
        if not note:
            await reply_embed(ctx, title="Note Not Found", description=f"No note exists with title `{title}`.", color=ERROR)
            return
        await reply_embed(
            ctx,
            title=f"Note: {note['title']}",
            description=note["content"][:3500],
            color=INFO,
            fields=[("Updated", note["created_at"].strftime("%Y-%m-%d %H:%M UTC"), True)],
        )

    @notes.command(name="list")
    async def notes_list(self, ctx: commands.Context) -> None:
        notes = self.bot.db.list_notes(ctx.guild.id, ctx.author.id)
        if not notes:
            await reply_embed(ctx, title="No Notes Saved", description="Add one with `-notes add <title> | <content>`.", color=INFO)
            return
        value = "\n".join(f"- {row['title']}" for row in notes[:20])
        await reply_embed(ctx, title="Saved Notes", description="Your revision note library.", color=INFO, fields=[("Titles", value, False)])

    @notes.command(name="delete")
    async def notes_delete(self, ctx: commands.Context, *, title: str) -> None:
        if not self.bot.db.delete_note(ctx.guild.id, ctx.author.id, title):
            await reply_embed(ctx, title="Note Not Found", description=f"No note exists with title `{title}`.", color=ERROR)
            return
        await reply_embed(ctx, title="Note Deleted", description=f"Removed note `{title}`.", color=SUCCESS)

    @commands.group(name="plan", invoke_without_command=True)
    async def plan(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Planner Commands", description="Use `-plan set/view/today/generate`.", color=INFO)

    @plan.command(name="set")
    async def plan_set(self, ctx: commands.Context, day: str, *, tasks: str) -> None:
        self.bot.db.set_plan(ctx.guild.id, ctx.author.id, day, tasks)
        await reply_embed(
            ctx,
            title="Plan Saved",
            description=f"Your plan for `{day}` has been updated.",
            color=SUCCESS,
            fields=[("Tasks", tasks[:500], False)],
        )

    @plan.command(name="view")
    async def plan_view(self, ctx: commands.Context, day: str) -> None:
        plan = self.bot.db.get_plan(ctx.guild.id, ctx.author.id, day)
        if not plan:
            await reply_embed(ctx, title="No Plan Found", description=f"No plan exists for `{day}`.", color=WARNING)
            return
        await reply_embed(ctx, title=f"Plan for {plan['day']}", description=plan["tasks"][:3500], color=INFO)

    @plan.command(name="today")
    async def plan_today(self, ctx: commands.Context) -> None:
        day = datetime.now().strftime("%A").lower()
        plan = self.bot.db.get_plan(ctx.guild.id, ctx.author.id, day)
        if not plan:
            await reply_embed(ctx, title="No Plan for Today", description="Set one with `-plan set today <tasks>` or your weekday name.", color=WARNING)
            return
        await reply_embed(ctx, title="Today's Study Plan", description=plan["tasks"][:3500], color=INFO)

    @plan.command(name="generate")
    async def plan_generate(self, ctx: commands.Context, exam: str, days: int) -> None:
        result = await self.bot.ai.generate_plan(exam, days)
        await reply_embed(ctx, title=f"Generated Plan: {exam}", description=result[:3500], color=INFO)

    @commands.group(name="progress", invoke_without_command=True)
    async def progress(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Progress Commands", description="Use `-progress add/stats/weekly/leaderboard`.", color=INFO)

    @progress.command(name="add")
    async def progress_add(self, ctx: commands.Context, subject: str, hours: float) -> None:
        hours = max(0.25, min(hours, 24.0))
        self.bot.db.add_progress(ctx.guild.id, ctx.author.id, subject, hours)
        await reply_embed(
            ctx,
            title="Study Hours Logged",
            description=f"Recorded `{hours}` hours for `{subject}`.",
            color=SUCCESS,
            fields=[("Coin Reward", f"`{int(hours * 20)}`", True)],
        )

    @progress.command(name="stats")
    async def progress_stats(self, ctx: commands.Context) -> None:
        totals = self.bot.db.get_progress_totals(ctx.guild.id, ctx.author.id)
        streak = self.bot.db.refresh_streak(ctx.guild.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Progress Stats",
            description="Your overall study logging summary.",
            color=INFO,
            fields=[
                ("Total Hours", f"`{totals['logged_hours']}`", True),
                ("Entries", f"`{totals['entries']}`", True),
                ("Current Streak", f"`{streak['streak']}` days", True),
            ],
        )

    @progress.command(name="weekly")
    async def progress_weekly(self, ctx: commands.Context) -> None:
        rows = self.bot.db.get_weekly_progress(ctx.guild.id, ctx.author.id)
        if not rows:
            await reply_embed(ctx, title="No Weekly Progress", description="Log some study hours first with `-progress add`.", color=WARNING)
            return
        value = "\n".join(f"- {row['subject']}: `{row['hours']}h`" for row in rows[:10])
        await reply_embed(ctx, title="Weekly Progress", description="Your last 7 days by subject.", color=INFO, fields=[("Breakdown", value, False)])

    @progress.command(name="leaderboard")
    async def progress_leaderboard(self, ctx: commands.Context) -> None:
        rows = self.bot.db.progress_leaderboard(ctx.guild.id)
        if not rows:
            await reply_embed(ctx, title="Leaderboard Empty", description="No progress has been logged in this server yet.", color=WARNING)
            return
        lines = []
        for index, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row["user_id"])
            lines.append(f"{index}. {(member.display_name if member else row['user_id'])} - `{row['total_hours']}h`")
        await reply_embed(ctx, title="Study Hours Leaderboard", description="\n".join(lines), color=INFO)

    @commands.command(name="streak")
    async def streak(self, ctx: commands.Context, action: str = "") -> None:
        if action.lower() == "reset":
            self.bot.db.reset_streak(ctx.guild.id, ctx.author.id)
            await reply_embed(ctx, title="Streak Reset", description="Your study streak has been reset.", color=WARNING)
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
            ],
        )

    @commands.group(name="goal", invoke_without_command=True)
    async def goal(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Goal Commands", description="Use `-goal set/status`.", color=INFO)

    @goal.command(name="set")
    async def goal_set(self, ctx: commands.Context, hours_per_day: float) -> None:
        hours_per_day = max(0.5, min(hours_per_day, 16.0))
        self.bot.db.set_goal(ctx.guild.id, ctx.author.id, hours_per_day)
        await reply_embed(ctx, title="Goal Updated", description=f"Your daily study goal is now `{hours_per_day}` hours.", color=SUCCESS)

    @goal.command(name="status")
    async def goal_status(self, ctx: commands.Context) -> None:
        summary = self.bot.db.analytics_summary(ctx.guild.id, ctx.author.id)
        await reply_embed(
            ctx,
            title="Goal Status",
            description="Here is your current progress toward today's target.",
            color=INFO,
            fields=[
                ("Today's Hours", f"`{summary['today_hours']}`", True),
                ("Daily Goal", f"`{summary['daily_goal_hours']}`", True),
                ("Pending Tasks", f"`{summary['pending_tasks']}`", True),
            ],
        )

    @commands.group(name="remind", invoke_without_command=True)
    async def remind(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Reminder Commands", description="Use `-remind me/daily/list`.", color=INFO)

    @remind.command(name="me")
    async def remind_me(self, ctx: commands.Context, duration: str, *, task: str) -> None:
        try:
            delta = parse_duration(duration)
        except (ValueError, IndexError):
            await reply_embed(ctx, title="Invalid Duration", description="Use a duration like `30m`, `2h`, or `1d`.", color=ERROR)
            return
        remind_at = datetime.now(UTC) + delta
        reminder_id = self.bot.db.add_reminder(
            ctx.guild.id,
            ctx.channel.id,
            ctx.author.id,
            task,
            remind_at,
            ctx.message.id,
        )
        await reply_embed(
            ctx,
            title="Reminder Created",
            description=f"Your reminder is scheduled.",
            color=SUCCESS,
            fields=[
                ("Reminder ID", str(reminder_id), True),
                ("When", f"<t:{int(remind_at.timestamp())}:R>", True),
                ("Task", task[:200], False),
            ],
        )

    @remind.command(name="daily")
    async def remind_daily(self, ctx: commands.Context, time_value: str, *, task: str = "Daily study reminder") -> None:
        try:
            hour, minute = parse_daily_time(time_value)
        except ValueError:
            await reply_embed(ctx, title="Invalid Time", description="Use 24-hour time like `07:30` or `21:15`.", color=ERROR)
            return
        now = datetime.now(UTC)
        remind_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if remind_at <= now:
            remind_at += timedelta(days=1)
        reminder_id = self.bot.db.add_reminder(
            ctx.guild.id,
            ctx.channel.id,
            ctx.author.id,
            task,
            remind_at,
            ctx.message.id,
            recurring="daily",
            daily_time=time_value,
        )
        await reply_embed(
            ctx,
            title="Daily Reminder Created",
            description=f"Your daily reminder is active.",
            color=SUCCESS,
            fields=[("Reminder ID", str(reminder_id), True), ("Next Run", f"<t:{int(remind_at.timestamp())}:R>", True)],
        )

    @remind.command(name="list")
    async def remind_list(self, ctx: commands.Context) -> None:
        reminders = self.bot.db.list_reminders(ctx.guild.id, ctx.author.id)
        if not reminders:
            await reply_embed(ctx, title="No Reminders", description="You have no active reminders.", color=INFO)
            return
        lines = [
            f"`{row['id']}` {row['message']} -> <t:{int(row['remind_at'].timestamp())}:R> ({row['recurring']})"
            for row in reminders[:12]
        ]
        await reply_embed(ctx, title="Your Reminders", description="\n".join(lines), color=INFO)

    @commands.group(name="exam", invoke_without_command=True)
    async def exam(self, ctx: commands.Context) -> None:
        await reply_embed(ctx, title="Exam Commands", description="Use `-exam add/list/countdown`.", color=INFO)

    @exam.command(name="add")
    async def exam_add(self, ctx: commands.Context, subject: str, date_value: str) -> None:
        try:
            exam_date = parse_exam_date(date_value)
        except ValueError:
            await reply_embed(ctx, title="Invalid Date", description="Use the format `YYYY-MM-DD`.", color=ERROR)
            return
        exam_id = self.bot.db.add_exam(ctx.guild.id, ctx.author.id, subject, exam_date)
        await reply_embed(
            ctx,
            title="Exam Added",
            description=f"Saved `{subject}` for `{exam_date}`.",
            color=SUCCESS,
            fields=[("Exam ID", str(exam_id), True)],
        )

    @exam.command(name="list")
    async def exam_list(self, ctx: commands.Context) -> None:
        exams = self.bot.db.list_exams(ctx.guild.id, ctx.author.id)
        if not exams:
            await reply_embed(ctx, title="No Exams Saved", description="Add one with `-exam add <subject> <date>`.", color=INFO)
            return
        value = "\n".join(f"`{row['id']}` {row['subject']} - `{row['exam_date']}`" for row in exams[:15])
        await reply_embed(ctx, title="Upcoming Exams", description=value, color=INFO)

    @exam.command(name="countdown")
    async def exam_countdown(self, ctx: commands.Context) -> None:
        exams = self.bot.db.list_exams(ctx.guild.id, ctx.author.id)
        if not exams:
            await reply_embed(ctx, title="No Exams Saved", description="Add exams before using countdown.", color=INFO)
            return
        today = datetime.now().date()
        value = []
        for row in exams[:10]:
            exam_day = datetime.fromisoformat(row["exam_date"]).date()
            value.append(f"{row['subject']}: `{(exam_day - today).days}` days left")
        await reply_embed(ctx, title="Exam Countdown", description="\n".join(value), color=INFO)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Study(bot))
