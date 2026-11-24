import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hotseat_core.storage import SessionStore


def make_legacy_classic_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            topic TEXT,
            audrey TEXT,
            claib TEXT,
            vertical TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO sessions (timestamp, topic, audrey, claib, vertical) VALUES (?,?,?,?,?)",
        ("2026-01-01T00:00:00", "legacy idea", "audit text", "market text", "closing text"),
    )
    conn.commit()
    conn.close()


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = self.root / "sessions.log"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_store_creates_schema_and_saves(self):
        store = SessionStore(self.root / "memory.db", self.log)
        store.initialize()
        session_id = store.save_session(
            mode="classic",
            topic="new idea",
            turns=[
                {"persona": "audrey", "speaker": "Dame Audrey", "content": "a", "round": 1, "model": "m"},
                {"persona": "claib", "speaker": "Claib", "content": "b", "round": 2, "model": "m"},
            ],
            transcript="# transcript",
            provider="demo",
            model="m",
        )
        self.assertGreater(session_id, 0)
        rows = store.recent(limit=5)
        self.assertEqual(rows[0]["topic"], "new idea")
        self.assertEqual([t["persona"] for t in rows[0]["turns"]], ["audrey", "claib"])
        self.assertEqual(rows[0]["provider"], "demo")

    def test_migrates_legacy_classic_database_without_losing_rows(self):
        db = self.root / "legacy.db"
        make_legacy_classic_db(db)
        store = SessionStore(db, self.log)
        store.initialize()

        with sqlite3.connect(db) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        self.assertTrue({"turns", "transcript", "mode", "provider", "model"} <= columns)

        rows = store.recent(limit=5)
        self.assertEqual(rows[0]["topic"], "legacy idea")
        self.assertEqual([t["persona"] for t in rows[0]["turns"]], ["audrey", "claib", "vertical"])
        self.assertEqual(rows[0]["transcript"] is None, True)

        store.save_session(
            mode="classic",
            topic="modern idea",
            turns=[{"persona": "audrey", "speaker": "Dame Audrey", "content": "new", "round": 1}],
            transcript="# modern",
        )
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT audrey, claib FROM sessions WHERE topic = 'modern idea'"
            ).fetchone()
        self.assertEqual(row["audrey"], "new")
        self.assertIsNone(row["claib"])

    def test_migrates_v3_database_and_keeps_private_log(self):
        db = self.root / "v3.db"
        conn = sqlite3.connect(db)
        conn.execute(
            """
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                mode TEXT,
                topic TEXT,
                marlowe TEXT,
                priya TEXT,
                zero TEXT
            )
            """
        )
        conn.execute("CREATE TABLE private_log (id INTEGER PRIMARY KEY, response TEXT)")
        conn.execute(
            "INSERT INTO sessions (timestamp, mode, topic, marlowe, priya, zero) VALUES (?,?,?,?,?,?)",
            ("2026-02-02T00:00:00", "panel", "v3 topic", "m", "p", "z"),
        )
        conn.commit()
        conn.close()

        store = SessionStore(db, self.log)
        rows = store.recent()
        self.assertEqual(rows[0]["mode"], "panel")
        self.assertEqual([t["persona"] for t in rows[0]["turns"]], ["marlowe", "priya", "zero"])
        with sqlite3.connect(db) as check:
            tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("private_log", tables)

    def test_log_appends_jsonl_and_reads_legacy_lines(self):
        self.log.write_text(
            "2026-05-19T11:57:20 | giving a recursive improvement engine the ability to improve itself\n",
            encoding="utf-8",
        )
        store = SessionStore(self.root / "memory.db", self.log)
        store.append_event({"event": "session_end", "topic": "new topic"})
        entries = list(store.log_entries())
        self.assertEqual(entries[0]["legacy"], True)
        self.assertTrue(entries[0]["topic"].startswith("giving a recursive"))
        self.assertEqual(entries[1]["event"], "session_end")
        self.assertEqual(entries[1]["topic"], "new topic")
        raw = self.log.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(json.loads(raw[-1])["topic"], "new topic")

    def test_history_text_handles_empty_and_filled(self):
        store = SessionStore(self.root / "memory.db", self.log)
        self.assertEqual(store.history_text(), "No previous sessions on record.")
        store.save_session(
            mode="v3",
            topic="history topic",
            turns=[{"persona": "zero", "speaker": "Zero", "content": "the thing", "round": 1}],
        )
        text = store.history_text(limit=3)
        self.assertIn("history topic", text)
        self.assertIn("Zero: the thing", text)


if __name__ == "__main__":
    unittest.main()
