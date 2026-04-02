from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandDoc:
    name: str
    category: str
    description: str
    usage: str
    example: str
    aliases: tuple[str, ...] = ()


COMMAND_DOCS: tuple[CommandDoc, ...] = (
    CommandDoc("help", "System", "Show all study bot commands.", "-help", "-help"),
    CommandDoc("command", "System", "Show detailed info for one command.", "-command <name>", "-command task", ("commands", "cmds")),
    CommandDoc("ping", "System", "Check bot latency.", "-ping", "-ping"),
    CommandDoc("about", "System", "Show bot information.", "-about", "-about"),
    CommandDoc("task", "Productivity", "Manage your study tasks.", "-task add/list/done/delete/clear", "-task add Revise Math"),
    CommandDoc("study", "Productivity", "Run focus and break timers.", "-study start/break/stop/status", "-study start 25"),
    CommandDoc("notes", "Knowledge", "Store and review notes.", "-notes add/view/list/delete", "-notes add Algebra | Quadratic formula"),
    CommandDoc("plan", "Productivity", "Set or generate daily study plans.", "-plan set/view/today/generate", "-plan set monday Physics, Chemistry"),
    CommandDoc("progress", "Tracking", "Log and review study hours.", "-progress add/stats/weekly/leaderboard", "-progress add math 2"),
    CommandDoc("streak", "Tracking", "Check or reset your study streak.", "-streak [reset]", "-streak"),
    CommandDoc("flash", "Knowledge", "Create and quiz flashcards.", "-flash add/quiz/list/delete", "-flash add What is inertia? | Resistance to change"),
    CommandDoc("quiz", "Knowledge", "Start subject quizzes and answer them.", "-quiz start/answer/score", "-quiz start physics"),
    CommandDoc("resource", "Knowledge", "Share and browse study resources.", "-resource add/list/delete", "-resource add math https://..."),
    CommandDoc("room", "Community", "Create and join voice study rooms.", "-room create/join/leave", "-room create Late Night Revision"),
    CommandDoc("goal", "Tracking", "Set and track a daily study goal.", "-goal set/status", "-goal set 4"),
    CommandDoc("remind", "Utility", "Create one-time or daily reminders.", "-remind me/daily/list", "-remind me 30m Start mock test"),
    CommandDoc("ask", "AI", "Ask the AI study assistant a question.", "-ask <question>", "-ask Explain Kirchhoff's law"),
    CommandDoc("summary", "AI", "Summarize study text.", "-summary <text>", "-summary Paste your paragraph here", ("summery",)),
    CommandDoc("analyze", "AI", "Analyze an attached text file.", "-analyze", "-analyze"),
    CommandDoc("exam", "Tracking", "Track exams and countdowns.", "-exam add/list/countdown", "-exam add chemistry 2026-04-20"),
    CommandDoc("leaderboard", "Gamification", "Show top students by study coins.", "-leaderboard", "-leaderboard"),
    CommandDoc("balance", "Gamification", "Show your study coin balance.", "-balance", "-balance"),
    CommandDoc("reward", "Gamification", "Reward a student with study coins.", "-reward <user> <coins>", "-reward @Alex 50"),
    CommandDoc("shop", "Gamification", "Browse or buy reward items.", "-shop [item]", "-shop focus_badge"),
    CommandDoc("calc", "Utility", "Calculate a math expression safely.", "-calc <expression>", "-calc (5+3)*2", ("calculator",)),
    CommandDoc("focus", "Moderation", "Turn personal focus mode on or off.", "-focus on/off", "-focus on"),
    CommandDoc("warn", "Moderation", "Warn a user.", "-warn <user> [reason]", "-warn @Alex Off-topic spam"),
    CommandDoc("mute", "Moderation", "Temporarily timeout a user.", "-mute <user> [minutes] [reason]", "-mute @Alex 10 Calm down"),
    CommandDoc("unmute", "Moderation", "Remove a timeout from a user.", "-unmute <user>", "-unmute @Alex"),
    CommandDoc("kick", "Moderation", "Kick a user from the server.", "-kick <user> [reason]", "-kick @Alex Repeated disruption"),
    CommandDoc("ban", "Moderation", "Ban a user from the server.", "-ban <user> [reason]", "-ban @Alex Severe disruption"),
    CommandDoc("clear", "Moderation", "Delete recent messages without removing the command message.", "-clear <number>", "-clear 10"),
    CommandDoc("analytics", "Tracking", "Show personal study analytics.", "-analytics", "-analytics"),
)


COMMAND_LOOKUP: dict[str, CommandDoc] = {}
for doc in COMMAND_DOCS:
    COMMAND_LOOKUP[doc.name] = doc
    for alias in doc.aliases:
        COMMAND_LOOKUP[alias] = doc
