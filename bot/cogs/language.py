from __future__ import annotations

from datetime import timedelta
import logging
import re

import discord
from discord.ext import commands, tasks

from bot.ui import ERROR, WARNING, make_embed


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
TEXT_TIMEOUT_DURATION = timedelta(hours=1)
TEXT_WARNING_THRESHOLD = 3
TEXT_BAN_THRESHOLD = 5
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

    async def _delete_message(self, message: discord.Message) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    async def _send_dm_notice(
        self,
        *,
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
            await member.send(embed=embed)
        except discord.HTTPException:
            log.info("Could not DM %s notice | guild=%s user=%s", log_label, member.guild.id, member.id)

    async def _handle_language_issue(self, message: discord.Message, member: discord.Member, reason: str) -> bool:
        await self._delete_message(message)
        counts = await self._db_call(
            self.bot.db.add_language_warning,
            message.guild.id,
            member.id,
            default={"warning_count": 1, "mute_count": 0},
            operation="add_language_warning",
        )
        warning_count = int(counts.get("warning_count", 1))
        mute_count = int(counts.get("mute_count", 0))
        color = WARNING
        action_text = f"Warning {warning_count}/3. This warning clears after {LANGUAGE_WARNING_DECAY_HOURS} hours if you stay compliant."

        if warning_count > 3:
            counts = await self._db_call(
                self.bot.db.apply_language_mute,
                message.guild.id,
                member.id,
                default={"warning_count": 0, "mute_count": mute_count + 1},
                operation="apply_language_mute",
            )
            warning_count = int(counts.get("warning_count", 0))
            mute_count = int(counts.get("mute_count", mute_count + 1))
            if mute_count >= 3:
                try:
                    await member.ban(reason=LANGUAGE_BAN_REASON)
                    color = ERROR
                    action_text = "You were banned for repeated non-English or unclear English messages."
                except discord.HTTPException:
                    color = ERROR
                    action_text = "Ban threshold reached, but I could not ban you because of permissions or role hierarchy."
            else:
                try:
                    await member.timeout(discord.utils.utcnow() + LANGUAGE_MUTE_DURATION, reason=LANGUAGE_BAN_REASON)
                    action_text = f"You were muted for {int(LANGUAGE_MUTE_DURATION.total_seconds() // 3600)} hours."
                except discord.HTTPException:
                    action_text = "Mute threshold reached, but I could not mute you because of permissions or role hierarchy."

        await self._send_dm_notice(
            member=member,
            title="⚠️ English Only Warning",
            description="Your message was removed because it was not clear English for this server.",
            color=color,
            fields=[
                ("Reason", reason[:120], False),
                ("Warnings", f"{warning_count}/3", True),
                ("Mute Count", str(mute_count), True),
                ("Action", action_text, False),
            ],
            log_label="language moderation",
        )
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
        await self._delete_message(message)
        recent_count = await self._db_call(
            self.bot.db.record_text_violation,
            message.guild.id,
            member.id,
            kind,
            message.content,
            default=1,
            operation=f"record_{kind}_violation",
        )
        color = WARNING
        action_text = f"Warning {recent_count}/{TEXT_WARNING_THRESHOLD}. Continued violations will trigger automatic timeout."
        if recent_count >= TEXT_BAN_THRESHOLD:
            try:
                await member.ban(reason=moderation_reason)
                color = ERROR
                action_text = "You were banned because this behavior kept repeating."
            except discord.HTTPException:
                color = ERROR
                action_text = "Ban threshold reached, but I could not ban you because of permissions or role hierarchy."
        elif recent_count >= TEXT_WARNING_THRESHOLD:
            try:
                await member.timeout(discord.utils.utcnow() + TEXT_TIMEOUT_DURATION, reason=moderation_reason)
                action_text = f"You were timed out for {int(TEXT_TIMEOUT_DURATION.total_seconds() // 3600)} hour because this kept repeating."
            except discord.HTTPException:
                action_text = "Timeout threshold reached, but I could not timeout you because of permissions or role hierarchy."

        await self._send_dm_notice(
            member=member,
            title=title,
            description=description,
            color=color,
            fields=[
                ("Reason", reason[:120], False),
                ("Recent Violations", str(recent_count), True),
                ("Action", action_text, False),
            ],
            log_label=kind,
        )
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
            self.bot.db.clear_expired_language_warnings,
            default=0,
            operation="clear_expired_language_warnings",
        )
        if cleared:
            log.info("Cleared %s expired language warnings.", cleared)

    @warning_decay_worker.before_loop
    async def before_warning_decay_worker(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LanguageEnforcer(bot))
