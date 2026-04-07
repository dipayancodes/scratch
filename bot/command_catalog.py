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
    CommandDoc("help", "Utility", "Show all study bot commands.", "-help", "-help"),
    CommandDoc("command", "Utility", "Show detailed info for one command.", "-command <name>", "-command task", ("commands", "cmds")),
    CommandDoc("ping", "Utility", "Check bot latency.", "-ping", "-ping"),
    CommandDoc("about", "Utility", "Show bot information.", "-about", "-about"),
    CommandDoc("task", "Productivity", "Manage your study tasks.", "-task add/list/done/delete/clear", "-task add Revise Physics"),
    CommandDoc("study", "Productivity", "Run focus and break timers.", "-study start/break/stop/status", "-study start 25"),
    CommandDoc("plan", "Productivity", "Set, view, and generate smart study plans.", "-plan set/view/today/smart", "-plan smart Biology Finals 14"),
    CommandDoc("goal", "Productivity", "Set and track a daily study goal.", "-goal set/status", "-goal set 4"),
    CommandDoc("checkin", "Productivity", "Complete your daily check-in for rewards.", "-checkin", "-checkin"),
    CommandDoc("dashboard", "Productivity", "Show your full study dashboard.", "-dashboard", "-dashboard"),
    CommandDoc("notes", "Learning", "Store and review notes.", "-notes add/view/list/delete", "-notes add Algebra | Quadratic formula"),
    CommandDoc("flash", "Learning", "Create and review flashcards.", "-flash add/quiz/list/delete", "-flash add What is inertia? Resistance to change"),
    CommandDoc("quiz", "Learning", "Start subject quizzes and answer them.", "-quiz start/answer/score", "-quiz start physics"),
    CommandDoc("resources", "Learning", "Share and browse study resources.", "-resources add/list/delete", "-resources add math https://...", ("resource",)),
    CommandDoc("exam", "Learning", "Track exams and countdowns.", "-exam add/list/countdown", "-exam add chemistry 2026-04-20"),
    CommandDoc("revise", "Learning", "Suggest revision topics from your study history.", "-revise", "-revise"),
    CommandDoc("progress", "Tracking", "Log and review study hours.", "-progress add/stats/weekly/leaderboard", "-progress add mathematics 2"),
    CommandDoc("streak", "Tracking", "Check, reset, or protect your study streak.", "-streak [reset|protect]", "-streak protect"),
    CommandDoc("analytics", "Tracking", "Show personal study analytics.", "-analytics", "-analytics"),
    CommandDoc("vc", "Tracking", "Show voice-study tracking stats.", "-vc stats", "-vc stats"),
    CommandDoc("graph", "Tracking", "Show your recent study trend graph.", "-graph", "-graph"),
    CommandDoc("leaderboard", "Tracking", "Show top students by study coins.", "-leaderboard", "-leaderboard"),
    CommandDoc("balance", "Tracking", "Show your study coin balance.", "-balance", "-balance"),
    CommandDoc("achievements", "Tracking", "Show your unlocked achievements.", "-achievements", "-achievements"),
    CommandDoc("xp", "Tracking", "Show your XP progress.", "-xp", "-xp"),
    CommandDoc("level", "Tracking", "Show your current study level.", "-level", "-level"),
    CommandDoc("ask", "AI", "Ask the AI study assistant a question.", "-ask <question>", "-ask Explain Kirchhoff's law"),
    CommandDoc("summary", "AI", "Summarize study text.", "-summary <text>", "-summary Paste your paragraph here", ("summery",)),
    CommandDoc("analyze", "AI", "Analyze an attached text file.", "-analyze", "-analyze"),
    CommandDoc("suggest", "AI", "Get an AI suggestion for what to study next.", "-suggest", "-suggest"),
    CommandDoc("weakness", "AI", "Detect weaker subjects from your study history.", "-weakness", "-weakness"),
    CommandDoc("remind", "Utility", "Create one-time or daily reminders.", "-remind me/daily/list/delete", "-remind me 30m Start mock test"),
    CommandDoc("room", "Utility", "Create and manage private study rooms.", "-room create/join/leave/delete/lock/unlock", "-room create Late Night Revision"),
    CommandDoc("reward", "Utility", "Reward a student with study coins.", "-reward <user> <coins>", "-reward @Alex 50"),
    CommandDoc("shop", "Utility", "Browse or buy reward items.", "-shop [item]", "-shop focus_badge"),
    CommandDoc("inventory", "Utility", "Show the items you bought from the shop.", "-inventory", "-inventory"),
    CommandDoc("calc", "Utility", "Calculate a math expression safely.", "-calc <expression>", "-calc (5+3)*2", ("calculator",)),
    CommandDoc("focus", "Utility", "Turn personal focus mode on or off.", "-focus on/off", "-focus on"),
    CommandDoc("warn", "Utility", "Warn a user.", "-warn <user> [reason]", "-warn @Alex Off-topic spam"),
    CommandDoc("mute", "Utility", "Temporarily timeout a user.", "-mute <user> [minutes] [reason]", "-mute @Alex 10 Calm down"),
    CommandDoc("unmute", "Utility", "Remove a timeout from a user.", "-unmute <user>", "-unmute @Alex"),
    CommandDoc("kick", "Utility", "Kick a user from the server.", "-kick <user> [reason]", "-kick @Alex Repeated disruption"),
    CommandDoc("ban", "Utility", "Ban a user from the server.", "-ban <user> [reason]", "-ban @Alex Severe disruption"),
    CommandDoc("clear", "Utility", "Delete recent messages without removing the command message.", "-clear <number>", "-clear 10"),
)


COMMAND_LOOKUP: dict[str, CommandDoc] = {}
for doc in COMMAND_DOCS:
    COMMAND_LOOKUP[doc.name] = doc
    for alias in doc.aliases:
        COMMAND_LOOKUP[alias] = doc
