from __future__ import annotations

import re
from datetime import timedelta

import discord
from discord.ext import commands

from bot.ui import ERROR, WARNING, make_embed


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
    "bhalo",
    "bhai",
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
QUOTE_PATTERN = re.compile(r'"([^"]+)"|\'([^\']+)\'')
WORD_PATTERN = re.compile(r"[a-z]+")
REPORTING_PATTERN = re.compile(r"\b\w+\s+(said|told|mentioned|wrote|replied|asked)\b", re.IGNORECASE)
SPEAKER_PATTERN = re.compile(r"^\s*\w+\s*:", re.IGNORECASE)
NORMALIZE_MAP = str.maketrans(
    {
        "@": "a",
        "$": "s",
        "0": "o",
        "1": "i",
        "!": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "+": "t",
    }
)
LANGUAGE_MUTE_DURATION = timedelta(hours=2)


def normalize_text(text: str) -> str:
    normalized = (text or "").lower().translate(NORMALIZE_MAP)
    return re.sub(r"[^a-z\"':\s]", " ", normalized)


def extract_quotes(text: str) -> list[str]:
    if not text:
        return []
    return [match.group(1) or match.group(2) for match in QUOTE_PATTERN.finditer(text)]


def extract_words(text: str) -> list[str]:
    return WORD_PATTERN.findall(normalize_text(text))


def contains_non_english_phrase(words: list[str]) -> bool:
    if not words:
        return False
    if len(words) == 1 and words[0] in NON_ENGLISH_WORDS:
        return True
    streak = 0
    for word in words:
        if word in NON_ENGLISH_WORDS:
            streak += 1
            if streak >= 2:
                return True
        else:
            streak = 0
    for index in range(len(words) - 2):
        if words[index] in NON_ENGLISH_WORDS and words[index + 2] in NON_ENGLISH_WORDS:
            return True
    return False


def is_reporting_sentence(text: str) -> bool:
    if not text:
        return False
    return bool(REPORTING_PATTERN.search(text) or SPEAKER_PATTERN.search(text))


def should_warn(text: str) -> bool:
    if not text or is_reporting_sentence(text):
        return False
    words = extract_words(text)
    if contains_non_english_phrase(words):
        return True
    for quote in extract_quotes(text):
        if contains_non_english_phrase(extract_words(quote)):
            return True
    return False


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

        content = (message.content or "").strip()
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
        if is_reporting_sentence(content):
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
            await message.reply(content=member.mention, embed=embed, mention_author=False)
        except discord.HTTPException:
            pass
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        return True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LanguageEnforcer(bot))
