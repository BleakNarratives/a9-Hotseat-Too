"""Unified, backward-compatible persistence for Hotseat sessions.

The legacy trees wrote several different SQLite layouts:

* classic: ``sessions(timestamp, topic, audrey, claib, vertical)`` plus ``topics``
* v3:      ``sessions(timestamp, mode, topic, marlowe, priya, zero)`` plus ``private_log``
* v2:      JSON transcripts under ``~/hotseat_v2/logs`` (now archived)

This store keeps one normalized schema (a JSON ``turns`` column plus rendered
``transcript``) and migrates existing databases in place: missing columns are
added with ``ALTER TABLE`` and legacy persona columns continue to be populated so
older tools keep working. Nothing is dropped or rewritten destructively.

The session log is append-only JSONL, and the reader still understands the legacy
``timestamp | topic`` lines.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SESSION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("timestamp", "TEXT"),
    ("mode", "TEXT DEFAULT 'classic'"),
    ("topic", "TEXT"),
    ("turns", "TEXT"),
    ("transcript", "TEXT"),
    ("provider", "TEXT"),
    ("model", "TEXT"),
)

LEGACY_PERSONA_COLUMNS: tuple[str, ...] = (
    "audrey",
    "claib",
    "vertical",
    "marlowe",
    "priya",
    "zero",
)

SPEAKER_NAMES = {
    "audrey": "Dame Audrey",
    "claib": "Claib",
    "vertical": "Vertical AI",
    "marlowe": "Marlowe",
    "priya": "Priya Nair",
    "zero": "Zero",
}


class StorageError(RuntimeError):
    """A user-safe persistence failure."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_turn(turn: Any) -> dict[str, Any] | None:
    if not isinstance(turn, Mapping) or not turn.get("content"):
        return None
    return {
        "persona": str(turn.get("persona", "unknown")),
        "speaker": str(turn.get("speaker") or turn.get("persona") or "unknown"),
        "content": str(turn.get("content", "")),
        "round": int(turn.get("round", 0) or 0),
        "model": turn.get("model"),
    }


def _session_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    raw_turns = record.get("turns")
    if raw_turns:
        try:
            parsed = json.loads(raw_turns)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            turns = [turn for turn in (_normalize_turn(t) for t in parsed) if turn]
    if not turns:
        turns = _turns_from_legacy(record)
    return {
        "id": record.get("id"),
        "timestamp": record.get("timestamp"),
        "mode": record.get("mode") or "classic",
        "topic": record.get("topic"),
        "turns": turns,
        "transcript": record.get("transcript"),
        "provider": record.get("provider"),
        "model": record.get("model"),
    }


def _turns_from_legacy(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for column in LEGACY_PERSONA_COLUMNS:
        content = row.get(column)
        if content:
            turns.append(
                {
                    "persona": column,
                    "speaker": SPEAKER_NAMES.get(column, column.title()),
                    "content": str(content),
                    "round": len(turns) + 1,
                    "model": None,
                }
            )
    return turns


class SessionStore:
    """SQLite session memory plus an append-only event log."""

    def __init__(self, db_path: str | Path, session_log: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser()
        self.session_log = Path(session_log).expanduser() if session_log else None
        self._log_lock = threading.Lock()
        self._initialized = False
        self._init_lock = threading.Lock()

    # ── setup ─────────────────────────────────────────────────────────────────
    def initialize(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                if self.session_log is not None:
                    self.session_log.parent.mkdir(parents=True, exist_ok=True)
                with self._session() as conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS sessions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT,
                            mode TEXT DEFAULT 'classic',
                            topic TEXT,
                            turns TEXT,
                            transcript TEXT,
                            provider TEXT,
                            model TEXT
                        )
                        """
                    )
                    self._migrate(conn)
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS sessions_timestamp_idx "
                        "ON sessions(timestamp)"
                    )
                    conn.commit()
            except (OSError, sqlite3.Error) as exc:
                raise StorageError(f"Cannot initialize session store at {self.db_path}: {exc}") from exc
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _session(self):
        """Yield a connection and always close it; sqlite3's context manager only commits."""

        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _columns(conn: sqlite3.Connection) -> set[str]:
        return {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}

    def _migrate(self, conn: sqlite3.Connection) -> None:
        existing = self._columns(conn)
        for name, declaration in SESSION_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {declaration}")

    # ── writes ────────────────────────────────────────────────────────────────
    def save_session(
        self,
        *,
        mode: str,
        topic: str,
        turns: Sequence[Mapping[str, Any]],
        transcript: str = "",
        provider: str | None = None,
        model: str | None = None,
        timestamp: str | None = None,
    ) -> int:
        """Persist one finished session and return its row id."""

        self.initialize()
        normalized = [turn for turn in (_normalize_turn(t) for t in turns) if turn]
        values: dict[str, Any] = {
            "timestamp": timestamp or _now(),
            "mode": mode,
            "topic": topic,
            "turns": json.dumps(normalized, ensure_ascii=False),
            "transcript": transcript,
            "provider": provider,
            "model": model,
        }
        for turn in normalized:
            column = turn["persona"]
            if column in LEGACY_PERSONA_COLUMNS and column not in values:
                values[column] = turn["content"]

        try:
            with self._session() as conn:
                self._migrate(conn)
                columns = self._columns(conn)
                usable = {k: v for k, v in values.items() if k in columns}
                placeholders = ", ".join("?" for _ in usable)
                sql = f"INSERT INTO sessions ({', '.join(usable)}) VALUES ({placeholders})"
                cursor = conn.execute(sql, tuple(usable.values()))
                session_id = int(cursor.lastrowid)
                conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot save session: {exc}") from exc
        return session_id

    def append_event(self, event: Mapping[str, Any]) -> None:
        """Append a JSONL event. Never raises; logging must not break a session."""

        if self.session_log is None:
            return
        record = {"timestamp": _now(), **dict(event)}
        line = json.dumps(record, ensure_ascii=False, default=str)
        try:
            with self._log_lock:
                self.session_log.parent.mkdir(parents=True, exist_ok=True)
                with self.session_log.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError:
            return

    # ── reads ─────────────────────────────────────────────────────────────────
    def recent(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return the most recent sessions, newest first."""

        self.initialize()
        limit = max(1, min(int(limit), 100))
        try:
            with self._session() as conn:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot read sessions: {exc}") from exc

        return [_session_from_record({key: row[key] for key in row.keys()}) for row in rows]

    def get(self, session_id: int | str) -> dict[str, Any] | None:
        """Load one session by row id (the integer memory id)."""

        self.initialize()
        try:
            numeric = int(session_id)
        except (TypeError, ValueError):
            return None
        try:
            with self._session() as conn:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE id = ?", (numeric,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot read session {session_id}: {exc}") from exc
        return _session_from_record({key: row[key] for key in row.keys()}) if row else None

    def append_turns(
        self,
        session_id: int | str,
        *,
        turns: Sequence[Mapping[str, Any]],
        transcript: str = "",
        timestamp: str | None = None,
    ) -> None:
        """Rewrite a thread's turns and transcript after a follow-up pass."""

        self.initialize()
        try:
            numeric = int(session_id)
        except (TypeError, ValueError) as exc:
            raise StorageError(f"Invalid session id: {session_id}") from exc
        normalized = [turn for turn in (_normalize_turn(t) for t in turns) if turn]
        values: dict[str, Any] = {
            "turns": json.dumps(normalized, ensure_ascii=False),
            "transcript": transcript,
        }
        if timestamp:
            values["timestamp"] = timestamp
        for turn in normalized:
            column = turn["persona"]
            if column in LEGACY_PERSONA_COLUMNS and column not in values:
                values[column] = turn["content"]
        try:
            with self._session() as conn:
                self._migrate(conn)
                columns = self._columns(conn)
                usable = {key: value for key, value in values.items() if key in columns}
                assignments = ", ".join(f"{key} = ?" for key in usable)
                conn.execute(
                    f"UPDATE sessions SET {assignments} WHERE id = ?",
                    (*usable.values(), numeric),
                )
                conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot append to session {session_id}: {exc}") from exc

    def history_text(self, limit: int = 5) -> str:
        sessions = self.recent(limit=limit)
        if not sessions:
            return "No previous sessions on record."
        lines = ["--- RECENT HOT SEAT SESSIONS ---"]
        for session in sessions:
            topic = (session.get("topic") or "(untitled)").strip()
            timestamp = str(session.get("timestamp") or "")[:10]
            lines.append(f"[{timestamp}] ({session.get('mode')}) {topic}")
            turns = session.get("turns") or []
            if turns:
                last = turns[-1]
                snippet = " ".join(str(last.get("content", "")).split())
                if snippet:
                    lines.append(f"  → {last.get('speaker', 'unknown')}: {snippet[:120]}")
        return "\n".join(lines)

    def log_entries(self) -> Iterable[dict[str, Any]]:
        """Yield parsed session-log entries, including legacy pipe lines."""

        if self.session_log is None or not self.session_log.is_file():
            return []
        entries: list[dict[str, Any]] = []
        try:
            for line in self.session_log.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("{"):
                    try:
                        parsed = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(parsed, dict):
                        entries.append(parsed)
                    continue
                if "|" in line:
                    timestamp, topic = line.split("|", 1)
                    entries.append(
                        {
                            "event": "session_end",
                            "timestamp": timestamp.strip(),
                            "topic": topic.strip(),
                            "legacy": True,
                        }
                    )
        except OSError:
            return []
        return entries
