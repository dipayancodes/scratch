from __future__ import annotations

from discord import app_commands
import discord


COMMON_SUBJECTS = [
    "mathematics",
    "physics",
    "chemistry",
    "biology",
    "computer science",
    "english",
    "social studies",
    "literature",
    "history",
    "geography",
    "civics",
    "economics",
    "commerce",
    "business studies",
    "accounting",
    "political science",
    "psychology",
    "sociology",
    "philosophy",
    "statistics",
    "environmental science",
    "earth science",
    "geology",
    "general science",
    "art",
    "drama",
    "music",
    "physical education",
    "health science",
    "home science",
    "engineering",
    "mechanical engineering",
    "electrical engineering",
    "civil engineering",
    "law",
    "medicine",
    "nursing",
    "astronomy",
    "agriculture",
    "design",
    "media studies",
    "foreign languages",
    "journalism",
    "robotics",
    "marketing",
    "entrepreneurship",
    "computer applications",
    "data science",
    "information technology",
    "others",
]

DAYS_OF_WEEK = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def clean_subject(subject: str, custom_subject: str = "") -> str:
    normalized = (subject or "").strip().lower()
    custom = (custom_subject or "").strip()
    if normalized == "others":
        return custom
    return subject.strip()


def is_custom_subject(subject: str) -> bool:
    return subject.strip().lower() not in COMMON_SUBJECTS and bool(subject.strip())


def finalize_subject(subject: str, custom_subject: str = "") -> str:
    resolved = clean_subject(subject, custom_subject).strip()
    return resolved or subject.strip()


async def subject_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current_lower = current.lower().strip()
    custom_subjects = []
    db = getattr(interaction.client, "db", None)
    if db is not None:
        custom_subjects = db.get_user_subjects(interaction.guild_id or 0, interaction.user.id)
    pool = []
    seen = set()
    for subject in [*COMMON_SUBJECTS, *custom_subjects]:
        key = subject.lower()
        if key in seen:
            continue
        seen.add(key)
        if not current_lower or current_lower in key:
            pool.append(subject)
    pool.sort()
    return [app_commands.Choice(name=subject.title(), value=subject) for subject in pool[:25]]
