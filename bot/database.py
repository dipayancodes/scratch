from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument


def utc_now() -> datetime:
    return datetime.now(UTC)


class Database:
    def __init__(self, uri: str, database_name: str) -> None:
        self.client = MongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
        self.client.admin.command("ping")
        self.db = self.client[database_name]
        self._initialize()

    def _initialize(self) -> None:
        self.db.tasks.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("status", ASCENDING)])
        self.db.notes.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("title_key", ASCENDING)], unique=True)
        self.db.plans.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("day_key", ASCENDING)], unique=True)
        self.db.progress_logs.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("logged_at", DESCENDING)])
        self.db.study_days.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("day", ASCENDING)], unique=True)
        self.db.user_stats.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        self.db.flashcards.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("id", DESCENDING)])
        self.db.resources.create_index([("guild_id", ASCENDING), ("subject_key", ASCENDING), ("id", DESCENDING)])
        self.db.reminders.create_index([("remind_at", ASCENDING)])
        self.db.exams.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("exam_date", ASCENDING)])
        self.db.warnings.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("id", DESCENDING)])
        self.db.study_rooms.create_index([("guild_id", ASCENDING), ("name_key", ASCENDING), ("active", ASCENDING)])
        self.db.voice_sessions.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING)], unique=True)

    def _next_id(self, name: str) -> int:
        counter = self.db.counters.find_one_and_update(
            {"_id": name},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(counter["value"])

    def ensure_user_stats(self, guild_id: int, user_id: int) -> None:
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {
                "$setOnInsert": {
                    "coins": 0,
                    "daily_goal_hours": 2.0,
                    "focus_mode": False,
                    "streak": 0,
                    "longest_streak": 0,
                    "total_focus_minutes": 0,
                    "total_voice_minutes": 0,
                    "last_study_day": None,
                    "distraction_warnings": 0,
                }
            },
            upsert=True,
        )

    def add_task(self, guild_id: int, user_id: int, content: str) -> int:
        task_id = self._next_id("tasks")
        self.db.tasks.insert_one(
            {
                "id": task_id,
                "guild_id": guild_id,
                "user_id": user_id,
                "content": content,
                "status": "pending",
                "created_at": utc_now(),
                "completed_at": None,
            }
        )
        return task_id

    def list_tasks(self, guild_id: int, user_id: int) -> list[dict]:
        return list(
            self.db.tasks.find(
                {"guild_id": guild_id, "user_id": user_id, "status": "pending"},
                {"_id": 0},
            ).sort("id", ASCENDING)
        )

    def complete_task(self, guild_id: int, user_id: int, task_id: int) -> bool:
        result = self.db.tasks.update_one(
            {"guild_id": guild_id, "user_id": user_id, "id": task_id, "status": "pending"},
            {"$set": {"status": "done", "completed_at": utc_now()}},
        )
        return result.modified_count > 0

    def delete_task(self, guild_id: int, user_id: int, task_id: int) -> bool:
        result = self.db.tasks.delete_one({"guild_id": guild_id, "user_id": user_id, "id": task_id})
        return result.deleted_count > 0

    def clear_tasks(self, guild_id: int, user_id: int) -> int:
        result = self.db.tasks.delete_many({"guild_id": guild_id, "user_id": user_id})
        return int(result.deleted_count)

    def save_note(self, guild_id: int, user_id: int, title: str, content: str) -> None:
        self.db.notes.update_one(
            {"guild_id": guild_id, "user_id": user_id, "title_key": title.lower()},
            {
                "$set": {
                    "title": title,
                    "title_key": title.lower(),
                    "content": content,
                    "created_at": utc_now(),
                }
            },
            upsert=True,
        )

    def get_note(self, guild_id: int, user_id: int, title: str) -> dict | None:
        return self.db.notes.find_one(
            {"guild_id": guild_id, "user_id": user_id, "title_key": title.lower()},
            {"_id": 0},
        )

    def list_notes(self, guild_id: int, user_id: int) -> list[dict]:
        return list(
            self.db.notes.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0, "title": 1, "created_at": 1}).sort(
                "title", ASCENDING
            )
        )

    def delete_note(self, guild_id: int, user_id: int, title: str) -> bool:
        result = self.db.notes.delete_one({"guild_id": guild_id, "user_id": user_id, "title_key": title.lower()})
        return result.deleted_count > 0

    def set_plan(self, guild_id: int, user_id: int, day: str, tasks: str) -> None:
        self.db.plans.update_one(
            {"guild_id": guild_id, "user_id": user_id, "day_key": day.lower()},
            {"$set": {"day": day, "day_key": day.lower(), "tasks": tasks, "updated_at": utc_now()}},
            upsert=True,
        )

    def get_plan(self, guild_id: int, user_id: int, day: str) -> dict | None:
        return self.db.plans.find_one(
            {"guild_id": guild_id, "user_id": user_id, "day_key": day.lower()},
            {"_id": 0},
        )

    def add_progress(self, guild_id: int, user_id: int, subject: str, hours: float) -> None:
        self.db.progress_logs.insert_one(
            {
                "id": self._next_id("progress_logs"),
                "guild_id": guild_id,
                "user_id": user_id,
                "subject": subject,
                "subject_key": subject.lower(),
                "hours": hours,
                "logged_at": utc_now(),
            }
        )
        self.record_study_activity(guild_id, user_id)
        self.add_coins(guild_id, user_id, int(hours * 20))

    def get_progress_totals(self, guild_id: int, user_id: int) -> dict:
        rows = list(
            self.db.progress_logs.aggregate(
                [
                    {"$match": {"guild_id": guild_id, "user_id": user_id}},
                    {"$group": {"_id": None, "logged_hours": {"$sum": "$hours"}, "entries": {"$sum": 1}}},
                ]
            )
        )
        if not rows:
            return {"logged_hours": 0.0, "entries": 0}
        row = rows[0]
        return {"logged_hours": round(float(row["logged_hours"]), 2), "entries": int(row["entries"])}

    def get_weekly_progress(self, guild_id: int, user_id: int) -> list[dict]:
        since = utc_now() - timedelta(days=7)
        rows = list(
            self.db.progress_logs.aggregate(
                [
                    {"$match": {"guild_id": guild_id, "user_id": user_id, "logged_at": {"$gte": since}}},
                    {"$group": {"_id": "$subject", "hours": {"$sum": "$hours"}}},
                    {"$sort": {"hours": -1}},
                ]
            )
        )
        return [{"subject": row["_id"], "hours": round(float(row["hours"]), 2)} for row in rows]

    def progress_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        rows = list(
            self.db.progress_logs.aggregate(
                [
                    {"$match": {"guild_id": guild_id}},
                    {"$group": {"_id": "$user_id", "total_hours": {"$sum": "$hours"}}},
                    {"$sort": {"total_hours": -1}},
                    {"$limit": limit},
                ]
            )
        )
        return [{"user_id": row["_id"], "total_hours": round(float(row["total_hours"]), 2)} for row in rows]

    def record_study_session(self, guild_id: int, user_id: int, session_type: str, minutes: int, subject: str | None = None) -> None:
        now = utc_now()
        self.db.study_sessions.insert_one(
            {
                "id": self._next_id("study_sessions"),
                "guild_id": guild_id,
                "user_id": user_id,
                "session_type": session_type,
                "subject": subject,
                "minutes": minutes,
                "completed": True,
                "started_at": now,
                "ended_at": now,
            }
        )
        self.ensure_user_stats(guild_id, user_id)
        if session_type == "focus":
            self.db.user_stats.update_one(
                {"guild_id": guild_id, "user_id": user_id},
                {"$inc": {"total_focus_minutes": minutes}},
            )
            self.add_coins(guild_id, user_id, max(5, minutes // 5))
        self.record_study_activity(guild_id, user_id)

    def record_study_activity(self, guild_id: int, user_id: int) -> None:
        today = utc_now().date().isoformat()
        self.ensure_user_stats(guild_id, user_id)
        self.db.study_days.update_one(
            {"guild_id": guild_id, "user_id": user_id, "day": today},
            {"$setOnInsert": {"day": today}},
            upsert=True,
        )
        self.refresh_streak(guild_id, user_id)

    def refresh_streak(self, guild_id: int, user_id: int) -> dict:
        self.ensure_user_stats(guild_id, user_id)
        rows = list(
            self.db.study_days.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0, "day": 1}).sort("day", DESCENDING)
        )
        day_set = {datetime.fromisoformat(row["day"]).date() for row in rows}
        today = utc_now().date()
        streak = 0
        cursor_day = today if today in day_set else today - timedelta(days=1)
        if cursor_day in day_set:
            while cursor_day in day_set:
                streak += 1
                cursor_day -= timedelta(days=1)
        stats = self.get_user_stats(guild_id, user_id)
        longest = max(streak, int(stats["longest_streak"]))
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"streak": streak, "longest_streak": longest, "last_study_day": today.isoformat()}},
        )
        return self.get_user_stats(guild_id, user_id)

    def reset_streak(self, guild_id: int, user_id: int) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"streak": 0}})

    def get_user_stats(self, guild_id: int, user_id: int) -> dict:
        self.ensure_user_stats(guild_id, user_id)
        return self.db.user_stats.find_one({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}) or {}

    def set_goal(self, guild_id: int, user_id: int, hours_per_day: float) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"daily_goal_hours": hours_per_day}},
        )

    def add_flashcard(self, guild_id: int, user_id: int, question: str, answer: str, subject: str = "general") -> int:
        flashcard_id = self._next_id("flashcards")
        self.db.flashcards.insert_one(
            {
                "id": flashcard_id,
                "guild_id": guild_id,
                "user_id": user_id,
                "subject": subject,
                "subject_key": subject.lower(),
                "question": question,
                "answer": answer,
                "created_at": utc_now(),
            }
        )
        return flashcard_id

    def list_flashcards(self, guild_id: int, user_id: int) -> list[dict]:
        return list(
            self.db.flashcards.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0, "id": 1, "subject": 1, "question": 1}).sort(
                "id", DESCENDING
            )
        )

    def get_flashcards(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self.db.flashcards.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}).sort("id", ASCENDING))

    def delete_flashcard(self, guild_id: int, user_id: int, flashcard_id: int) -> bool:
        result = self.db.flashcards.delete_one({"guild_id": guild_id, "user_id": user_id, "id": flashcard_id})
        return result.deleted_count > 0

    def add_resource(self, guild_id: int, user_id: int, subject: str, link: str, description: str) -> int:
        resource_id = self._next_id("resources")
        self.db.resources.insert_one(
            {
                "id": resource_id,
                "guild_id": guild_id,
                "user_id": user_id,
                "subject": subject,
                "subject_key": subject.lower(),
                "link": link,
                "description": description,
                "created_at": utc_now(),
            }
        )
        return resource_id

    def list_resources(self, guild_id: int, subject: str) -> list[dict]:
        return list(
            self.db.resources.find({"guild_id": guild_id, "subject_key": subject.lower()}, {"_id": 0}).sort("id", DESCENDING)
        )

    def delete_resource(self, guild_id: int, resource_id: int) -> bool:
        result = self.db.resources.delete_one({"guild_id": guild_id, "id": resource_id})
        return result.deleted_count > 0

    def add_reminder(
        self,
        guild_id: int | None,
        channel_id: int,
        user_id: int,
        message: str,
        remind_at: datetime,
        source_message_id: int,
        recurring: str = "once",
        daily_time: str | None = None,
    ) -> int:
        reminder_id = self._next_id("reminders")
        self.db.reminders.insert_one(
            {
                "id": reminder_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "user_id": user_id,
                "message": message,
                "remind_at": remind_at,
                "source_message_id": source_message_id,
                "recurring": recurring,
                "daily_time": daily_time,
            }
        )
        return reminder_id

    def due_reminders(self, now: datetime) -> list[dict]:
        return list(self.db.reminders.find({"remind_at": {"$lte": now}}, {"_id": 0}).sort("remind_at", ASCENDING))

    def list_reminders(self, guild_id: int, user_id: int) -> list[dict]:
        return list(
            self.db.reminders.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}).sort("remind_at", ASCENDING)
        )

    def delete_reminder(self, reminder_id: int) -> None:
        self.db.reminders.delete_one({"id": reminder_id})

    def reschedule_daily_reminder(self, reminder_id: int, next_run: datetime) -> None:
        self.db.reminders.update_one({"id": reminder_id}, {"$set": {"remind_at": next_run}})

    def add_exam(self, guild_id: int, user_id: int, subject: str, exam_date: str) -> int:
        exam_id = self._next_id("exams")
        self.db.exams.insert_one(
            {
                "id": exam_id,
                "guild_id": guild_id,
                "user_id": user_id,
                "subject": subject,
                "exam_date": exam_date,
            }
        )
        return exam_id

    def list_exams(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self.db.exams.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}).sort("exam_date", ASCENDING))

    def add_coins(self, guild_id: int, user_id: int, amount: int) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"coins": amount}})

    def spend_coins(self, guild_id: int, user_id: int, amount: int) -> bool:
        self.ensure_user_stats(guild_id, user_id)
        stats = self.get_user_stats(guild_id, user_id)
        if int(stats["coins"]) < amount:
            return False
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"coins": -amount}})
        return True

    def coin_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        return list(
            self.db.user_stats.find({"guild_id": guild_id}, {"_id": 0, "user_id": 1, "coins": 1, "total_focus_minutes": 1})
            .sort([("coins", DESCENDING), ("total_focus_minutes", DESCENDING)])
            .limit(limit)
        )

    def set_focus_mode(self, guild_id: int, user_id: int, enabled: bool) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"focus_mode": enabled}})

    def add_distraction_warning(self, guild_id: int, user_id: int) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"distraction_warnings": 1}})

    def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        warning_id = self._next_id("warnings")
        self.db.warnings.insert_one(
            {
                "id": warning_id,
                "guild_id": guild_id,
                "user_id": user_id,
                "moderator_id": moderator_id,
                "reason": reason,
                "created_at": utc_now(),
            }
        )
        return warning_id

    def get_warnings(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self.db.warnings.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}).sort("id", DESCENDING))

    def create_room(self, guild_id: int, name: str, channel_id: int, created_by: int) -> int:
        room_id = self._next_id("study_rooms")
        self.db.study_rooms.insert_one(
            {
                "id": room_id,
                "guild_id": guild_id,
                "name": name,
                "name_key": name.lower(),
                "channel_id": channel_id,
                "created_by": created_by,
                "active": True,
                "created_at": utc_now(),
            }
        )
        return room_id

    def get_room_by_name(self, guild_id: int, name: str) -> dict | None:
        return self.db.study_rooms.find_one(
            {"guild_id": guild_id, "name_key": name.lower(), "active": True},
            {"_id": 0},
            sort=[("id", DESCENDING)],
        )

    def deactivate_room(self, channel_id: int) -> None:
        self.db.study_rooms.update_one({"channel_id": channel_id}, {"$set": {"active": False}})

    def start_voice_session(self, guild_id: int, user_id: int, channel_id: int) -> None:
        self.db.voice_sessions.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"channel_id": channel_id, "started_at": utc_now()}},
            upsert=True,
        )

    def stop_voice_session(self, guild_id: int, user_id: int) -> int:
        session = self.db.voice_sessions.find_one_and_delete({"guild_id": guild_id, "user_id": user_id}, {"_id": 0})
        if session is None:
            return 0
        minutes = max(0, int((utc_now() - session["started_at"]).total_seconds() // 60))
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"total_voice_minutes": minutes}},
        )
        if minutes > 0:
            self.record_study_activity(guild_id, user_id)
            self.add_coins(guild_id, user_id, max(3, minutes // 10))
        return minutes

    def analytics_summary(self, guild_id: int, user_id: int) -> dict[str, object]:
        stats = self.get_user_stats(guild_id, user_id)
        totals = self.get_progress_totals(guild_id, user_id)
        week = self.get_weekly_progress(guild_id, user_id)
        tasks = len(self.list_tasks(guild_id, user_id))
        exams = self.list_exams(guild_id, user_id)
        today = utc_now().date()
        rows = list(
            self.db.progress_logs.aggregate(
                [
                    {"$match": {"guild_id": guild_id, "user_id": user_id}},
                    {
                        "$addFields": {
                            "logged_day": {
                                "$dateToString": {"format": "%Y-%m-%d", "date": "$logged_at", "timezone": "UTC"}
                            }
                        }
                    },
                    {"$match": {"logged_day": today.isoformat()}},
                    {"$group": {"_id": None, "hours": {"$sum": "$hours"}}},
                ]
            )
        )
        today_hours = round(float(rows[0]["hours"]), 2) if rows else 0.0
        return {
            "coins": int(stats["coins"]),
            "streak": int(stats["streak"]),
            "longest_streak": int(stats["longest_streak"]),
            "daily_goal_hours": float(stats["daily_goal_hours"]),
            "today_hours": today_hours,
            "total_logged_hours": float(totals["logged_hours"]),
            "focus_minutes": int(stats["total_focus_minutes"]),
            "voice_minutes": int(stats["total_voice_minutes"]),
            "pending_tasks": tasks,
            "top_subjects": week[:3],
            "upcoming_exams": exams[:3],
        }
