from __future__ import annotations

from datetime import timedelta
import logging
import re

import discord
from discord.ext import commands, tasks

from bot.ui import ERROR, WARNING, make_embed, reply_to_message


log = logging.getLogger(__name__)

EXCLUDED_CHANNEL_IDS = {
    1453299769916129350,
    1453299878665912450,
    1453299960387731477,
    1490777438215733358,
}
REPORTING_PATTERN = re.compile(r"\b\w+\s+(said|told|mentioned|wrote|replied|asked)\b", re.IGNORECASE)
SPEAKER_PATTERN = re.compile(r"^\s*\w+\s*:", re.IGNORECASE)
LANGUAGE_MUTE_DURATION = timedelta(hours=2)
LANGUAGE_WARNING_DECAY_HOURS = 24
LANGUAGE_BAN_REASON = "Using non-English language in English-only channels"
EXPLICIT_BAN_REASON = "Using explicit or vulgar language in the server"
BEHAVIOR_BAN_REASON = "Using insulting or hostile language in the server"


def is_reporting_sentence(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    return bool(REPORTING_PATTERN.search(text) or SPEAKER_PATTERN.search(text))


class LanguageEnforcer(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.warning_decay_worker.start()

    def cog_unload(self) -> None:
        self.warning_decay_worker.cancel()

    async def _db_call(self, func, *args, default=None, operation: str = "database operation", **kwargs):
        helper = getattr(self.bot, "_db_call", None)
        if callable(helper):
            return await helper(func, *args, default=default, operation=operation, **kwargs)
        return func(*args, **kwargs)

    def _flagged_excerpt(self, content: str) -> str:
        compact = re.sub(r"\s+", " ", content or "").strip()
        if not compact:
            return "No readable text found."
        compact = compact.replace("`", "'")
        if len(compact) > 220:
            return compact[:217] + "..."
        return compact

    async def _reply_warning(
        self,
        *,
        message: discord.Message,
        member: discord.Member,
        title: str,
        description: str,
        color: discord.Color,
        fields: list[tuple[str, str, bool]],
        log_label: str,
    ) -> None:
        embed = make_embed(
            user=member,
            title=title,
            description=description,
            color=color,
            fields=fields,
        )
        try:
            await reply_to_message(message, user=member, title=title, description=description, color=color, fields=fields)
        except discord.HTTPException:
            log.info("Could not reply with %s notice | guild=%s user=%s", log_label, member.guild.id, member.id)
            try:
                await message.channel.send(
                    content=member.mention,
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except discord.HTTPException:
                log.info("Could not send fallback %s notice | guild=%s user=%s", log_label, member.guild.id, member.id)

    async def _delete_message(self, message: discord.Message) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    async def _handle_language_issue(self, message: discord.Message, member: discord.Member, reason: str) -> bool:
        counts = await self._db_call(
            self.bot.db.add_moderation_warning,
            message.guild.id,
            member.id,
            default={"warning_count": 1, "timeout_count": 0},
            operation="add_moderation_warning",
        )
        warning_count = int(counts.get("warning_count", 1))
        timeout_count = int(counts.get("timeout_count", 0))
        color = WARNING
        warning_text = f"{warning_count}/3"
        action_text = "This warning stays active for 24 hours from your latest flagged message."

        if warning_count >= 3:
            counts = await self._db_call(
                self.bot.db.apply_moderation_timeout,
                message.guild.id,
                member.id,
                default={"warning_count": 0, "timeout_count": timeout_count + 1},
                operation="apply_moderation_timeout",
            )
            timeout_count = int(counts.get("timeout_count", timeout_count + 1))
            warning_text = "3/3"
            if timeout_count >= 3:
                try:
                    await member.ban(reason=LANGUAGE_BAN_REASON)
                    color = ERROR
                    action_text = "You reached 3 timeouts, so you were banned permanently."
                except discord.HTTPException:
                    color = ERROR
                    action_text = "Ban threshold reached, but I could not ban you because of permissions or role hierarchy."
            else:
                try:
                    await member.timeout(discord.utils.utcnow() + LANGUAGE_MUTE_DURATION, reason=LANGUAGE_BAN_REASON)
                    action_text = f"You reached 3 warnings, so you were timed out for {int(LANGUAGE_MUTE_DURATION.total_seconds() // 3600)} hours."
                except discord.HTTPException:
                    action_text = "Timeout threshold reached, but I could not timeout you because of permissions or role hierarchy."

        await self._reply_warning(
            message=message,
            member=member,
            title="⚠️ English Only Warning",
            description="Your message was removed because it was not clear English for this server.",
            color=color,
            fields=[
                ("Flagged Message", self._flagged_excerpt(message.content), False),
                ("Reason", reason[:120], False),
                ("Warnings", warning_text, True),
                ("Timeouts", str(timeout_count), True),
                ("Action", action_text, False),
            ],
            log_label="language moderation",
        )
        await self._delete_message(message)
        return True

    async def _handle_text_violation(
        self,
        *,
        message: discord.Message,
        member: discord.Member,
        kind: str,
        title: str,
        description: str,
        reason: str,
        moderation_reason: str,
    ) -> bool:
        counts = await self._db_call(
            self.bot.db.add_moderation_warning,
            message.guild.id,
            member.id,
            default={"warning_count": 1, "timeout_count": 0},
            operation=f"add_{kind}_warning",
        )
        color = WARNING
        warning_count = int(counts.get("warning_count", 1))
        timeout_count = int(counts.get("timeout_count", 0))
        warning_text = f"{warning_count}/3"
        action_text = "This warning stays active for 24 hours from your latest flagged message."
        if warning_count >= 3:
            counts = await self._db_call(
                self.bot.db.apply_moderation_timeout,
                message.guild.id,
                member.id,
                default={"warning_count": 0, "timeout_count": timeout_count + 1},
                operation=f"apply_{kind}_timeout",
            )
            timeout_count = int(counts.get("timeout_count", timeout_count + 1))
            warning_text = "3/3"
        if timeout_count >= 3:
            try:
                await member.ban(reason=moderation_reason)
                color = ERROR
                action_text = "You reached 3 timeouts, so you were banned permanently."
            except discord.HTTPException:
                color = ERROR
                action_text = "Ban threshold reached, but I could not ban you because of permissions or role hierarchy."
        elif warning_count >= 3:
            try:
                await member.timeout(discord.utils.utcnow() + LANGUAGE_MUTE_DURATION, reason=moderation_reason)
                action_text = f"You reached 3 warnings, so you were timed out for {int(LANGUAGE_MUTE_DURATION.total_seconds() // 3600)} hours."
            except discord.HTTPException:
                action_text = "Timeout threshold reached, but I could not timeout you because of permissions or role hierarchy."

        await self._db_call(
            self.bot.db.record_text_violation,
            message.guild.id,
            member.id,
            kind,
            message.content,
            default=None,
            operation=f"record_{kind}_event",
        )
        await self._reply_warning(
            message=message,
            member=member,
            title=title,
            description=description,
            color=color,
            fields=[
                ("Flagged Message", self._flagged_excerpt(message.content), False),
                ("Reason", reason[:120], False),
                ("Warnings", warning_text, True),
                ("Timeouts", str(timeout_count), True),
                ("Action", action_text, False),
            ],
            log_label=kind,
        )
        await self._delete_message(message)
        return True

    async def handle_message(self, message: discord.Message) -> bool:
        if message.author.bot or message.guild is None:
            return False
        if message.channel.id in EXCLUDED_CHANNEL_IDS:
            return False

        content = (message.content or "").strip()
        if not content:
            return False

        prefix = getattr(getattr(self.bot, "settings", None), "prefix", "-")
        if content.startswith(prefix):
            return False
        if self.bot.user is not None and content.startswith(self.bot.user.mention):
            return False
        if is_reporting_sentence(content):
            return False

        decision = await self.bot.ai.moderate_message(content)
        if decision.label == "allow":
            return False
        log.info(
            "AI moderation flagged message | guild=%s channel=%s user=%s label=%s reason=%s",
            message.guild.id,
            message.channel.id,
            message.author.id,
            decision.label,
            decision.reason,
        )

        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if member is None:
            return False

        if decision.label in {"non_english", "gibberish"}:
            return await self._handle_language_issue(message, member, decision.reason)
        if decision.label == "explicit":
            return await self._handle_text_violation(
                message=message,
                member=member,
                kind="ai_explicit_language",
                title="🚫 Explicit Language Warning",
                description="Your message was removed for vulgar, explicit, or inappropriate language.",
                reason=decision.reason,
                moderation_reason=EXPLICIT_BAN_REASON,
            )
        if decision.label == "abusive":
            return await self._handle_text_violation(
                message=message,
                member=member,
                kind="ai_hostile_behavior",
                title="🚫 Behavior Warning",
                description="Your message was removed because it looked insulting, hostile, or argumentative.",
                reason=decision.reason,
                moderation_reason=BEHAVIOR_BAN_REASON,
            )
        return False

    @tasks.loop(hours=1)
    async def warning_decay_worker(self) -> None:
        cleared = await self._db_call(
            self.bot.db.clear_expired_moderation_warnings,
            default=0,
            operation="clear_expired_moderation_warnings",
        )
        if cleared:
            log.info("Cleared %s expired moderation warnings.", cleared)

    @warning_decay_worker.before_loop
    async def before_warning_decay_worker(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LanguageEnforcer(bot))
