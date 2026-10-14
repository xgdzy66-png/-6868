from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass

COOKIE = 'tg_atelier_admin'


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError('管理员密码至少 12 个字符')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, wanted = encoded.split('$')
        if algorithm != 'scrypt':
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest, base64.b64decode(wanted))
    except (ValueError, TypeError):
        return False


@dataclass
class Session:
    csrf: str
    expires: float


class Security:
    def __init__(self, vault, clock=time.time):
        self.vault, self.clock = vault, clock
        self.sessions: dict[str, Session] = {}
        self.attempts = defaultdict(list)

    def login(self, password: str, address: str) -> tuple[str, Session]:
        now = self.clock()
        self.attempts[address] = [at for at in self.attempts[address] if now - at < 300]
        if len(self.attempts[address]) >= 5:
            raise ValueError('登录尝试过多，请 5 分钟后重试')
        self.attempts[address].append(now)
        if not verify_password(password, self.vault.admin_hash()):
            raise ValueError('管理员密码不正确')
        self.attempts[address].clear()
        self.sessions = {token: value for token, value in self.sessions.items() if value.expires > now}
        if len(self.sessions) >= 50:
            oldest = min(self.sessions, key=lambda token: self.sessions[token].expires)
            self.sessions.pop(oldest)
        token = secrets.token_urlsafe(32)
        session = Session(secrets.token_urlsafe(32), now + 8 * 3600)
        self.sessions[token] = session
        return token, session

    def session(self, token: str | None) -> Session | None:
        value = self.sessions.get(token or '')
        if value and value.expires > self.clock():
            return value
        if token:
            self.sessions.pop(token, None)
        return None

    def logout(self, token: str | None):
        self.sessions.pop(token or '', None)

    def valid_csrf(self, session: Session, csrf: str | None) -> bool:
        return bool(csrf and hmac.compare_digest(session.csrf, csrf))
