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
from bot.ui import INFO, SUCCESS, WARNING, reply_embed, reply_to_message

log = logging.getLogger(__name__)


@dataclass(slots=True)
class StudyTimer:
    user_id: int
    guild_id: int
    channel_id: int
    source_message_id: int
    minutes: int
    session_type: str
    ends_at: datetime


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
        self._synced_guilds: set[int] = set()
        self.add_check(self._guild_only_check)

    async def _guild_only_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This bot only works inside study servers.")
        return True

    async def setup_hook(self) -> None:
        for extension in (
            "bot.cogs.meta",
            "bot.cogs.study",
            "bot.cogs.learning",
            "bot.cogs.community",
            "bot.cogs.utility",
            "bot.cogs.moderation",
        ):
            await self.load_extension(extension)
        self.reminder_worker.start()
        self.timer_worker.start()
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
        if before.channel is None and after.channel is not None:
            self.db.start_voice_session(member.guild.id, member.id, after.channel.id)
            return
        if before.channel is not None and after.channel is None:
            self.db.stop_voice_session(member.guild.id, member.id)
            return
        if before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            self.db.stop_voice_session(member.guild.id, member.id)
            self.db.start_voice_session(member.guild.id, member.id, after.channel.id)

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

    @tasks.loop(seconds=15)
    async def reminder_worker(self) -> None:
        if not self.is_ready():
            return
        now = datetime.now(UTC)
        for reminder in self.db.due_reminders(now):
            await self.reply_to_source(
                channel_id=reminder["channel_id"],
                message_id=reminder["source_message_id"],
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
    async def before_background_workers(self) -> None:
        await self.wait_until_ready()


def build_bot() -> StudyBot:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        db = Database(settings.mongodb_uri, settings.mongodb_database)
    except Exception as exc:
        raise RuntimeError(
            f"MongoDB connection failed for {settings.mongodb_uri}. Start MongoDB or set MONGODB_URI to a reachable server."
        ) from exc
    return StudyBot(settings, db)


def run() -> None:
    bot = build_bot()
    bot.run(bot.settings.token, log_handler=None)
