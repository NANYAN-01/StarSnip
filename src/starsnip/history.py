"""Local history store (sqlite3 + PNG thumbnails), no external deps."""

import datetime
import json
import os
import sqlite3
import threading
import uuid

from . import paths


def default_base_dir() -> str:
    return paths.data_home()


class History:
    def __init__(self, base_dir: str = None, keep: int = 500):
        self.base_dir = base_dir or default_base_dir()
        self.thumbs_dir = os.path.join(self.base_dir, "thumbs")
        os.makedirs(self.thumbs_dir, exist_ok=True)
        self.db_path = os.path.join(self.base_dir, "history.db")
        self.keep = max(20, int(keep))
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                mode TEXT NOT NULL,
                model TEXT NOT NULL,
                elapsed_ms INTEGER,
                text TEXT NOT NULL,
                thumb_path TEXT,
                meta TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_history_created
                ON history(created_at DESC);
        """)
        self._conn.commit()

    def add(self, source: str, mode: str, model: str, elapsed_ms: int,
            text: str, thumb_png: bytes = None, meta: dict = None) -> int:
        thumb_rel = None
        if thumb_png:
            thumb_rel = "thumbs/%s.png" % uuid.uuid4().hex
            with open(os.path.join(self.base_dir, thumb_rel), "wb") as f:
                f.write(thumb_png)
        created = datetime.datetime.now().isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO history (created_at, source, mode, model,"
                " elapsed_ms, text, thumb_path, meta)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (created, source, mode, model, int(elapsed_ms or 0), text,
                 thumb_rel, json.dumps(meta or {}, ensure_ascii=False)))
            self._conn.commit()
            row_id = cur.lastrowid
            self._prune_locked()
        return row_id

    def search(self, keyword: str = "", limit: int = 200) -> list:
        sql = "SELECT id, created_at, source, mode, model, elapsed_ms, text, thumb_path FROM history"
        args = []
        if keyword:
            sql += " WHERE text LIKE ? OR model LIKE ?"
            like = "%" + keyword + "%"
            args = [like, like]
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def get(self, row_id: int):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM history WHERE id = ?", (row_id,)).fetchone()
        return dict(row) if row else None

    def delete(self, row_id: int) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT thumb_path FROM history WHERE id = ?", (row_id,)).fetchone()
            self._conn.execute("DELETE FROM history WHERE id = ?", (row_id,))
            self._conn.commit()
        if row and row["thumb_path"]:
            self._remove_file(row["thumb_path"])

    def clear(self) -> None:
        with self._lock:
            rows = self._conn.execute("SELECT thumb_path FROM history").fetchall()
            self._conn.execute("DELETE FROM history")
            self._conn.commit()
        for row in rows:
            if row["thumb_path"]:
                self._remove_file(row["thumb_path"])

    def prune(self) -> None:
        with self._lock:
            self._prune_locked()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------- internals ----------
    def _prune_locked(self) -> None:
        rows = self._conn.execute(
            "SELECT id, thumb_path FROM history ORDER BY id DESC LIMIT -1 OFFSET ?",
            (self.keep,)).fetchall()
        for row in rows:
            self._conn.execute("DELETE FROM history WHERE id = ?", (row["id"],))
            if row["thumb_path"]:
                self._remove_file(row["thumb_path"])
        if rows:
            self._conn.commit()

    def _remove_file(self, rel_path: str) -> None:
        try:
            os.remove(os.path.join(self.base_dir, rel_path))
        except OSError:
            pass

    def thumb_file(self, rel_path: str) -> str:
        return os.path.join(self.base_dir, rel_path) if rel_path else ""
