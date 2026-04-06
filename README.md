# Study OS Discord Bot

Study OS is a Discord productivity assistant for study-focused servers. It uses MongoDB for persistence, reply-based embeds for all command output, and a modular `discord.py` architecture.

## Core behavior

- Prefix: `-`
- Every command replies to the triggering message
- Every response uses an embed
- Storage uses MongoDB
- AI commands support Groq when configured and fallback behavior when not configured

## Main systems

- Tasks, planner, and Pomodoro study timer
- Notes, flashcards, quizzes, and resources
- Progress logs, streaks, goals, and analytics
- Reminders, exams, and calculator utility
- Group study rooms and voice study tracking
- Coins, leaderboard, rewards, and shop
- Focus mode and moderation tools

## Commands

- `-help`
- `-command <name>`
- `-ping`
- `-about`
- `-task add/list/done/delete/clear`
- `-study start/break/stop/status`
- `-notes add/view/list/delete`
- `-plan set/view/today/generate`
- `-progress add/stats/weekly/leaderboard`
- `-streak`
- `-streak reset`
- `-flash add/quiz/list/delete`
- `-quiz start/answer/score`
- `-resource add/list/delete`
- `-room create/join/leave`
- `-goal set/status`
- `-remind me/daily/list`
- `-ask`
- `-summary`
- `-analyze`
- `-exam add/list/countdown`
- `-leaderboard`
- `-balance`
- `-reward`
- `-shop`
- `-calc`
- `-focus on/off`
- `-warn`
- `-mute`
- `-unmute`
- `-kick`
- `-ban`
- `-clear`
- `-analytics`

## Setup

1. Start MongoDB locally or provide a hosted URI.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env`
4. Set `DISCORD_TOKEN`
5. Set `MONGODB_URI` if you are not using local MongoDB
6. Optionally set `GROQ_API_KEY`
7. Run:

```powershell
python main.py
```

## Notes

- Prefix commands require the `MESSAGE CONTENT INTENT` to be enabled in the Discord Developer Portal.
- Voice tracking requires the bot to have permission to view and connect to voice channels.
- AI commands work without Groq, but answers will be simpler.
