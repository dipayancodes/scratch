from __future__ import annotations

from datetime import UTC, datetime, timedelta

from discord import app_commands
from discord.ext import commands

from bot.subjects import DAYS_OF_WEEK, finalize_subject, is_custom_subject


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
    today = datetime.now(UTC).date()
    delta = (day_index - today.weekday()) % 7
    target = today + timedelta(days=delta)
    return target.isoformat()


def resolve_subject(ctx: commands.Context, subject: str, custom_subject: str = "") -> str:
    resolved = finalize_subject(subject, custom_subject).strip()
    if subject.lower() == "others" and not custom_subject.strip():
        raise ValueError("Custom subject is required when you choose others.")
    if is_custom_subject(resolved):
        ctx.bot.db.add_custom_subject(ctx.guild.id, ctx.author.id, resolved)
    return resolved


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


def progress_bar(current: float, total: float, *, length: int = 10) -> str:
    if total <= 0:
        filled = 0
    else:
        filled = max(0, min(length, int(round((current / total) * length))))
    return "█" * filled + "░" * (length - filled)
