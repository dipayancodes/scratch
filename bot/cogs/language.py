from __future__ import annotations

import re
from datetime import timedelta

import discord
from discord.ext import commands

from bot.ui import ERROR, WARNING, make_embed

try:
    from wordfreq import zipf_frequency
except ImportError:
    zipf_frequency = None


EXCLUDED_CHANNEL_IDS = {
    1453299769916129350,
    1453299878665912450,
    1453299960387731477,
    1490777438215733358,
}
NON_ENGLISH_WORDS = {
    "acha",
    "achi",
    "ami",
    "achi",
    "bhai",
    "bhalo",
    "hai",
    "kal",
    "korbo",
    "kya",
    "mera",
    "nahi",
    "tera",
    "tum",
    "tumi",
}
WORD_PATTERN = re.compile(r"[^\W\d_]+", flags=re.UNICODE)
ENGLISH_THRESHOLD = 0.3
LANGUAGE_MUTE_DURATION = timedelta(hours=2)


def _extract_words(text: str) -> list[str]:
    return [word.lower() for word in WORD_PATTERN.findall(text)]


def english_score(text: str) -> float:
    words = _extract_words(text)
    if not words:
        return 1.0
    if zipf_frequency is None:
        english_like = sum(1 for word in words if word.isascii())
        return english_like / len(words)
    english_hits = sum(1 for word in words if zipf_frequency(word, "en") > 0.0)
    return english_hits / len(words)


def contains_non_english_words(text: str) -> bool:
    words = set(_extract_words(text))
    return any(word in NON_ENGLISH_WORDS for word in words)


def should_warn(text: str) -> bool:
    words = _extract_words(text)
    if len(words) <= 2:
        return False
    if contains_non_english_words(text):
        return True
    return english_score(text) < ENGLISH_THRESHOLD


class LanguageEnforcer(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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
        content = message.content.strip()
        if not content:
            return False
        prefix = getattr(getattr(self.bot, "settings", None), "prefix", "-")
        if content.startswith(prefix):
            return False
        if self.bot.user is not None and content.startswith(self.bot.user.mention):
            return False
        lowered = content.lower()
        if "http://" in lowered or "https://" in lowered or "www." in lowered:
            return False
        if message.mentions or message.role_mentions or message.channel_mentions:
            return False
        if not should_warn(content):
            return False

        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if member is None:
            return False

        counts = await self._db_call(
            self.bot.db.add_language_warning,
            message.guild.id,
            member.id,
            default={"warning_count": 1, "mute_count": 0},
            operation="add_language_warning",
        )
        warning_count = int(counts.get("warning_count", 1))
        mute_count = int(counts.get("mute_count", 0))
        action_text = "Warning issued."
        color = WARNING

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
                    await member.ban(reason="Using non-English language repeatedly")
                    action_text = "Banned for repeated non-English messages."
                    color = ERROR
                except discord.HTTPException:
                    action_text = "Ban threshold reached, but I could not ban the user."
                    color = ERROR
            else:
                try:
                    await member.timeout(
                        discord.utils.utcnow() + LANGUAGE_MUTE_DURATION,
                        reason="Using non-English language repeatedly",
                    )
                    action_text = "Timed out for 2 hours."
                except discord.HTTPException:
                    action_text = "Mute threshold reached, but I could not timeout the user."

        embed = make_embed(
            user=member,
            title="⚠️ English Only",
            description="Please communicate in English so everyone can understand.",
            color=color,
            fields=[
                ("Warnings", str(warning_count), True),
                ("Action", action_text, False),
            ],
        )
        try:
            await message.reply(embed=embed, mention_author=False)
        except discord.HTTPException:
            pass
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        return True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LanguageEnforcer(bot))
