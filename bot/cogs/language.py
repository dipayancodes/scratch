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

        decision = await self.bot.ai.classify_language(content)
        if decision is None:
            log.warning(
                "Skipped language moderation because Groq classification was unavailable | guild=%s channel=%s user=%s message=%s",
                message.guild.id,
                message.channel.id,
                message.author.id,
                message.id,
            )
            return False
        if decision == "english":
            return False

        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if member is None:
            return False

        try:
            await message.delete()
        except discord.HTTPException:
            pass

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
        action_text = f"Warning {warning_count}/3. This warning will clear after {LANGUAGE_WARNING_DECAY_HOURS} hours if you stay compliant."

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
                    action_text = "You have been banned for repeated non-English messages in English-only channels."
                    log.warning(
                        "Language moderation ban | guild=%s user=%s mute_count=%s message=%s",
                        message.guild.id,
                        member.id,
                        mute_count,
                        message.id,
                    )
                except discord.HTTPException:
                    color = ERROR
                    action_text = "Ban threshold reached, but I could not ban you because of missing permissions or role hierarchy."
                    log.warning(
                        "Language moderation ban failed | guild=%s user=%s mute_count=%s message=%s",
                        message.guild.id,
                        member.id,
                        mute_count,
                        message.id,
                    )
            else:
                try:
                    await member.timeout(discord.utils.utcnow() + LANGUAGE_MUTE_DURATION, reason=LANGUAGE_BAN_REASON)
                    action_text = f"You have been muted for {int(LANGUAGE_MUTE_DURATION.total_seconds() // 3600)} hours."
                    log.warning(
                        "Language moderation mute | guild=%s user=%s mute_count=%s message=%s",
                        message.guild.id,
                        member.id,
                        mute_count,
                        message.id,
                    )
                except discord.HTTPException:
                    action_text = "Mute threshold reached, but I could not mute you because of missing permissions or role hierarchy."
                    log.warning(
                        "Language moderation mute failed | guild=%s user=%s mute_count=%s message=%s",
                        message.guild.id,
                        member.id,
                        mute_count,
                        message.id,
                    )
        else:
            log.info(
                "Language moderation warning | guild=%s user=%s warning_count=%s message=%s",
                message.guild.id,
                member.id,
                warning_count,
                message.id,
            )

        embed = make_embed(
            user=member,
            title="⚠️ English Only",
            description="Your message was removed because English is required in this channel.",
            color=color,
            fields=[
                ("Warnings", f"{warning_count}/3", True),
                ("Mute Count", str(mute_count), True),
                ("Action", action_text, False),
            ],
        )
        try:
            await member.send(embed=embed)
        except discord.HTTPException:
            log.info("Could not DM language moderation notice | guild=%s user=%s", message.guild.id, member.id)
        return True

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
