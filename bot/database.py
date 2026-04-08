from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument


def utc_now() -> datetime:
    return datetime.now(UTC)


LANGUAGE_WARNING_DECAY = timedelta(hours=24)


class Database:
    def __init__(self, uri: str, database_name: str) -> None:
        self.client = MongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
        self.client.admin.command("ping")
        self.db = self.client[database_name]
        self._initialize()

    def _ensure_counter_floor(self, name: str, floor: int) -> None:
        self.db.counters.update_one({"_id": name}, {"$max": {"value": int(floor)}}, upsert=True)

    def _backfill_numeric_ids(self, collection_name: str, counter_name: str | None = None) -> None:
        counter_key = counter_name or collection_name
        collection = self.db[collection_name]

        highest_row = collection.find_one({"id": {"$type": "number"}}, {"_id": 0, "id": 1}, sort=[("id", DESCENDING)])
        if highest_row and highest_row.get("id") is not None:
            self._ensure_counter_floor(counter_key, int(highest_row["id"]))

        for row in collection.find({}, {"_id": 1, "id": 1}).sort("_id", ASCENDING):
            raw_id = row.get("id")
            if isinstance(raw_id, bool):
                raw_id = None
            if isinstance(raw_id, int):
                continue
            if isinstance(raw_id, float) and raw_id.is_integer():
                normalized = int(raw_id)
                collection.update_one({"_id": row["_id"]}, {"$set": {"id": normalized}})
                self._ensure_counter_floor(counter_key, normalized)
                continue
            if isinstance(raw_id, str):
                trimmed = raw_id.strip()
                if trimmed.isdigit():
                    normalized = int(trimmed)
                    collection.update_one({"_id": row["_id"]}, {"$set": {"id": normalized}})
                    self._ensure_counter_floor(counter_key, normalized)
                    continue
            collection.update_one({"_id": row["_id"]}, {"$set": {"id": self._next_id(counter_key)}})

    def _next_weekday_date(self, day_name: str) -> str:
        weekday_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        normalized = day_name.strip().lower()
        today = utc_now().date()
        if normalized not in weekday_names:
            return today.isoformat()
        delta = (weekday_names.index(normalized) - today.weekday()) % 7
        return (today + timedelta(days=delta)).isoformat()

    def _backfill_plan_dates(self) -> None:
        for row in self.db.plans.find({}, {"_id": 1, "guild_id": 1, "user_id": 1, "day": 1, "target_date": 1}).sort("_id", ASCENDING):
            target_date = row.get("target_date")
            if isinstance(target_date, str) and target_date.strip():
                continue
            day_name = str(row.get("day", "")).strip().lower()
            candidate = datetime.fromisoformat(self._next_weekday_date(day_name)).date()
            while self.db.plans.find_one(
                {
                    "_id": {"$ne": row["_id"]},
                    "guild_id": row.get("guild_id"),
                    "user_id": row.get("user_id"),
                    "target_date": candidate.isoformat(),
                },
                {"_id": 1},
            ):
                candidate += timedelta(days=1)
            update_fields = {"target_date": candidate.isoformat()}
            if day_name:
                update_fields["day_key"] = day_name
            self.db.plans.update_one({"_id": row["_id"]}, {"$set": update_fields})

    def _initialize(self) -> None:
        for collection_name, index_name in (
            ("notes", "guild_id_1_user_id_1_title_key_1"),
            ("plans", "guild_id_1_user_id_1_day_key_1"),
            ("reports", "guild_id_1_channel_id_1"),
        ):
            try:
                self.db[collection_name].drop_index(index_name)
            except Exception:
                pass
        for collection_name in (
            "notes",
            "flashcards",
            "resources",
            "reminders",
            "exams",
            "warnings",
            "study_rooms",
            "reports",
            "progress_logs",
            "study_sessions",
            "tasks",
        ):
            self._backfill_numeric_ids(collection_name)
        self._backfill_plan_dates()
        self.db.tasks.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("status", ASCENDING)])
        self.db.users.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        self.db.notes.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("id", ASCENDING)], unique=True)
        self.db.plans.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("target_date", ASCENDING)], unique=True)
        self.db.progress.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("logged_at", DESCENDING)])
        self.db.progress_logs.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("logged_at", DESCENDING)])
        self.db.streaks.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("day", ASCENDING)], unique=True)
        self.db.study_days.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("day", ASCENDING)], unique=True)
        self.db.coins.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        self.db.achievements.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("key", ASCENDING)], unique=True)
        self.db.user_stats.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        self.db.flashcards.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("id", DESCENDING)])
        self.db.resources.create_index([("guild_id", ASCENDING), ("subject_key", ASCENDING), ("id", DESCENDING)])
        self.db.reminders.create_index([("remind_at", ASCENDING)])
        self.db.exams.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("exam_date", ASCENDING)])
        self.db.warnings.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("id", DESCENDING)])
        self.db.study_rooms.create_index([("guild_id", ASCENDING), ("created_by", ASCENDING), ("name_key", ASCENDING), ("active", ASCENDING)])
        self.db.voice_sessions.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        self.db.custom_subjects.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("subject_key", ASCENDING)], unique=True)
        self.db.weekly_rewards.create_index([("guild_id", ASCENDING), ("week_key", ASCENDING)], unique=True)
        self.db.inventory.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("item_key", ASCENDING)], unique=True)
        self.db.reports.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.reports.create_index(
            [("guild_id", ASCENDING), ("channel_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"channel_id": {"$exists": True}},
        )
        self.db.report_panels.create_index([("guild_id", ASCENDING)], unique=True)
        self.db.report_attempts.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.automod_events.create_index([("guild_id", ASCENDING), ("user_id", ASCENDING), ("created_at", DESCENDING)])

    def _next_id(self, name: str) -> int:
        counter = self.db.counters.find_one_and_update(
            {"_id": name},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(counter["value"])

    def ensure_user_stats(self, guild_id: int, user_id: int) -> None:
        defaults = {
            "coins": 0,
            "daily_goal_hours": 2.0,
            "focus_mode": False,
            "streak": 0,
            "longest_streak": 0,
            "total_focus_minutes": 0,
            "total_voice_minutes": 0,
            "last_study_day": None,
            "distraction_warnings": 0,
            "study_hours": 0.0,
            "xp": 0,
            "level": 1,
            "last_checkin": None,
            "streak_protects": 1,
            "protected_until": None,
            "language_warning_count": 0,
            "language_mute_count": 0,
            "language_warning_expires_at": None,
            "moderation_warning_count": 0,
            "moderation_timeout_count": 0,
            "moderation_warning_expires_at": None,
        }
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$setOnInsert": defaults},
            upsert=True,
        )
        self.db.users.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {
                "$setOnInsert": {
                    **defaults,
                    "user_id": user_id,
                }
            },
            upsert=True,
        )
        self.db.coins.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$setOnInsert": {"balance": 0, "updated_at": utc_now()}},
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

    def save_note(self, guild_id: int, user_id: int, title: str, content: str) -> int:
        note_id = self._next_id("notes")
        self.db.notes.insert_one(
            {
                "id": note_id,
                "guild_id": guild_id,
                "user_id": user_id,
                "title": title,
                "content": content,
                "created_at": utc_now(),
            }
        )
        return note_id

    def get_note_by_id(self, guild_id: int, user_id: int, note_id: int) -> dict | None:
        return self.db.notes.find_one({"guild_id": guild_id, "user_id": user_id, "id": note_id}, {"_id": 0})

    def list_notes(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self.db.notes.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}).sort("id", ASCENDING))

    def delete_note_by_id(self, guild_id: int, user_id: int, note_id: int) -> bool:
        result = self.db.notes.delete_one({"guild_id": guild_id, "user_id": user_id, "id": note_id})
        return result.deleted_count > 0

    def set_plan(self, guild_id: int, user_id: int, day: str, target_date: str, tasks: str) -> None:
        self.db.plans.update_one(
            {"guild_id": guild_id, "user_id": user_id, "target_date": target_date},
            {"$set": {"day": day, "day_key": day.lower(), "target_date": target_date, "tasks": tasks, "updated_at": utc_now()}},
            upsert=True,
        )

    def get_plan_by_date(self, guild_id: int, user_id: int, target_date: str) -> dict | None:
        return self.db.plans.find_one({"guild_id": guild_id, "user_id": user_id, "target_date": target_date}, {"_id": 0})

    def list_plans(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self.db.plans.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}).sort("target_date", ASCENDING))

    def add_progress(self, guild_id: int, user_id: int, subject: str, hours: float) -> None:
        payload = {
            "id": self._next_id("progress_logs"),
            "guild_id": guild_id,
            "user_id": user_id,
            "subject": subject,
            "subject_key": subject.lower(),
            "hours": hours,
            "logged_at": utc_now(),
        }
        self.db.progress_logs.insert_one(payload)
        self.db.progress.insert_one(payload)
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"study_hours": hours}})
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"study_hours": hours}})
        self.record_study_activity(guild_id, user_id)
        self.add_coins(guild_id, user_id, int(hours * 20))
        self.add_xp(guild_id, user_id, max(10, int(hours * 20)))

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

    def weekly_progress_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        since = utc_now() - timedelta(days=7)
        rows = list(
            self.db.progress_logs.aggregate(
                [
                    {"$match": {"guild_id": guild_id, "logged_at": {"$gte": since}}},
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
            hours = round(minutes / 60, 2)
            focus_subject = subject or "focused study"
            progress_payload = {
                "id": self._next_id("progress_logs"),
                "guild_id": guild_id,
                "user_id": user_id,
                "subject": focus_subject,
                "subject_key": focus_subject.lower(),
                "hours": hours,
                "logged_at": now,
                "source": "timer",
            }
            self.db.progress_logs.insert_one(progress_payload)
            self.db.progress.insert_one(progress_payload)
            self.db.user_stats.update_one(
                {"guild_id": guild_id, "user_id": user_id},
                {"$inc": {"total_focus_minutes": minutes, "study_hours": hours}},
            )
            self.db.users.update_one(
                {"guild_id": guild_id, "user_id": user_id},
                {"$inc": {"total_focus_minutes": minutes, "study_hours": hours}},
            )
            self.add_coins(guild_id, user_id, max(5, minutes // 5))
            self.add_xp(guild_id, user_id, max(10, minutes // 2))
        self.record_study_activity(guild_id, user_id)

    def record_study_activity(self, guild_id: int, user_id: int) -> None:
        today = utc_now().date().isoformat()
        self.ensure_user_stats(guild_id, user_id)
        self.db.study_days.update_one(
            {"guild_id": guild_id, "user_id": user_id, "day": today},
            {"$setOnInsert": {"day": today}},
            upsert=True,
        )
        self.db.streaks.update_one(
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
        profile = self.get_user_stats(guild_id, user_id)
        protected_until_raw = str(profile.get("protected_until") or "").strip()
        protected_until = datetime.fromisoformat(protected_until_raw).date() if protected_until_raw else None
        streak = 0
        cursor_day = today if today in day_set else today - timedelta(days=1)
        if cursor_day in day_set:
            while cursor_day in day_set:
                streak += 1
                cursor_day -= timedelta(days=1)
        elif protected_until is not None and protected_until >= today and profile.get("streak", 0):
            streak = int(profile.get("streak", 0))
        longest = max(streak, int(profile["longest_streak"]))
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"streak": streak, "longest_streak": longest, "last_study_day": today.isoformat()}},
        )
        self.db.users.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"streak": streak, "longest_streak": longest, "last_study_day": today.isoformat()}},
        )
        return self.get_user_stats(guild_id, user_id)

    def reset_streak(self, guild_id: int, user_id: int) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"streak": 0, "protected_until": None}})
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"streak": 0, "protected_until": None}})

    def get_user_stats(self, guild_id: int, user_id: int) -> dict:
        self.ensure_user_stats(guild_id, user_id)
        profile = self.db.users.find_one({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}) or {}
        legacy = self.db.user_stats.find_one({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}) or {}
        coins = self.db.coins.find_one({"guild_id": guild_id, "user_id": user_id}, {"_id": 0, "balance": 1}) or {}
        merged = {**legacy, **profile}
        if "balance" in coins:
            merged["coins"] = int(coins["balance"])
        return merged

    def set_goal(self, guild_id: int, user_id: int, hours_per_day: float) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"daily_goal_hours": hours_per_day}},
        )
        self.db.users.update_one(
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

    def delete_resource(self, guild_id: int, user_id: int, subject: str, resource_id: int) -> bool:
        result = self.db.resources.delete_one({"guild_id": guild_id, "user_id": user_id, "subject_key": subject.lower(), "id": resource_id})
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

    def delete_reminder_for_user(self, guild_id: int, user_id: int, reminder_id: int) -> bool:
        result = self.db.reminders.delete_one({"guild_id": guild_id, "user_id": user_id, "id": reminder_id})
        return result.deleted_count > 0

    def update_reminder_source(self, reminder_id: int, message_id: int) -> None:
        self.db.reminders.update_one({"id": reminder_id}, {"$set": {"source_message_id": message_id}})

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
                "subject_key": subject.lower(),
                "exam_date": exam_date,
            }
        )
        return exam_id

    def cleanup_expired_exams(self, guild_id: int, user_id: int) -> None:
        today = utc_now().date().isoformat()
        self.db.exams.delete_many({"guild_id": guild_id, "user_id": user_id, "exam_date": {"$lt": today}})

    def list_exams(self, guild_id: int, user_id: int, subject: str = "") -> list[dict]:
        self.cleanup_expired_exams(guild_id, user_id)
        query = {"guild_id": guild_id, "user_id": user_id}
        if subject:
            query["subject_key"] = subject.lower()
        return list(self.db.exams.find(query, {"_id": 0}).sort("exam_date", ASCENDING))

    def add_coins(self, guild_id: int, user_id: int, amount: int) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"coins": amount}})
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"coins": amount}})
        self.db.coins.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"balance": amount}, "$set": {"updated_at": utc_now()}},
            upsert=True,
        )

    def spend_coins(self, guild_id: int, user_id: int, amount: int) -> bool:
        self.ensure_user_stats(guild_id, user_id)
        stats = self.get_user_stats(guild_id, user_id)
        if int(stats["coins"]) < amount:
            return False
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"coins": -amount}})
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"coins": -amount}})
        self.db.coins.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"balance": -amount}, "$set": {"updated_at": utc_now()}},
            upsert=True,
        )
        return True

    def coin_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        return list(
            self.db.users.find({"guild_id": guild_id}, {"_id": 0, "user_id": 1, "coins": 1, "total_focus_minutes": 1, "level": 1})
            .sort([("coins", DESCENDING), ("total_focus_minutes", DESCENDING)])
            .limit(limit)
        )

    def set_focus_mode(self, guild_id: int, user_id: int, enabled: bool) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"focus_mode": enabled}})
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"focus_mode": enabled}})

    def add_distraction_warning(self, guild_id: int, user_id: int) -> None:
        self.ensure_user_stats(guild_id, user_id)
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"distraction_warnings": 1}})
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"distraction_warnings": 1}})

    def _clear_expired_moderation_warning_for_user(self, guild_id: int, user_id: int) -> None:
        now = utc_now()
        query = {
            "guild_id": guild_id,
            "user_id": user_id,
            "moderation_warning_count": {"$gt": 0},
            "moderation_warning_expires_at": {"$lte": now},
        }
        updates = {"moderation_warning_count": 0, "moderation_warning_expires_at": None}
        self.db.users.update_one(query, {"$set": updates})
        self.db.user_stats.update_one(query, {"$set": updates})

    def get_moderation_enforcement(self, guild_id: int, user_id: int) -> dict[str, int]:
        self._clear_expired_moderation_warning_for_user(guild_id, user_id)
        stats = self.get_user_stats(guild_id, user_id)
        return {
            "warning_count": int(stats.get("moderation_warning_count", 0)),
            "timeout_count": int(stats.get("moderation_timeout_count", 0)),
        }

    def add_moderation_warning(self, guild_id: int, user_id: int) -> dict[str, int]:
        self.ensure_user_stats(guild_id, user_id)
        self._clear_expired_moderation_warning_for_user(guild_id, user_id)
        expires_at = utc_now() + LANGUAGE_WARNING_DECAY
        self.db.users.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"moderation_warning_count": 1}, "$set": {"moderation_warning_expires_at": expires_at}},
        )
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"moderation_warning_count": 1}, "$set": {"moderation_warning_expires_at": expires_at}},
        )
        return self.get_moderation_enforcement(guild_id, user_id)

    def apply_moderation_timeout(self, guild_id: int, user_id: int) -> dict[str, int]:
        self.ensure_user_stats(guild_id, user_id)
        updates = {"moderation_warning_count": 0, "moderation_warning_expires_at": None}
        self.db.users.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": updates, "$inc": {"moderation_timeout_count": 1}},
        )
        self.db.user_stats.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": updates, "$inc": {"moderation_timeout_count": 1}},
        )
        return self.get_moderation_enforcement(guild_id, user_id)

    def clear_expired_moderation_warnings(self) -> int:
        now = utc_now()
        query = {
            "moderation_warning_count": {"$gt": 0},
            "moderation_warning_expires_at": {"$lte": now},
        }
        updates = {"moderation_warning_count": 0, "moderation_warning_expires_at": None}
        result = self.db.users.update_many(query, {"$set": updates})
        self.db.user_stats.update_many(query, {"$set": updates})
        return int(result.modified_count)

    def _clear_expired_language_warning_for_user(self, guild_id: int, user_id: int) -> None:
        self._clear_expired_moderation_warning_for_user(guild_id, user_id)

    def get_language_enforcement(self, guild_id: int, user_id: int) -> dict[str, int]:
        counts = self.get_moderation_enforcement(guild_id, user_id)
        return {
            "warning_count": counts["warning_count"],
            "mute_count": counts["timeout_count"],
        }

    def add_language_warning(self, guild_id: int, user_id: int) -> dict[str, int]:
        counts = self.add_moderation_warning(guild_id, user_id)
        return {
            "warning_count": counts["warning_count"],
            "mute_count": counts["timeout_count"],
        }

    def apply_language_mute(self, guild_id: int, user_id: int) -> dict[str, int]:
        counts = self.apply_moderation_timeout(guild_id, user_id)
        return {
            "warning_count": counts["warning_count"],
            "mute_count": counts["timeout_count"],
        }

    def clear_expired_language_warnings(self) -> int:
        return self.clear_expired_moderation_warnings()

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

    def create_report(self, guild_id: int, user_id: int, request_channel_id: int, report_channel_id: int | None = None) -> dict:
        report_id = self._next_id("reports")
        payload = {
            "id": report_id,
            "guild_id": guild_id,
            "user_id": user_id,
            "request_channel_id": request_channel_id,
            "status": "awaiting_evidence",
            "claimed_by": None,
            "thanked_by": None,
            "thanked_at": None,
            "created_at": utc_now(),
        }
        if report_channel_id is not None:
            payload["channel_id"] = report_channel_id
        self.db.reports.insert_one(payload)
        return payload

    def get_active_report_for_user(self, guild_id: int, user_id: int) -> dict | None:
        return self.db.reports.find_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"_id": 0},
            sort=[("created_at", DESCENDING)],
        )

    def get_active_report_by_channel(self, guild_id: int, channel_id: int) -> dict | None:
        return self.db.reports.find_one(
            {"guild_id": guild_id, "channel_id": channel_id},
            {"_id": 0},
            sort=[("created_at", DESCENDING)],
        )

    def get_active_report_for_dm_user(self, user_id: int) -> dict | None:
        return self.db.reports.find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("created_at", DESCENDING)],
        )

    def mark_report_submitted(self, report_id: int) -> None:
        self.db.reports.update_one(
            {"id": report_id},
            {"$set": {"status": "submitted", "submitted_at": utc_now()}},
        )

    def attach_report_channel(self, report_id: int, channel_id: int) -> dict | None:
        return self.db.reports.find_one_and_update(
            {"id": report_id},
            {"$set": {"channel_id": channel_id}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    def claim_report(self, report_id: int, moderator_id: int) -> dict | None:
        return self.db.reports.find_one_and_update(
            {"id": report_id},
            {"$set": {"status": "claimed", "claimed_by": moderator_id, "claimed_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    def mark_report_thanked(self, report_id: int, moderator_id: int) -> dict | None:
        return self.db.reports.find_one_and_update(
            {"id": report_id, "thanked_at": None},
            {"$set": {"thanked_by": moderator_id, "thanked_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    def close_report(self, report_id: int) -> dict | None:
        return self.db.reports.find_one_and_delete({"id": report_id}, {"_id": 0})

    def close_report_by_channel(self, guild_id: int, channel_id: int) -> dict | None:
        return self.db.reports.find_one_and_delete({"guild_id": guild_id, "channel_id": channel_id}, {"_id": 0})

    def get_report_panel_state(self, guild_id: int) -> dict | None:
        return self.db.report_panels.find_one({"guild_id": guild_id}, {"_id": 0})

    def set_report_panel_state(
        self,
        guild_id: int,
        *,
        channel_id: int,
        message_id: int | None = None,
        category_id: int | None = None,
    ) -> None:
        updates: dict[str, object] = {"guild_id": guild_id, "channel_id": channel_id}
        if message_id is not None:
            updates["message_id"] = message_id
        if category_id is not None:
            updates["category_id"] = category_id
        self.db.report_panels.update_one(
            {"guild_id": guild_id},
            {"$set": updates},
            upsert=True,
        )

    def add_report_attempt(self, guild_id: int, user_id: int) -> int:
        now = utc_now()
        self.db.report_attempts.insert_one(
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "created_at": now,
            }
        )
        since = now - timedelta(minutes=10)
        return int(
            self.db.report_attempts.count_documents(
                {
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "created_at": {"$gte": since},
                }
            )
        )

    def record_automod_violation(self, guild_id: int, user_id: int, kind: str, preview: str) -> int:
        now = utc_now()
        self.db.automod_events.insert_one(
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "kind": kind,
                "preview": preview[:300],
                "created_at": now,
            }
        )
        since = now - timedelta(hours=24)
        return int(
            self.db.automod_events.count_documents(
                {
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "created_at": {"$gte": since},
                }
            )
        )

    def record_text_violation(self, guild_id: int, user_id: int, kind: str, preview: str) -> int:
        now = utc_now()
        self.db.automod_events.insert_one(
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "kind": kind,
                "preview": preview[:300],
                "created_at": now,
            }
        )
        since = now - timedelta(hours=24)
        return int(
            self.db.automod_events.count_documents(
                {
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "kind": kind,
                    "created_at": {"$gte": since},
                }
            )
        )

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
                "locked": False,
                "created_at": utc_now(),
            }
        )
        return room_id

    def get_room_by_name(self, guild_id: int, created_by: int, name: str) -> dict | None:
        return self.db.study_rooms.find_one(
            {"guild_id": guild_id, "created_by": created_by, "name_key": name.lower(), "active": True},
            {"_id": 0},
            sort=[("id", DESCENDING)],
        )

    def list_rooms_for_user(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self.db.study_rooms.find({"guild_id": guild_id, "created_by": user_id, "active": True}, {"_id": 0}).sort("name", ASCENDING))

    def is_active_room_channel(self, guild_id: int, channel_id: int) -> bool:
        return self.db.study_rooms.find_one({"guild_id": guild_id, "channel_id": channel_id, "active": True}, {"_id": 1}) is not None

    def get_active_room_channel_ids(self, guild_id: int) -> set[int]:
        rows = self.db.study_rooms.find({"guild_id": guild_id, "active": True}, {"_id": 0, "channel_id": 1})
        return {int(row["channel_id"]) for row in rows if row.get("channel_id") is not None}

    def deactivate_room(self, channel_id: int) -> None:
        self.db.study_rooms.update_one({"channel_id": channel_id}, {"$set": {"active": False}})

    def delete_room(self, guild_id: int, created_by: int, name: str) -> dict | None:
        return self.db.study_rooms.find_one_and_delete(
            {"guild_id": guild_id, "created_by": created_by, "name_key": name.lower(), "active": True},
            {"_id": 0},
        )

    def set_room_lock(self, guild_id: int, created_by: int, name: str, locked: bool) -> dict | None:
        return self.db.study_rooms.find_one_and_update(
            {"guild_id": guild_id, "created_by": created_by, "name_key": name.lower(), "active": True},
            {"$set": {"locked": locked}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

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
        self.db.users.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"total_voice_minutes": minutes}},
        )
        if minutes > 0:
            self.record_study_activity(guild_id, user_id)
            self.add_coins(guild_id, user_id, max(3, minutes // 10))
            self.add_xp(guild_id, user_id, max(5, minutes // 8))
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
            "study_hours": round(float(stats.get("study_hours", 0.0)), 2),
            "xp": int(stats.get("xp", 0)),
            "level": int(stats.get("level", 1)),
            "daily_goal_hours": float(stats["daily_goal_hours"]),
            "today_hours": today_hours,
            "total_logged_hours": float(totals["logged_hours"]),
            "focus_minutes": int(stats["total_focus_minutes"]),
            "voice_minutes": int(stats["total_voice_minutes"]),
            "pending_tasks": tasks,
            "top_subjects": week[:3],
            "upcoming_exams": exams[:3],
        }

    def add_custom_subject(self, guild_id: int, user_id: int, subject: str) -> None:
        clean = subject.strip()
        if not clean:
            return
        self.db.custom_subjects.update_one(
            {"guild_id": guild_id, "user_id": user_id, "subject_key": clean.lower()},
            {"$setOnInsert": {"subject": clean, "subject_key": clean.lower(), "created_at": utc_now()}},
            upsert=True,
        )

    def get_user_subjects(self, guild_id: int, user_id: int) -> list[str]:
        rows = self.db.custom_subjects.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0, "subject": 1}).sort("subject", ASCENDING)
        return [row["subject"] for row in rows]

    def get_weekly_reward_status(self, guild_id: int, week_key: str) -> dict | None:
        return self.db.weekly_rewards.find_one({"guild_id": guild_id, "week_key": week_key}, {"_id": 0})

    def mark_weekly_rewards(self, guild_id: int, week_key: str, rewarded_user_ids: list[int]) -> None:
        self.db.weekly_rewards.update_one(
            {"guild_id": guild_id, "week_key": week_key},
            {"$set": {"rewarded_user_ids": rewarded_user_ids, "rewarded_at": utc_now()}},
            upsert=True,
        )

    def add_inventory_item(self, guild_id: int, user_id: int, item_key: str, item_name: str) -> None:
        self.db.inventory.update_one(
            {"guild_id": guild_id, "user_id": user_id, "item_key": item_key},
            {"$inc": {"quantity": 1}, "$setOnInsert": {"item_name": item_name}},
            upsert=True,
        )

    def get_inventory(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self.db.inventory.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}).sort("item_name", ASCENDING))

    def add_xp(self, guild_id: int, user_id: int, amount: int) -> dict:
        self.ensure_user_stats(guild_id, user_id)
        current = self.get_user_stats(guild_id, user_id)
        xp = int(current.get("xp", 0)) + max(0, amount)
        level = max(1, (xp // 100) + 1)
        payload = {"xp": xp, "level": level}
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": payload})
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": payload})
        return {"xp": xp, "level": level}

    def daily_checkin(self, guild_id: int, user_id: int) -> dict:
        self.ensure_user_stats(guild_id, user_id)
        today = utc_now().date().isoformat()
        stats = self.get_user_stats(guild_id, user_id)
        if stats.get("last_checkin") == today:
            return {"ok": False, "reason": "already_checked_in", "stats": stats}
        reward = 25 + min(25, int(stats.get("streak", 0)) * 2)
        self.record_study_activity(guild_id, user_id)
        self.add_coins(guild_id, user_id, reward)
        xp = self.add_xp(guild_id, user_id, 20)
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"last_checkin": today}})
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"last_checkin": today}})
        updated = self.refresh_streak(guild_id, user_id)
        return {"ok": True, "reward": reward, "xp": xp, "stats": updated}

    def activate_streak_protection(self, guild_id: int, user_id: int) -> dict:
        self.ensure_user_stats(guild_id, user_id)
        stats = self.get_user_stats(guild_id, user_id)
        remaining = int(stats.get("streak_protects", 0))
        if remaining <= 0:
            return {"ok": False, "reason": "no_protects", "stats": stats}
        protected_until = (utc_now().date() + timedelta(days=1)).isoformat()
        updates = {"streak_protects": remaining - 1, "protected_until": protected_until}
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": updates})
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": updates})
        return {"ok": True, "protected_until": protected_until, "remaining": remaining - 1}

    def grant_streak_protect(self, guild_id: int, user_id: int, amount: int = 1) -> None:
        self.ensure_user_stats(guild_id, user_id)
        amount = max(0, amount)
        if amount <= 0:
            return
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"streak_protects": amount}})
        self.db.user_stats.update_one({"guild_id": guild_id, "user_id": user_id}, {"$inc": {"streak_protects": amount}})

    def get_dashboard_data(self, guild_id: int, user_id: int) -> dict[str, object]:
        stats = self.get_user_stats(guild_id, user_id)
        summary = self.analytics_summary(guild_id, user_id)
        tasks = self.list_tasks(guild_id, user_id)[:5]
        exams = self.list_exams(guild_id, user_id)[:5]
        plans = self.list_plans(guild_id, user_id)[:3]
        inventory = self.get_inventory(guild_id, user_id)[:8]
        return {
            "stats": stats,
            "summary": summary,
            "tasks": tasks,
            "exams": exams,
            "plans": plans,
            "inventory": inventory,
        }

    def get_voice_stats(self, guild_id: int, user_id: int) -> dict[str, int]:
        stats = self.get_user_stats(guild_id, user_id)
        current = self.db.voice_sessions.find_one({"guild_id": guild_id, "user_id": user_id}, {"_id": 0, "started_at": 1})
        current_minutes = 0
        if current is not None:
            current_minutes = max(0, int((utc_now() - current["started_at"]).total_seconds() // 60))
        return {
            "total_voice_minutes": int(stats.get("total_voice_minutes", 0)),
            "current_session_minutes": current_minutes,
            "total_focus_minutes": int(stats.get("total_focus_minutes", 0)),
        }

    def get_daily_graph(self, guild_id: int, user_id: int, days: int = 7) -> list[dict]:
        since = utc_now() - timedelta(days=max(1, days - 1))
        rows = list(
            self.db.progress.aggregate(
                [
                    {"$match": {"guild_id": guild_id, "user_id": user_id, "logged_at": {"$gte": since}}},
                    {"$addFields": {"day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$logged_at", "timezone": "UTC"}}}},
                    {"$group": {"_id": "$day", "hours": {"$sum": "$hours"}}},
                    {"$sort": {"_id": 1}},
                ]
            )
        )
        mapped = {row["_id"]: round(float(row["hours"]), 2) for row in rows}
        points = []
        for offset in range(max(1, days)):
            day = (utc_now().date() - timedelta(days=(days - 1 - offset))).isoformat()
            points.append({"day": day, "hours": mapped.get(day, 0.0)})
        return points

    def get_subject_totals(self, guild_id: int, user_id: int) -> list[dict]:
        rows = list(
            self.db.progress.aggregate(
                [
                    {"$match": {"guild_id": guild_id, "user_id": user_id}},
                    {"$group": {"_id": "$subject", "hours": {"$sum": "$hours"}, "last_seen": {"$max": "$logged_at"}}},
                    {"$sort": {"hours": -1}},
                ]
            )
        )
        return [{"subject": row["_id"], "hours": round(float(row["hours"]), 2), "last_seen": row["last_seen"]} for row in rows]

    def get_weak_subjects(self, guild_id: int, user_id: int, limit: int = 3) -> list[dict]:
        subjects = self.get_subject_totals(guild_id, user_id)
        weak = sorted(subjects, key=lambda row: (row["hours"], row["subject"]))
        return weak[:limit]

    def get_revision_topics(self, guild_id: int, user_id: int, limit: int = 5) -> list[dict]:
        subjects = self.get_subject_totals(guild_id, user_id)
        if not subjects:
            return []
        ordered = sorted(subjects, key=lambda row: row["last_seen"] or utc_now())
        return ordered[:limit]

    def _unlock_achievement(self, guild_id: int, user_id: int, key: str, name: str, description: str) -> bool:
        result = self.db.achievements.update_one(
            {"guild_id": guild_id, "user_id": user_id, "key": key},
            {"$setOnInsert": {"name": name, "description": description, "unlocked_at": utc_now()}},
            upsert=True,
        )
        return result.upserted_id is not None

    def sync_achievements(self, guild_id: int, user_id: int) -> list[dict]:
        stats = self.get_user_stats(guild_id, user_id)
        unlocked: list[dict] = []
        checks = [
            ("first_checkin", stats.get("last_checkin") is not None, "First Check-In", "Completed your first daily check-in."),
            ("streak_7", int(stats.get("streak", 0)) >= 7, "Streak Builder", "Reached a 7-day study streak."),
            ("focus_100", int(stats.get("total_focus_minutes", 0)) >= 100, "Focus Rookie", "Completed 100 focus minutes."),
            ("voice_120", int(stats.get("total_voice_minutes", 0)) >= 120, "Voice Regular", "Spent 120 minutes in study voice."),
            ("coins_500", int(stats.get("coins", 0)) >= 500, "Coin Collector", "Saved 500 study coins."),
            ("level_5", int(stats.get("level", 1)) >= 5, "Level Climber", "Reached level 5."),
        ]
        if len(self.list_tasks(guild_id, user_id)) >= 1:
            checks.append(("task_starter", True, "Task Starter", "Created your first study task."))
        if len(self.list_notes(guild_id, user_id)) >= 1:
            checks.append(("note_keeper", True, "Note Keeper", "Saved your first study note."))
        if len(self.list_exams(guild_id, user_id)) >= 1:
            checks.append(("exam_planner", True, "Exam Planner", "Added your first exam."))
        for key, condition, name, description in checks:
            if not condition:
                continue
            if self._unlock_achievement(guild_id, user_id, key, name, description):
                unlocked.append({"key": key, "name": name, "description": description})
        return unlocked

    def list_achievements(self, guild_id: int, user_id: int) -> list[dict]:
        return list(self.db.achievements.find({"guild_id": guild_id, "user_id": user_id}, {"_id": 0}).sort("unlocked_at", DESCENDING))

    def get_daily_report_candidates(self, guild_id: int) -> list[dict]:
        return list(self.db.users.find({"guild_id": guild_id}, {"_id": 0, "user_id": 1, "last_report_day": 1, "last_study_day": 1}))

    def mark_daily_report_sent(self, guild_id: int, user_id: int, day: str) -> None:
        self.db.users.update_one({"guild_id": guild_id, "user_id": user_id}, {"$set": {"last_report_day": day}})
