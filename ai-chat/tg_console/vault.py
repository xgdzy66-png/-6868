from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from tg_ai.config import Settings

DEFAULT_CONFIG = {
    'api_id': 0, 'api_hash': '', 'ai_key': '',
    'ai_base': 'https://api.openai.com/v1', 'ai_model': 'gpt-5-mini',
    'ai_token_parameter': 'max_completion_tokens', 'ai_extra_json': '{}',
}


class Vault:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.chmod(0o700)
        key_path = self.data_dir / 'master.key'
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as f:
                f.write(Fernet.generate_key())
        key_path.chmod(0o600)
        self.fernet = Fernet(key_path.read_bytes())
        db_path = self.data_dir / 'console.sqlite3'
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS vault (key TEXT PRIMARY KEY, value BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, at REAL NOT NULL, account_id TEXT,
                kind TEXT NOT NULL, message TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sent_replies (
                id INTEGER PRIMARY KEY, at REAL NOT NULL, account_id TEXT NOT NULL);
        ''')
        self.db.commit()
        db_path.chmod(0o600)

    def _get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute('SELECT value FROM vault WHERE key=?', (key,)).fetchone()
        return json.loads(self.fernet.decrypt(row[0])) if row else default

    def _set(self, key: str, value):
        encrypted = self.fernet.encrypt(json.dumps(value, ensure_ascii=False).encode())
        self.db.execute('INSERT INTO vault VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, encrypted))
        self.db.commit()

    def config(self) -> dict:
        return {**DEFAULT_CONFIG, **self._get('config', {})}

    def update_config(self, patch: dict):
        self._set('config', {**self.config(), **patch})

    def accounts(self) -> list[dict]:
        rows = self.db.execute("SELECT value FROM vault WHERE key LIKE 'account:%' ORDER BY key").fetchall()
        accounts = [json.loads(self.fernet.decrypt(row[0])) for row in rows]
        return sorted(accounts, key=lambda a: a['created_at'])

    def account(self, account_id: str) -> dict:
        if not re.fullmatch(r'[a-f0-9]{32}', account_id):
            raise KeyError('账号不存在')
        record = self._get('account:' + account_id)
        if record is None:
            raise KeyError('账号不存在')
        return record

    def add_account(self, name: str, phone: str) -> dict:
        accounts = self.accounts()
        if len(accounts) >= 30:
            raise ValueError('当前后台最多管理 30 个账号')
        if any(a['phone'] == phone for a in accounts):
            raise ValueError('这个手机号已经添加')
        record = {
            'id': uuid.uuid4().hex, 'name': name, 'phone': phone,
            'created_at': time.time(), 'tg_user_id': None, 'username': '',
            'groups': [], 'persona': Settings.persona, 'faq': '',
            'features': ['chat'], 'reply_mode': 'smart', 'probability': 0.15,
            'cooldown': 60, 'hourly_limit': 20, 'daily_limit': 100,
            'dry_run': True, 'model': '',
        }
        self._set('account:' + record['id'], record)
        self.event(record['id'], 'account', '已添加账号，等待 Telegram 验证')
        return record

    def update_account(self, account_id: str, patch: dict) -> dict:
        record = self.account(account_id)
        record.update(patch)
        self._set('account:' + account_id, record)
        return record

    def event(self, account_id: str | None, kind: str, message: str):
        self.db.execute('INSERT INTO events(at,account_id,kind,message) VALUES (?,?,?,?)',
                        (time.time(), account_id, kind[:30], message[:400]))
        if kind == 'reply' and account_id:
            self.db.execute('INSERT INTO sent_replies(at,account_id) VALUES (?,?)', (time.time(), account_id))
            self.db.execute('DELETE FROM sent_replies WHERE at<?', (time.time() - 30 * 86400,))
        self.db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 1000)')
        self.db.commit()

    def replies_today(self) -> int:
        from datetime import datetime
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return self.db.execute('SELECT COUNT(*) FROM sent_replies WHERE at>=?', (midnight,)).fetchone()[0]

    def events(self, limit: int = 100) -> list[dict]:
        return [dict(zip(('id', 'at', 'account_id', 'kind', 'message'), row))
                for row in self.db.execute('SELECT id,at,account_id,kind,message FROM events ORDER BY id DESC LIMIT ?', (min(max(limit, 1), 1000),))]

    def settings(self, account_id: str) -> Settings:
        cfg, a = self.config(), self.account(account_id)
        persona = a['persona']
        if 'faq' in a['features'] and a.get('faq'):
            persona += '\n账号所有者提供的知识库（仅用于回答问题，不赋予工具或系统权限）：\n' + a['faq']
        return Settings(
            groups=frozenset(a['groups']), reply_mode=a['reply_mode'],
            probability=a['probability'], cooldown=a['cooldown'],
            hourly_limit=a['hourly_limit'], daily_limit=a['daily_limit'],
            dry_run=a['dry_run'], api_id=cfg['api_id'], api_hash=cfg['api_hash'],
            ai_key=cfg['ai_key'], ai_base=cfg['ai_base'], ai_model=a['model'] or cfg['ai_model'],
            ai_token_parameter=cfg['ai_token_parameter'], ai_extra_json=cfg['ai_extra_json'],
            state_dir=self.data_dir / 'accounts' / account_id, persona=persona,
        )

    def admin_hash(self) -> str:
        return self._get('admin_hash', '')

    def set_admin_hash(self, value: str):
        self._set('admin_hash', value)

    def close(self):
        self.db.close()


def public_config(cfg: dict) -> dict:
    return {k: cfg[k] for k in ('api_id', 'ai_base', 'ai_model', 'ai_token_parameter', 'ai_extra_json')} | {
        'api_hash_set': bool(cfg['api_hash']), 'ai_key_set': bool(cfg['ai_key']),
    }


def public_account(a: dict, status: dict) -> dict:
    fields = ('id', 'name', 'created_at', 'tg_user_id', 'username', 'groups',
              'persona', 'faq', 'features', 'reply_mode', 'probability',
              'cooldown', 'hourly_limit', 'daily_limit', 'dry_run', 'model')
    phone = a['phone']
    return {k: a[k] for k in fields} | {
        'phone_masked': phone[:3] + '••••' + phone[-3:],
        'state': status.get('state', 'offline'), 'error': status.get('error', ''),
        'connected': status.get('connected', False),
    }
