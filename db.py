"""本地 SQLite 数据层：任务、打卡记录、提醒、设置与状态推导。

状态语义（严格按 AI_SPEC）：
- pending : 今天尚未结束且没有记录（推导，不落库）
- perfect / smooth / hard / pain : 四种完成质量（落库）
- missed  : 日期已结束且没有记录（推导，不落库）
"""

from __future__ import annotations

import calendar
import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

STATUSES = ("perfect", "smooth", "hard", "pain")
STATUS_LABEL = {
    "pending": "待打卡",
    "perfect": "完美",
    "smooth": "顺利",
    "hard": "艰难",
    "pain": "痛苦",
    "missed": "未记录",
}
SEVERITY = {"perfect": 0, "smooth": 1, "hard": 2, "pain": 3}

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "checkin.db"


def default_db_path() -> Path:
    """Android 上应用包内目录只读，优先使用 Flet 提供的可写数据目录。"""
    storage = os.getenv("FLET_APP_STORAGE_DATA")
    if storage:
        return Path(storage) / "checkin.db"
    return DEFAULT_DB_PATH


def today() -> date:
    return date.today()


def iso(d: date) -> str:
    return d.isoformat()


def parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def effective_status(checkin: Optional[dict], d: date, today_date: Optional[date] = None) -> str:
    """未记录 = 日期已结束且无 CheckIn；当天未结束无记录 = pending。"""
    if checkin:
        return checkin["status"]
    return "pending" if d >= (today_date or today()) else "missed"


def weekday_cn(d: date) -> str:
    return "一二三四五六日"[d.weekday()]


class DB:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        self._seed_if_needed()

    # ------------------------------------------------------------------ 基础
    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS task (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'normal' CHECK (type IN ('normal', 'special')),
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                deadline TEXT,
                created_at TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS checkin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('perfect', 'smooth', 'hard', 'pain')),
                is_backfill INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (task_id, date)
            );

            CREATE TABLE IF NOT EXISTS reminder (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL UNIQUE REFERENCES task(id) ON DELETE CASCADE,
                time TEXT,
                repeat_rule TEXT NOT NULL DEFAULT 'daily',
                enabled INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_checkin_date ON checkin (date);
            CREATE INDEX IF NOT EXISTS idx_checkin_task ON checkin (task_id, date);
            """
        )
        self.conn.commit()

    def _seed_if_needed(self) -> None:
        if self.get_setting("seeded"):
            return
        self.set_setting("seeded", "1")
        self.set_setting("theme_mode", "light")
        self.set_setting("summary_enabled", "0")
        self.set_setting("summary_time", "21:00")
        if self.list_tasks(include_archived=True):
            return
        t = today()
        self.add_task("本周复盘 · 写下三件小事", "special", deadline=iso(t + timedelta(days=2)))
        self.add_task("早睡 · 24:00 前放下手机", "normal", reminder_time="22:30")
        self.add_task("阅读 30 分钟", "normal")
        self.add_task("运动 20 分钟", "normal")

    # ------------------------------------------------------------------ 设置
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ 任务
    def list_tasks(self, include_archived: bool = False) -> list[dict]:
        sql = """
            SELECT t.*, r.time AS reminder_time, r.repeat_rule AS reminder_repeat,
                   r.enabled AS reminder_enabled
            FROM task t
            LEFT JOIN reminder r ON r.task_id = t.id
        """
        if not include_archived:
            sql += " WHERE t.archived = 0"
        sql += " ORDER BY t.archived, t.is_pinned DESC, t.sort_order, t.id"
        return [dict(r) for r in self.conn.execute(sql).fetchall()]

    def get_task(self, task_id: int) -> Optional[dict]:
        for t in self.list_tasks(include_archived=True):
            if t["id"] == task_id:
                return t
        return None

    def tasks_for_date(self, d: date) -> list[dict]:
        """某天可记录的任务：归档任务仅在有记录时保留。

        允许为任务创建之前的日期补记（凭记忆补录），日历的未记录统计仍按创建日期起算。
        """
        result = []
        for t in self.list_tasks(include_archived=True):
            if t["archived"] and not self.get_checkin(t["id"], d):
                continue
            result.append(t)
        return result

    def add_task(
        self,
        name: str,
        type_: str = "normal",
        deadline: Optional[str] = None,
        reminder_time: Optional[str] = None,
        repeat_rule: str = "daily",
        reminder_enabled: bool = False,
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("任务名称不能为空")
        if type_ not in ("normal", "special"):
            raise ValueError("未知任务类型")
        sort_order = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM task WHERE type = ?", (type_,)
        ).fetchone()[0]
        cur = self.conn.execute(
            "INSERT INTO task (name, type, sort_order, is_pinned, deadline, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, type_, sort_order, 1 if type_ == "special" else 0, deadline, now_iso()),
        )
        task_id = int(cur.lastrowid)
        if reminder_time:
            self.set_reminder(task_id, reminder_time, repeat_rule, bool(reminder_enabled or True))
        self.conn.commit()
        return task_id

    def update_task(self, task_id: int, **fields: Any) -> None:
        allowed = {"name", "type", "deadline", "sort_order", "is_pinned", "archived"}
        sets, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "type" and value not in ("normal", "special"):
                raise ValueError("未知任务类型")
            sets.append(f"{key} = ?")
            values.append(value)
        if not sets:
            return
        values.append(task_id)
        self.conn.execute(f"UPDATE task SET {', '.join(sets)} WHERE id = ?", values)
        if "type" in fields:
            self.conn.execute(
                "UPDATE task SET is_pinned = ? WHERE id = ?",
                (1 if fields["type"] == "special" else 0, task_id),
            )
        self.conn.commit()

    def set_archived(self, task_id: int, archived: bool) -> None:
        self.update_task(task_id, archived=1 if archived else 0)

    def delete_task(self, task_id: int) -> None:
        self.conn.execute("DELETE FROM task WHERE id = ?", (task_id,))
        self.conn.commit()

    # ------------------------------------------------------------------ 提醒
    def set_reminder(self, task_id: int, time: Optional[str], repeat_rule: str = "daily", enabled: bool = True) -> None:
        if not time:
            self.conn.execute("DELETE FROM reminder WHERE task_id = ?", (task_id,))
            self.conn.commit()
            return
        self.conn.execute(
            "INSERT INTO reminder (task_id, time, repeat_rule, enabled) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(task_id) DO UPDATE SET time = excluded.time, "
            "repeat_rule = excluded.repeat_rule, enabled = excluded.enabled",
            (task_id, time, repeat_rule, 1 if enabled else 0),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ 打卡
    def get_checkin(self, task_id: int, d: date) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM checkin WHERE task_id = ? AND date = ?", (task_id, iso(d))
        ).fetchone()
        return dict(row) if row else None

    def day_checkins(self, d: date) -> dict[int, dict]:
        rows = self.conn.execute("SELECT * FROM checkin WHERE date = ?", (iso(d),)).fetchall()
        return {int(r["task_id"]): dict(r) for r in rows}

    def upsert_checkin(self, task_id: int, d: date, status: str, note: Optional[str] = None) -> None:
        if status not in STATUSES:
            raise ValueError("打卡状态只能是 perfect / smooth / hard / pain")
        if d > today():
            raise ValueError("不能为未来日期打卡")
        is_backfill = 1 if d < today() else 0
        note = (note or "").strip() or None
        now = now_iso()
        self.conn.execute(
            "INSERT INTO checkin (task_id, date, status, is_backfill, note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(task_id, date) DO UPDATE SET status = excluded.status, "
            "note = excluded.note, is_backfill = excluded.is_backfill, updated_at = excluded.updated_at",
            (task_id, iso(d), status, is_backfill, note, now, now),
        )
        self.conn.commit()

    def delete_checkin(self, task_id: int, d: date) -> None:
        self.conn.execute("DELETE FROM checkin WHERE task_id = ? AND date = ?", (task_id, iso(d)))
        self.conn.commit()

    def checkins_between(self, start: date, end: date) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM checkin WHERE date BETWEEN ? AND ? ORDER BY date", (iso(start), iso(end))
        ).fetchall()
        return [dict(r) for r in rows]

    def task_checkins(self, task_id: int, start: date, end: date) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM checkin WHERE task_id = ? AND date BETWEEN ? AND ? ORDER BY date",
            (task_id, iso(start), iso(end)),
        ).fetchall()
        return [dict(r) for r in rows]

    def month_map(self, year: int, month: int) -> dict[str, dict]:
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        buckets: dict[str, dict] = {}
        for row in self.checkins_between(start, end):
            b = buckets.setdefault(row["date"], {"status": row["status"], "count": 0, "backfill": 0})
            b["count"] += 1
            b["backfill"] += 1 if row["is_backfill"] else 0
            if SEVERITY[row["status"]] > SEVERITY[b["status"]]:
                b["status"] = row["status"]

        # 无记录的日子：今天为 pending，过去为 missed；任务创建之前的日期留白。
        tasks = self.list_tasks()
        if not tasks:
            return buckets
        today_date = today()
        first_created = min(parse_date(t["created_at"]) for t in tasks)
        day = max(start, first_created)
        while day <= min(end, today_date):
            key = iso(day)
            if key not in buckets:
                buckets[key] = {
                    "status": "pending" if day == today_date else "missed",
                    "count": 0,
                    "backfill": 0,
                }
            day += timedelta(days=1)
        return buckets

    # ------------------------------------------------------------------ 统计
    def task_stats(self, task_id: int, days: int = 30) -> dict:
        end = today()
        start = end - timedelta(days=days - 1)
        rows = self.task_checkins(task_id, start, end)
        counts = {s: 0 for s in STATUSES}
        backfill = 0
        days_recorded = set()
        for r in rows:
            counts[r["status"]] += 1
            days_recorded.add(r["date"])
            backfill += 1 if r["is_backfill"] else 0
        return {
            "days": days,
            "records": len(rows),
            "counts": counts,
            "backfill": backfill,
            "streak": self._longest_streak(days_recorded),
        }

    def period_summary(self, start: date, end: date) -> dict:
        end = min(end, today())
        if start > end:
            return {"records": 0, "counts": {s: 0 for s in STATUSES}, "missed": 0,
                    "streak": 0, "special": 0, "backfill": 0, "days": 0}
        counts = {s: 0 for s in STATUSES}
        records = missed = special = backfill = 0
        recorded_days: set[str] = set()
        for t in self.list_tasks(include_archived=True):
            created = parse_date(t["created_at"])
            from_day = max(start, created)
            if from_day > end:
                continue
            rows = self.task_checkins(t["id"], from_day, end)
            for r in rows:
                counts[r["status"]] += 1
                records += 1
                recorded_days.add(r["date"])
                backfill += 1 if r["is_backfill"] else 0
                if t["type"] == "special":
                    special += 1
            if not t["archived"]:
                day = from_day
                while day <= end and day < today():
                    if not self.get_checkin(t["id"], day):
                        missed += 1
                    day += timedelta(days=1)
        return {
            "records": records,
            "counts": counts,
            "missed": missed,
            "streak": self._longest_streak(recorded_days),
            "special": special,
            "backfill": backfill,
            "days": (end - start).days + 1,
        }

    @staticmethod
    def _longest_streak(day_values: set[str]) -> int:
        if not day_values:
            return 0
        days = sorted(parse_date(v) for v in day_values)
        best = current = 1
        for prev, cur in zip(days, days[1:]):
            current = current + 1 if (cur - prev).days == 1 else 1
            best = max(best, current)
        return best

    # ------------------------------------------------------------------ 导入导出
    def export_data(self) -> dict:
        tasks = [dict(r) for r in self.conn.execute("SELECT * FROM task ORDER BY id").fetchall()]
        checkins = [dict(r) for r in self.conn.execute("SELECT * FROM checkin ORDER BY id").fetchall()]
        reminders = [dict(r) for r in self.conn.execute("SELECT * FROM reminder ORDER BY id").fetchall()]
        settings = {r["key"]: r["value"] for r in self.conn.execute("SELECT * FROM settings").fetchall()}
        return {
            "app": "checkin-taskbar",
            "version": 1,
            "exported_at": now_iso(),
            "tasks": tasks,
            "checkins": checkins,
            "reminders": reminders,
            "settings": settings,
        }

    def export_to_file(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.export_data(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def import_data(self, data: dict, replace: bool = True) -> None:
        if not isinstance(data, dict) or "tasks" not in data or "checkins" not in data:
            raise ValueError("不是有效的打卡数据文件")
        with self.conn:
            if replace:
                self.conn.execute("DELETE FROM checkin")
                self.conn.execute("DELETE FROM reminder")
                self.conn.execute("DELETE FROM task")
            for t in data.get("tasks", []):
                self.conn.execute(
                    "INSERT OR REPLACE INTO task (id, name, type, sort_order, is_pinned, deadline, "
                    "created_at, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (t.get("id"), t.get("name", "未命名"), t.get("type", "normal"),
                     t.get("sort_order", 0), t.get("is_pinned", 0), t.get("deadline"),
                     t.get("created_at", now_iso()), t.get("archived", 0)),
                )
            for c in data.get("checkins", []):
                self.conn.execute(
                    "INSERT OR REPLACE INTO checkin (id, task_id, date, status, is_backfill, note, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (c.get("id"), c["task_id"], c["date"], c["status"], c.get("is_backfill", 0),
                     c.get("note"), c.get("created_at", now_iso()), c.get("updated_at", now_iso())),
                )
            for r in data.get("reminders", []):
                self.conn.execute(
                    "INSERT OR REPLACE INTO reminder (id, task_id, time, repeat_rule, enabled) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (r.get("id"), r["task_id"], r.get("time"), r.get("repeat_rule", "daily"),
                     r.get("enabled", 0)),
                )
            for key, value in data.get("settings", {}).items():
                if key == "seeded":
                    continue
                self.conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    def clear_all(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM checkin")
            self.conn.execute("DELETE FROM reminder")
            self.conn.execute("DELETE FROM task")
            self.conn.execute("DELETE FROM settings")

    def close(self) -> None:
        self.conn.close()
