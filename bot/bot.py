from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging

import discord
from discord.ext import commands, tasks

from bot.ai import StudyAI
from bot.config import Settings, load_settings
from bot.database import Database
from bot.logging_setup import configure_logging
from bot.ui import INFO, SUCCESS, WARNING, make_embed, reply_embed, reply_to_message

log = logging.getLogger(__name__)
CAMERA_WARNING_CHANNEL_ID = 1490599054479196313
CAMERA_WARNING_DELAY = timedelta(minutes=2)
CAMERA_KICK_DELAY = timedelta(minutes=4)


@dataclass(slots=True)
class StudyTimer:
    user_id: int
    guild_id: int
    channel_id: int
    source_message_id: int
    minutes: int
    session_type: str
    ends_at: datetime


@dataclass(slots=True)
class CameraWatch:
    guild_id: int
    user_id: int
    channel_id: int
    started_at: datetime
    warned_at: datetime | None = None


class StudyBot(commands.Bot):
    def __init__(self, settings: Settings, db: Database) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.voice_states = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(settings.prefix),
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
        )
        self.settings = settings
        self.db = db
        self.ai = StudyAI(settings.openai_api_key, settings.openai_model)
        self.active_timers: dict[tuple[int, int], StudyTimer] = {}
        self.quiz_sessions: dict[tuple[int, int], dict[str, object]] = {}
        self.distraction_cooldowns: dict[tuple[int, int], datetime] = {}
        self.camera_watches: dict[tuple[int, int], CameraWatch] = {}
        self._synced_guilds: set[int] = set()
        self.add_check(self._guild_only_check)

    async def _guild_only_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This bot only works inside study servers.")
        return True

    async def setup_hook(self) -> None:
        for extension in (
            "bot.cogs.meta",
            "bot.cogs.task",
            "bot.cogs.study",
            "bot.cogs.notes",
            "bot.cogs.progress",
            "bot.cogs.learning",
            "bot.cogs.ai",
            "bot.cogs.analytics",
            "bot.cogs.gamification",
            "bot.cogs.community",
            "bot.cogs.utility",
            "bot.cogs.moderation",
        ):
            await self.load_extension(extension)
        self.reminder_worker.start()
        self.timer_worker.start()
        self.weekly_reward_worker.start()
        self.camera_enforcement_worker.start()
        self.daily_report_worker.start()
        log.info("Loaded study bot extensions")

    async def on_ready(self) -> None:
        for guild in self.guilds:
            if guild.id in self._synced_guilds:
                continue
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            self._synced_guilds.add(guild.id)
        log.info(
            "Ready as %s (%s) | prefix=%s | mongo_db=%s",
            self.user,
            self.user.id if self.user else "unknown",
            self.settings.prefix,
            self.settings.mongodb_database,
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        stats = self.db.get_user_stats(message.guild.id, message.author.id)
        if stats.get("focus_mode"):
            prefixes = (self.settings.prefix, self.user.mention if self.user else "")
            is_command = any(prefix and message.content.startswith(prefix) for prefix in prefixes)
            if not is_command:
                key = (message.guild.id, message.author.id)
                now = datetime.now(UTC)
                cooldown_until = self.distraction_cooldowns.get(key)
                if cooldown_until is None or now >= cooldown_until:
                    self.distraction_cooldowns[key] = now + timedelta(minutes=5)
                    self.db.add_distraction_warning(message.guild.id, message.author.id)
                    await reply_to_message(
                        message,
                        user=message.author,
                        title="Focus Mode Active",
                        description="Distraction detected. Use study commands or stay off chat until your session is done.",
                        color=WARNING,
                    )

        await self.process_commands(message)

    async def on_command_error(self, context: commands.Context, exception: commands.CommandError) -> None:
        if isinstance(exception, commands.CommandNotFound):
            return
        if isinstance(exception, commands.MissingPermissions):
            await reply_embed(context, title="Permission Error", description="You do not have permission to use that command.", color=WARNING)
            return
        if isinstance(exception, commands.NoPrivateMessage):
            await reply_embed(context, title="Server Only", description=str(exception), color=WARNING)
            return
        if isinstance(exception, commands.MissingRequiredArgument):
            await reply_embed(context, title="Missing Argument", description=f"Missing argument: `{exception.param.name}`.", color=WARNING)
            return
        if isinstance(exception, commands.BadArgument):
            await reply_embed(context, title="Invalid Argument", description="Invalid argument format for that command.", color=WARNING)
            return
        raise exception

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot or member.guild is None:
            return
        key = (member.guild.id, member.id)
        if before.channel is None and after.channel is not None:
            self.db.start_voice_session(member.guild.id, member.id, after.channel.id)
        elif before.channel is not None and after.channel is None:
            self.db.stop_voice_session(member.guild.id, member.id)
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            self.db.stop_voice_session(member.guild.id, member.id)
            self.db.start_voice_session(member.guild.id, member.id, after.channel.id)
        if (
            after.channel is None
            or not isinstance(after.channel, discord.VoiceChannel)
            or self.db.is_active_room_channel(member.guild.id, after.channel.id)
            or after.self_video
        ):
            self.camera_watches.pop(key, None)
            return
        current = self.camera_watches.get(key)
        if current is None or current.channel_id != after.channel.id or before.self_video:
            self.camera_watches[key] = CameraWatch(
                guild_id=member.guild.id,
                user_id=member.id,
                channel_id=after.channel.id,
                started_at=datetime.now(UTC),
            )

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if isinstance(channel, discord.VoiceChannel):
            self.db.deactivate_room(channel.id)

    async def reply_to_source(
        self,
        *,
        channel_id: int,
        message_id: int,
        user_id: int,
        title: str,
        description: str,
        color: discord.Color,
    ) -> None:
        channel = self.get_channel(channel_id)
        user = self.get_user(user_id)
        if user is None:
            try:
                user = await self.fetch_user(user_id)
            except discord.HTTPException:
                user = None
        if channel is None or user is None or not hasattr(channel, "get_partial_message"):
            return
        try:
            partial = channel.get_partial_message(message_id)
            await reply_to_message(partial, user=user, title=title, description=description, color=color)
        except discord.HTTPException:
            return

    async def send_dm_embed(self, *, user_id: int, title: str, description: str, color: discord.Color) -> None:
        user = self.get_user(user_id)
        if user is None:
            try:
                user = await self.fetch_user(user_id)
            except discord.HTTPException:
                return
        embed = make_embed(user=user, title=title, description=description, color=color)
        try:
            await user.send(embed=embed)
        except discord.HTTPException:
            return

    async def send_camera_notice(self, *, member: discord.Member, channel: discord.VoiceChannel, title: str, description: str, color: discord.Color) -> None:
        warning_channel = member.guild.get_channel(CAMERA_WARNING_CHANNEL_ID)
        if warning_channel is None or not hasattr(warning_channel, "send"):
            return
        embed = make_embed(user=member, title=title, description=description, color=color)
        try:
            await warning_channel.send(content=f"{member.mention} {channel.mention}", embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException:
            return

    async def send_daily_report(self, *, guild: discord.Guild, user_id: int) -> None:
        summary = self.db.analytics_summary(guild.id, user_id)
        description = (
            f"Study hours: `{summary['study_hours']}`\n"
            f"Today vs goal: `{summary['today_hours']}` / `{summary['daily_goal_hours']}`\n"
            f"Streak: `{summary['streak']}` days\n"
            f"Focus minutes: `{summary['focus_minutes']}`\n"
            f"Voice minutes: `{summary['voice_minutes']}`"
        )
        await self.send_dm_embed(user_id=user_id, title="Daily Study Report", description=description, color=INFO)

    @tasks.loop(seconds=15)
    async def reminder_worker(self) -> None:
        if not self.is_ready():
            return
        now = datetime.now(UTC)
        for reminder in self.db.due_reminders(now):
            await self.send_dm_embed(
                user_id=reminder["user_id"],
                title="Reminder",
                description=reminder["message"],
                color=INFO,
            )
            if reminder["recurring"] == "daily":
                next_run = reminder["remind_at"] + timedelta(days=1)
                self.db.reschedule_daily_reminder(reminder["id"], next_run)
            else:
                self.db.delete_reminder(reminder["id"])

    @tasks.loop(hours=1)
    async def weekly_reward_worker(self) -> None:
        if not self.is_ready():
            return
        now = datetime.now(UTC)
        if now.weekday() != 0:
            return
        previous_week = (now - timedelta(days=7)).isocalendar()
        week_key = f"{previous_week.year}-W{previous_week.week:02d}"
        for guild in self.guilds:
            if self.db.get_weekly_reward_status(guild.id, week_key):
                continue
            rows = self.db.weekly_progress_leaderboard(guild.id, limit=10)
            rewarded_user_ids = [row["user_id"] for row in rows]
            for user_id in rewarded_user_ids:
                self.db.add_coins(guild.id, user_id, 100)
            self.db.mark_weekly_rewards(guild.id, week_key, rewarded_user_ids)

    @tasks.loop(hours=1)
    async def daily_report_worker(self) -> None:
        if not self.is_ready():
            return
        now = datetime.now(UTC)
        if now.hour < 20:
            return
        today = now.date().isoformat()
        for guild in self.guilds:
            for row in self.db.get_daily_report_candidates(guild.id):
                if row.get("last_study_day") != today or row.get("last_report_day") == today:
                    continue
                await self.send_daily_report(guild=guild, user_id=row["user_id"])
                self.db.mark_daily_report_sent(guild.id, row["user_id"], today)

    @tasks.loop(seconds=20)
    async def camera_enforcement_worker(self) -> None:
        if not self.is_ready():
            return
        now = datetime.now(UTC)
        active_keys: set[tuple[int, int]] = set()
        for guild in self.guilds:
            for channel in guild.voice_channels:
                if self.db.is_active_room_channel(guild.id, channel.id):
                    continue
                for member in channel.members:
                    if member.bot:
                        continue
                    if member.voice is not None and member.voice.self_video:
                        self.camera_watches.pop((guild.id, member.id), None)
                        continue
                    key = (guild.id, member.id)
                    active_keys.add(key)
                    watch = self.camera_watches.get(key)
                    if watch is None or watch.channel_id != channel.id:
                        watch = CameraWatch(
                            guild_id=guild.id,
                            user_id=member.id,
                            channel_id=channel.id,
                            started_at=now,
                        )
                        self.camera_watches[key] = watch
                    if watch.warned_at is None and now - watch.started_at >= CAMERA_WARNING_DELAY:
                        await self.send_camera_notice(
                            member=member,
                            channel=channel,
                            title="Camera Required",
                            description="Please turn on your camera within 2 minutes or you will be removed from the voice channel.",
                            color=WARNING,
                        )
                        watch.warned_at = now
                        continue
                    if watch.warned_at is not None and now - watch.started_at >= CAMERA_KICK_DELAY:
                        removed = False
                        try:
                            await member.move_to(None, reason="Camera required in monitored voice channels.")
                            removed = True
                        except discord.HTTPException:
                            removed = False
                        await self.send_camera_notice(
                            member=member,
                            channel=channel,
                            title="Voice Channel Removal" if removed else "Camera Enforcement Failed",
                            description="You were removed for keeping your camera off for over 4 minutes." if removed else "Camera stayed off for over 4 minutes, but I could not disconnect you. Check bot permissions and role hierarchy.",
                            color=WARNING,
                        )
                        self.camera_watches.pop(key, None)
        for key in list(self.camera_watches):
            if key not in active_keys:
                self.camera_watches.pop(key, None)

    @tasks.loop(seconds=10)
    async def timer_worker(self) -> None:
        if not self.is_ready():
            return
        now = datetime.now(UTC)
        expired: list[tuple[int, int]] = []
        for key, timer in self.active_timers.items():
            if now >= timer.ends_at:
                if timer.session_type == "focus":
                    self.db.record_study_session(timer.guild_id, timer.user_id, "focus", timer.minutes)
                    title = "Study Session Complete"
                    description = f"Your `{timer.minutes}` minute focus session is complete. Take a short break."
                    color = SUCCESS
                else:
                    title = "Break Complete"
                    description = f"Your `{timer.minutes}` minute break is over. Back to focused work."
                    color = INFO
                await self.reply_to_source(
                    channel_id=timer.channel_id,
                    message_id=timer.source_message_id,
                    user_id=timer.user_id,
                    title=title,
                    description=description,
                    color=color,
                )
                expired.append(key)
        for key in expired:
            self.active_timers.pop(key, None)

    @reminder_worker.before_loop
    @timer_worker.before_loop
    @weekly_reward_worker.before_loop
    @camera_enforcement_worker.before_loop
    @daily_report_worker.before_loop
    async def before_background_workers(self) -> None:
        await self.wait_until_ready()


def build_bot() -> StudyBot:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        db = Database(settings.mongodb_uri, settings.mongodb_database)
    except Exception as exc:
        raise RuntimeError(f"MongoDB initialization failed for {settings.mongodb_uri}: {exc}") from exc
    return StudyBot(settings, db)


def run() -> None:
    bot = build_bot()
    bot.run(bot.settings.token, log_handler=None)
