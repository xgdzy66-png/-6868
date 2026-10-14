from __future__ import annotations

import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY, room TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT NOT NULL, at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS history_room ON history(room, id);
        CREATE TABLE IF NOT EXISTS seen (
            key TEXT PRIMARY KEY, at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL, at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS replies_group ON replies(group_id, at);
        CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        self.db.commit()
        path.chmod(0o600)

    def close(self):
        self.db.close()

    def get(self, key: str, default: str = '') -> str:
        row = self.db.execute('SELECT value FROM prefs WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set(self, key: str, value: str):
        self.db.execute('INSERT INTO prefs VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
        self.db.commit()

    def claim(self, key: str, now: float) -> bool:
        cursor = self.db.execute('INSERT OR IGNORE INTO seen VALUES (?,?)', (key, now))
        self.db.commit()
        return cursor.rowcount == 1

    def add(self, room: str, role: str, content: str, now: float, limit: int):
        self.db.execute('INSERT INTO history(room,role,content,at) VALUES (?,?,?,?)', (room, role, content, now))
        self.db.execute('DELETE FROM history WHERE room=? AND id NOT IN (SELECT id FROM history WHERE room=? ORDER BY id DESC LIMIT ?)', (room, room, limit))
        self.db.commit()

    def history(self, room: str) -> list[dict]:
        return [{'role': r, 'content': c} for r, c in self.db.execute('SELECT role,content FROM history WHERE room=? ORDER BY id', (room,))]

    def clear(self, group: int):
        self.db.execute('DELETE FROM history WHERE room LIKE ?', (f'{group}:%',))
        self.db.commit()

    def prune(self, now: float, retention_hours: int):
        self.db.execute('DELETE FROM history WHERE at<?', (now - retention_hours * 3600,))
        self.db.execute('DELETE FROM seen WHERE at<?', (now - 7 * 86400,))
        self.db.execute('DELETE FROM replies WHERE at<?', (now - 86400,))
        self.db.commit()

    def record_reply(self, group: int, now: float):
        self.db.execute('INSERT INTO replies(group_id,at) VALUES (?,?)', (group, now))
        self.db.commit()

    def limits(self, group: int, now: float) -> tuple[float, int, int]:
        row = self.db.execute('SELECT MAX(at), SUM(CASE WHEN at>? THEN 1 ELSE 0 END), COUNT(*) FROM replies WHERE group_id=? AND at>?', (now - 3600, group, now - 86400)).fetchone()
        return (row[0] if row[0] is not None else -1e30, row[1] or 0, row[2] or 0)
