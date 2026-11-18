"""Local diary and explainable preferences for a single bedroom."""
import datetime as dt
import re
import sqlite3
import statistics
from contextlib import contextmanager


def minute(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("Enter a local time in HH:MM format.")
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def clock(value):
    hours, minutes = divmod(round(value) % 1440, 60)
    return f"{hours:02d}:{minutes:02d}"


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Expected a whole number from {low} to {high}.")
    return value


def routine(body):
    minute(body["bedtime"])
    return body["bedtime"], integer(body["minutes"], 0, 30), integer(body["level"], 1, 10)


def suggestion(nights):
    """One vote per date. Circular L1 median handles midnight without a day boundary."""
    recent = nights[:14]
    if len(recent) < 3:
        return None
    times = [minute(n["bedtime"]) for n in recent]
    distance = lambda a, b: abs((a - b + 720) % 1440 - 720)
    center = min(times, key=lambda t: sum(distance(t, v) for v in times))
    spread = statistics.median(distance(center, t) for t in times)
    if spread > 90:
        return None
    liked = [n for n in recent if n["comfort"] >= 4]
    return dict(bedtime=clock(center), nights=len(recent), spread=round(spread),
                minutes=round(statistics.median(n["minutes"] for n in liked)) if len(liked) >= 3 else None,
                liked=len(liked))


class Diary:
    def __init__(self, path):
        self.path = path
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS profiles (
                  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                  bedtime TEXT NOT NULL DEFAULT '22:30', minutes INTEGER NOT NULL DEFAULT 10,
                  level INTEGER NOT NULL DEFAULT 2);
                CREATE TABLE IF NOT EXISTS nights (
                  profile INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
                  date TEXT, bedtime TEXT NOT NULL, minutes INTEGER NOT NULL, comfort INTEGER NOT NULL,
                  PRIMARY KEY(profile,date));
                INSERT OR IGNORE INTO profiles(id,name) VALUES(1,'My room');
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def profile(self, db, pid):
        p = db.execute("SELECT * FROM profiles WHERE id=?", (integer(pid,1,2**31-1),)).fetchone()
        if p is None:
            raise ValueError("Profile does not exist.")
        return dict(p)

    def state(self, pid):
        with self.db() as db:
            p = self.profile(db, pid)
            rows = [dict(row) for row in db.execute(
                "SELECT date,bedtime,minutes,comfort FROM nights WHERE profile=? ORDER BY date DESC LIMIT 30", (pid,))]
            profiles = [dict(row) for row in db.execute("SELECT id,name FROM profiles ORDER BY id")]
            return dict(profile=p, profiles=profiles, nights=rows, suggestion=suggestion(rows))

    def update(self, action, body):
        with self.db() as db:
            if action == "new":
                name = body["name"].strip() if isinstance(body["name"],str) else ""
                if not 1 <= len(name) <= 50:
                    raise ValueError("Use a profile name between 1 and 50 characters.")
                return db.execute("INSERT INTO profiles(name) VALUES(?)", (name,)).lastrowid
            pid = self.profile(db, body["profile"])["id"]
            if action == "routine":
                db.execute("UPDATE profiles SET bedtime=?,minutes=?,level=? WHERE id=?", (*routine(body),pid))
            elif action == "night":
                day = dt.date.fromisoformat(body["date"])
                if day.isoformat() != body["date"] or day > dt.date.today():
                    raise ValueError("Use today or an earlier local date.")
                minute(body["bedtime"])
                db.execute("INSERT OR REPLACE INTO nights VALUES(?,?,?,?,?)",
                           (pid,day.isoformat(),body["bedtime"],integer(body["minutes"],0,30),
                            integer(body["comfort"],1,5)))
            elif action == "forget":
                db.execute("DELETE FROM nights WHERE profile=?", (pid,))
            else:
                raise ValueError("Unknown diary action.")
            return pid
