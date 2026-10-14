"""Async lifecycle manager for the private multi-account Telegram console.

This module deliberately knows nothing about the web administrator session.  It only
accepts account ids already authorized by the server layer, and never serializes an
OTP, a two-factor password, or a Telethon session into the Vault.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from tg_ai.ai import ChatAI
from tg_ai.config import ConfigError, Settings
from tg_ai.engine import Engine, Message
from tg_ai.storage import Store


class ManagerError(RuntimeError):
    """An error whose ``message`` is safe to return from the server API.

    Callers must not expose arbitrary third-party exception text.  Every message
    generated here is a static Chinese status string (or a checked configuration
    error from :mod:`tg_ai.config`, which is also static).
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass
class _Runtime:
    state: str = 'offline'
    error: str = ''
    connected: bool = False
    client: Any | None = None
    settings: Settings | None = None
    code_hash: str | None = None
    code_expires_at: float = 0.0
    ai: ChatAI | None = None
    store: Store | None = None
    engine: Engine | None = None
    handler: Callable[..., Awaitable[None]] | None = None
    event_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    worker_active: bool = False
    demo_preview: tuple[int, str] | None = None


class Manager:
    """Manage local Telethon sessions and independent AI workers for Vault accounts.

    The object is intentionally event-loop local: create it once in the FastAPI
    application lifespan and invoke all async methods on that same loop.
    """

    MAX_ACCOUNTS = 30
    BATCH_CONCURRENCY = 2
    CODE_TTL_SECONDS = 10 * 60

    _ERROR_MESSAGES = {
        'PhoneCodeInvalidError': '验证码错误，请重新输入',
        'PhoneCodeExpiredError': '验证码已过期，请重新获取',
        'SessionPasswordNeededError': '需要两步验证密码',
        'PasswordHashInvalidError': '两步验证密码错误',
        'FloodWaitError': '操作过于频繁，请稍后再试',
        'AuthKeyUnregisteredError': '登录会话已失效，请重新登录',
        'SessionRevokedError': '登录会话已失效，请重新登录',
        'UserDeactivatedError': 'Telegram 账号已停用，无法登录',
        'UserDeactivatedBanError': 'Telegram 账号已停用，无法登录',
    }

    def __init__(self, vault, demo: bool = False, client_factory=None):
        self.vault = vault
        self.demo = bool(demo)
        self.client_factory = client_factory or self._telethon_client
        self._runtimes: dict[str, _Runtime] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # Engine normally has a two-slot semaphore per instance.  Console workers
        # share this one so multiple accounts cannot multiply AI request pressure.
        self._ai_slots = asyncio.Semaphore(self.BATCH_CONCURRENCY)
        self._identity_lock = asyncio.Lock()
        # Claiming a group's worker must be atomic across accounts, not merely
        # under each account lock. Profile lookup and handler install both await.
        self._start_lock = asyncio.Lock()

    @staticmethod
    def _telethon_client(*args, **kwargs):
        try:
            from telethon import TelegramClient
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise ManagerError('Telegram 客户端不可用，请检查本机依赖') from exc
        return TelegramClient(*args, **kwargs)

    @staticmethod
    async def _maybe_await(value):
        if inspect.isawaitable(value):
            return await value
        return value

    def _runtime(self, account_id: str) -> _Runtime:
        return self._runtimes.setdefault(account_id, _Runtime())

    def _lock(self, account_id: str) -> asyncio.Lock:
        return self._locks.setdefault(account_id, asyncio.Lock())

    def _account(self, account_id: str) -> dict:
        try:
            account = self.vault.account(account_id)
        except (KeyError, ValueError, TypeError) as exc:
            raise ManagerError('账号不存在') from exc
        if not isinstance(account, dict):
            raise ManagerError('账号配置无效，请检查设置')
        return account

    def _check_capacity(self) -> None:
        # Vault also enforces this on creation.  Keeping the guard here prevents a
        # malformed/imported Vault from causing unbounded local clients.
        try:
            count = len(self.vault.accounts())
        except Exception as exc:
            raise ManagerError('无法读取本机账号配置') from exc
        if count > self.MAX_ACCOUNTS:
            raise ManagerError('当前后台最多管理 30 个账号')

    def _settings(self, account_id: str) -> Settings:
        try:
            settings = self.vault.settings(account_id)
        except ConfigError as exc:
            # ConfigError messages are fixed validation messages, never input text.
            raise ManagerError(str(exc)) from exc
        except (KeyError, ValueError, TypeError) as exc:
            raise ManagerError('账号配置无效，请检查设置') from exc
        if not isinstance(settings, Settings):
            raise ManagerError('账号配置无效，请检查设置')
        return settings

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
        if isinstance(exc, ManagerError):
            return exc.message
        for cls in type(exc).__mro__:
            message = Manager._ERROR_MESSAGES.get(cls.__name__)
            if message:
                return message
        return '操作失败，请稍后重试'

    def _audit(self, account_id: str | None, kind: str, message: str) -> None:
        """Best-effort audit logging with only manager-owned static messages."""
        try:
            self.vault.event(account_id, kind, message)
        except Exception:
            # A closed/local audit database must not leave an active Telegram worker
            # running merely because a non-security-critical audit insertion failed.
            pass

    @staticmethod
    def _result(runtime: _Runtime, message: str) -> dict:
        return {'state': runtime.state, 'message': message}

    def _expire_code(self, runtime: _Runtime) -> bool:
        if runtime.code_hash and time.monotonic() >= runtime.code_expires_at:
            runtime.code_hash = None
            runtime.code_expires_at = 0.0
            if runtime.state == 'code':
                runtime.state = 'offline'
                runtime.error = '验证码已过期，请重新获取'
            return True
        return False

    def statuses(self) -> dict[str, dict]:
        """Return cached local state only; this method never contacts Telegram."""
        try:
            accounts = self.vault.accounts()
        except Exception:
            return {}
        result = {}
        for account in accounts[:self.MAX_ACCOUNTS]:
            account_id = account.get('id') if isinstance(account, dict) else None
            if not isinstance(account_id, str):
                continue
            runtime = self._runtimes.get(account_id)
            if runtime is None:
                result[account_id] = {'state': 'offline', 'error': '', 'connected': False}
                continue
            self._expire_code(runtime)
            result[account_id] = {
                'state': runtime.state,
                'error': runtime.error,
                'connected': runtime.connected,
            }
        return result

    def _require_demo_account(self, account: dict) -> None:
        if not (account.get('demo') is True or account.get('is_demo') is True):
            raise ManagerError('演示模式仅可操作预置演示账号')

    @staticmethod
    def _is_authorized_state(runtime: _Runtime) -> bool:
        return runtime.state in ('ready', 'running') and runtime.client is not None and runtime.connected

    async def _disconnect_client(self, runtime: _Runtime) -> None:
        client = runtime.client
        runtime.client = None
        runtime.connected = False
        if client is not None:
            try:
                await self._maybe_await(client.disconnect())
            except Exception:
                # Disconnect is local cleanup.  Do not surface a third-party detail.
                pass

    @staticmethod
    def _secure_session_files(settings: Settings) -> None:
        try:
            settings.state_dir.mkdir(parents=True, exist_ok=True)
            settings.state_dir.chmod(0o700)
            for path in settings.state_dir.glob('account.session*'):
                if path.is_file():
                    path.chmod(0o600)
        except OSError:
            # The subsequent client/store operation yields the appropriately safe
            # local failure.  Never delete a session as a recovery action.
            pass

    async def _ensure_client(self, account_id: str, runtime: _Runtime) -> Settings:
        settings = runtime.settings or self._settings(account_id)
        if settings.api_id <= 0 or not settings.api_hash:
            raise ManagerError('请先配置 Telegram API 凭据')
        runtime.settings = settings
        self._secure_session_files(settings)
        if runtime.client is None:
            try:
                runtime.client = self.client_factory(
                    str(settings.state_dir / 'account'), settings.api_id, settings.api_hash,
                    flood_sleep_threshold=0, request_retries=0,
                    auto_reconnect=True, connection_retries=5,
                )
            except ManagerError:
                raise
            except Exception as exc:
                raise ManagerError('Telegram 客户端初始化失败') from exc
        try:
            await self._maybe_await(runtime.client.connect())
            runtime.connected = True
            self._secure_session_files(settings)
            return settings
        except Exception as exc:
            runtime.connected = False
            runtime.state = 'error'
            runtime.error = self._safe_error(exc)
            self._audit(account_id, 'connection', 'Telegram 连接失败')
            raise ManagerError(runtime.error) from None

    async def _not_authorized(self, account_id: str, account: dict, runtime: _Runtime) -> None:
        await self._disconnect_client(runtime)
        if account.get('tg_user_id') is not None:
            runtime.state = 'error'
            runtime.error = '登录会话已失效，请重新登录'
            self._audit(account_id, 'connection', '已保存的 Telegram 登录会话失效')
        else:
            runtime.state = 'offline'
            runtime.error = '当前会话尚未登录，请先完成验证码验证'
        raise ManagerError(runtime.error)

    async def _require_authorized(self, account_id: str, account: dict, runtime: _Runtime) -> None:
        if not self._is_authorized_state(runtime):
            raise ManagerError('请先连接已保存的登录会话')
        client = runtime.client
        assert client is not None  # narrowed by _is_authorized_state above
        try:
            authorized = await self._maybe_await(client.is_user_authorized())
        except Exception as exc:
            runtime.state = 'error'
            runtime.error = self._safe_error(exc)
            await self._disconnect_client(runtime)
            self._audit(account_id, 'connection', 'Telegram 授权状态检查失败')
            raise ManagerError(runtime.error) from None
        if not authorized:
            await self._not_authorized(account_id, account, runtime)

    async def _finish_authorization(
        self, account_id: str, account: dict, runtime: _Runtime, audit_message: str,
    ) -> None:
        """Persist only safe Telegram profile metadata and enforce one user once."""
        client = runtime.client
        assert client is not None  # all callers have connected before profile lookup
        try:
            me = await self._maybe_await(client.get_me())
        except Exception as exc:
            runtime.state = 'error'
            runtime.error = self._safe_error(exc)
            await self._disconnect_client(runtime)
            self._audit(account_id, 'login', '读取 Telegram 账号信息失败')
            raise ManagerError(runtime.error) from None
        if me is None or not getattr(me, 'id', None):
            runtime.state = 'error'
            runtime.error = '无法读取 Telegram 账号信息'
            await self._disconnect_client(runtime)
            self._audit(account_id, 'login', '无法读取 Telegram 账号信息')
            raise ManagerError(runtime.error)
        if bool(getattr(me, 'bot', False)):
            runtime.state = 'error'
            runtime.error = '当前会话是 Bot，请使用普通账号登录'
            await self._disconnect_client(runtime)
            self._audit(account_id, 'login', '拒绝使用 Bot 会话')
            raise ManagerError(runtime.error)

        tg_user_id = int(me.id)
        try:
            async with self._identity_lock:
                for other in self.vault.accounts():
                    if other.get('id') == account_id:
                        continue
                    if other.get('tg_user_id') is not None and str(other.get('tg_user_id')) == str(tg_user_id):
                        runtime.state = 'error'
                        runtime.error = '该 Telegram 账号已在控制台中存在'
                        await self._disconnect_client(runtime)
                        self._audit(account_id, 'login', '拒绝重复的 Telegram 账号')
                        raise ManagerError(runtime.error)
                # Do not save display names, phone, passwords, OTPs, or any session
                # material.  Vault already owns the non-secret account metadata.
                self.vault.update_account(account_id, {
                    'tg_user_id': tg_user_id,
                    'username': getattr(me, 'username', '') or '',
                })
        except ManagerError:
            raise
        except Exception:
            runtime.state = 'error'
            runtime.error = '无法保存 Telegram 账号信息'
            await self._disconnect_client(runtime)
            self._audit(account_id, 'login', '保存 Telegram 账号信息失败')
            raise ManagerError(runtime.error) from None

        runtime.code_hash = None
        runtime.code_expires_at = 0.0
        runtime.state = 'ready'
        runtime.error = ''
        runtime.connected = True
        self._secure_session_files(runtime.settings or self._settings(account_id))
        self._audit(account_id, 'login', audit_message)

    async def request_code(self, account_id: str) -> dict:
        self._check_capacity()
        account = self._account(account_id)
        if self.demo:
            self._require_demo_account(account)
            raise ManagerError('演示模式不支持 Telegram 登录')
        async with self._lock(account_id):
            runtime = self._runtime(account_id)
            self._expire_code(runtime)
            await self._ensure_client(account_id, runtime)
            client = runtime.client
            assert client is not None  # _ensure_client initializes it or raises
            try:
                authorized = await self._maybe_await(client.is_user_authorized())
            except Exception as exc:
                runtime.state = 'error'
                runtime.error = self._safe_error(exc)
                await self._disconnect_client(runtime)
                self._audit(account_id, 'connection', 'Telegram 授权状态检查失败')
                raise ManagerError(runtime.error) from None
            if authorized:
                await self._finish_authorization(account_id, account, runtime, '已连接已授权的 Telegram 会话')
                return self._result(runtime, '已连接已授权会话')
            if runtime.state == 'code' and runtime.code_hash:
                return self._result(runtime, '验证码已发送，请在十分钟内验证')
            try:
                sent = await self._maybe_await(client.send_code_request(account['phone']))
                code_hash = getattr(sent, 'phone_code_hash', None)
                if not isinstance(code_hash, str) or not code_hash:
                    raise ValueError('missing phone code hash')
            except Exception as exc:
                runtime.state = 'error'
                runtime.error = self._safe_error(exc)
                self._audit(account_id, 'login', '请求 Telegram 验证码失败')
                raise ManagerError(runtime.error) from None
            runtime.code_hash = code_hash
            runtime.code_expires_at = time.monotonic() + self.CODE_TTL_SECONDS
            runtime.state = 'code'
            runtime.error = ''
            self._audit(account_id, 'login', '已请求 Telegram 验证码')
            return self._result(runtime, '验证码已发送，请在十分钟内验证')

    async def verify_code(self, account_id: str, code: str) -> dict:
        self._check_capacity()
        account = self._account(account_id)
        if self.demo:
            self._require_demo_account(account)
            raise ManagerError('演示模式不支持 Telegram 登录')
        async with self._lock(account_id):
            runtime = self._runtime(account_id)
            expired = self._expire_code(runtime)
            if expired:
                raise ManagerError('验证码已过期，请重新获取')
            if runtime.state != 'code' or not runtime.code_hash:
                raise ManagerError('请先获取验证码')
            if runtime.client is None or not runtime.connected:
                runtime.state = 'offline'
                runtime.error = '验证码会话已断开，请重新获取验证码'
                runtime.code_hash = None
                runtime.code_expires_at = 0.0
                raise ManagerError(runtime.error)
            try:
                await self._maybe_await(runtime.client.sign_in(
                    phone=account['phone'], code=code, phone_code_hash=runtime.code_hash,
                ))
            except Exception as exc:
                message = self._safe_error(exc)
                if message == '需要两步验证密码':
                    # The code hash is no longer needed once Telegram asks for 2FA.
                    runtime.code_hash = None
                    runtime.code_expires_at = 0.0
                    runtime.state = 'password'
                    runtime.error = ''
                    self._audit(account_id, 'login', 'Telegram 登录需要两步验证')
                    return self._result(runtime, message)
                if message == '验证码错误，请重新输入':
                    runtime.state = 'code'
                    runtime.error = message
                elif message == '验证码已过期，请重新获取':
                    runtime.code_hash = None
                    runtime.code_expires_at = 0.0
                    runtime.state = 'offline'
                    runtime.error = message
                else:
                    runtime.state = 'error'
                    runtime.error = message
                self._audit(account_id, 'login', 'Telegram 验证码验证失败')
                raise ManagerError(message) from None
            await self._finish_authorization(account_id, account, runtime, '已完成 Telegram 验证码登录')
            return self._result(runtime, 'Telegram 登录成功')

    async def verify_password(self, account_id: str, password: str) -> dict:
        self._check_capacity()
        account = self._account(account_id)
        if self.demo:
            self._require_demo_account(account)
            raise ManagerError('演示模式不支持 Telegram 登录')
        async with self._lock(account_id):
            runtime = self._runtime(account_id)
            if runtime.state != 'password' or runtime.client is None or not runtime.connected:
                raise ManagerError('当前无需两步验证，请先完成验证码登录')
            try:
                # password deliberately remains only a stack-local argument.
                await self._maybe_await(runtime.client.sign_in(password=password))
            except Exception as exc:
                message = self._safe_error(exc)
                if message == '两步验证密码错误':
                    runtime.state = 'password'
                    runtime.error = message
                else:
                    runtime.state = 'error'
                    runtime.error = message
                self._audit(account_id, 'login', 'Telegram 两步验证失败')
                raise ManagerError(message) from None
            await self._finish_authorization(account_id, account, runtime, '已完成 Telegram 两步验证登录')
            return self._result(runtime, 'Telegram 登录成功')

    async def connect(self, account_id: str) -> dict:
        self._check_capacity()
        account = self._account(account_id)
        async with self._lock(account_id):
            runtime = self._runtime(account_id)
            if self.demo:
                self._require_demo_account(account)
                runtime.state = 'ready'
                runtime.error = ''
                runtime.connected = True
                self._audit(account_id, 'connection', '演示账号已模拟连接')
                return self._result(runtime, '演示账号已连接（未连接 Telegram）')
            await self._ensure_client(account_id, runtime)
            client = runtime.client
            assert client is not None  # _ensure_client initializes it or raises
            try:
                authorized = await self._maybe_await(client.is_user_authorized())
            except Exception as exc:
                runtime.state = 'error'
                runtime.error = self._safe_error(exc)
                await self._disconnect_client(runtime)
                self._audit(account_id, 'connection', 'Telegram 授权状态检查失败')
                raise ManagerError(runtime.error) from None
            if not authorized:
                await self._not_authorized(account_id, account, runtime)
            await self._finish_authorization(account_id, account, runtime, '已连接保存的 Telegram 会话')
            return self._result(runtime, '已连接保存的登录会话')

    async def groups(self, account_id: str) -> list[dict]:
        account = self._account(account_id)
        async with self._lock(account_id):
            runtime = self._runtime(account_id)
            if self.demo:
                self._require_demo_account(account)
                if runtime.state not in ('ready', 'running'):
                    raise ManagerError('请先连接演示账号')
                supplied = account.get('demo_groups', account.get('groups', []))
                result = []
                for group in supplied:
                    if isinstance(group, dict) and isinstance(group.get('id'), int):
                        result.append({'id': group['id'], 'title': str(group.get('title') or '演示群组')})
                    elif isinstance(group, int):
                        result.append({'id': group, 'title': '演示群组'})
                return result
            await self._require_authorized(account_id, account, runtime)
            client = runtime.client
            assert client is not None  # _require_authorized keeps a live client
            result = []
            try:
                async for dialog in client.iter_dialogs():
                    if getattr(dialog, 'is_group', False):
                        result.append({'id': int(dialog.id), 'title': str(getattr(dialog, 'name', '') or '')})
            except Exception as exc:
                runtime.state = 'error'
                runtime.error = self._safe_error(exc)
                await self._disconnect_client(runtime)
                self._audit(account_id, 'groups', '读取 Telegram 群列表失败')
                raise ManagerError(runtime.error) from None
            return result

    def _has_running_overlap(self, account_id: str, groups: frozenset[int]) -> bool:
        for other_id, runtime in self._runtimes.items():
            if other_id == account_id:
                continue
            # State alone is insufficient during/after a stop.  A conflict exists
            # only for another running account with a live worker/simulation.
            if runtime.state != 'running' or not runtime.worker_active or runtime.settings is None:
                continue
            if groups.intersection(runtime.settings.groups):
                return True
        return False

    async def _remove_handler(self, runtime: _Runtime) -> None:
        if runtime.client is not None and runtime.handler is not None:
            try:
                await self._maybe_await(runtime.client.remove_event_handler(runtime.handler))
            except Exception:
                pass
        runtime.handler = None

    async def _cancel_event_tasks(self, runtime: _Runtime) -> None:
        # Never await or cancel the task which called stop itself; doing so makes a
        # handler-triggered shutdown deadlock.  It will drop out via its callback.
        current = asyncio.current_task()
        tasks = [task for task in runtime.event_tasks if task is not current and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        runtime.event_tasks.difference_update(tasks)

    def _make_handler(
        self, account_id: str, runtime: _Runtime, settings: Settings, self_id: int, username: str,
    ) -> Callable[..., Awaitable[None]]:
        command_times: dict[tuple[int, int], float] = {}

        async def process_event(event) -> None:
            try:
                raw_text = event.raw_text or ''
                # Exactly retain the single-account runtime boundary: private
                # messages only carry owner control commands, and group text is read
                # only after a local whitelist check.
                owner_ids = settings.owners | {self_id}
                if event.is_private:
                    if event.sender_id not in owner_ids or not raw_text.startswith('/ai_'):
                        return
                elif not event.is_group or event.chat_id not in settings.groups:
                    return
                if event.out and not raw_text.startswith('/ai_'):
                    return
                if raw_text.startswith('/ai_') and event.sender_id in owner_ids:
                    now = time.monotonic()
                    key = (event.chat_id, event.sender_id)
                    if now - command_times.get(key, -1e30) < 2:
                        return
                    command_times[key] = now

                sender = await event.get_sender()
                direct = bool(username and re.search(r'(?<!\w)@' + re.escape(username) + r'\b', raw_text, re.I))
                try:
                    from telethon.tl.types import MessageEntityMentionName
                    direct |= any(
                        isinstance(entity, MessageEntityMentionName) and entity.user_id == self_id
                        for entity in (event.message.entities or [])
                    )
                except Exception:
                    # Entity parsing is an optional enhancement; text and reply
                    # mention handling remain available for fake/minimal events.
                    pass
                if event.message.reply_to:
                    reply = await event.get_reply_message()
                    direct |= bool(reply and reply.sender_id == self_id)
                reply_header = event.message.reply_to
                thread = ((reply_header.reply_to_top_id or reply_header.reply_to_msg_id)
                          if reply_header and getattr(reply_header, 'forum_topic', False) else 0)
                message = Message(
                    chat_id=event.chat_id, message_id=event.id, sender_id=event.sender_id or 0,
                    text=raw_text, at=event.date.timestamp(),
                    sender_name=getattr(sender, 'first_name', None) or '群友',
                    thread_id=thread or 0, private=event.is_private, outgoing=event.out,
                    sender_bot=bool(getattr(sender, 'bot', False)), direct=direct,
                )
                if runtime.engine is not None:
                    await runtime.engine.handle(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Event text and third-party exception details must never reach audit
                # records or logs.  The worker remains available for later messages.
                return

        async def handler(event) -> None:
            task = asyncio.create_task(process_event(event))
            runtime.event_tasks.add(task)
            task.add_done_callback(runtime.event_tasks.discard)

        return handler

    async def start(self, account_id: str) -> dict:
        async with self._start_lock:
            return await self._start_account(account_id)

    async def _start_account(self, account_id: str) -> dict:
        self._check_capacity()
        account = self._account(account_id)
        async with self._lock(account_id):
            runtime = self._runtime(account_id)
            features = set(account.get('features') or [])
            if not features.intersection({'chat', 'faq'}):
                raise ManagerError('请至少启用聊天或 FAQ 功能后再启动')
            settings = self._settings(account_id)
            if not settings.groups:
                raise ManagerError('先设置群白名单，再启动自动聊天')
            if self._has_running_overlap(account_id, settings.groups):
                raise ManagerError('所选群已由本机其他运行账号处理')
            if runtime.state == 'running' and runtime.worker_active:
                return self._result(runtime, 'AI 管家已在运行')
            if self.demo:
                self._require_demo_account(account)
                runtime.settings = settings
                runtime.state = 'running'
                runtime.error = ''
                runtime.connected = True
                runtime.worker_active = True
                group_id = next(iter(settings.groups))
                runtime.demo_preview = (group_id, '【演示草稿】此内容不会发送到 Telegram，也不会请求真实 AI 服务。')
                self._audit(account_id, 'worker', '演示 AI 管家已启动')
                return self._result(runtime, '演示 AI 管家已启动（不会连接 Telegram 或 AI）')

            await self._require_authorized(account_id, account, runtime)
            client = runtime.client
            assert client is not None  # _require_authorized keeps a live client
            try:
                settings.validate(credentials=True, groups=True)
            except ConfigError as exc:
                raise ManagerError(str(exc)) from exc
            # Recheck after await: another account may have become running while this
            # account was checking its saved authorization state.
            if self._has_running_overlap(account_id, settings.groups):
                raise ManagerError('所选群已由本机其他运行账号处理')
            try:
                me = await self._maybe_await(client.get_me())
                if me is None or not getattr(me, 'id', None) or getattr(me, 'bot', False):
                    raise ManagerError('当前会话不是可用的普通账号')
                ai = ChatAI(settings)
                store = Store(settings.state_dir / 'chat.sqlite3')
                # stop() records a tagged global pause before cancelling generated
                # responses.  Only clear that tagged pause on a deliberate restart;
                # an owner-created /ai_pause all remains persistent.
                if store.get('manager:stopped') == '1':
                    store.set('paused:all', '0')
                    store.set('manager:stopped', '0')

                async def send(message: Message, text: str) -> None:
                    await client.send_message(
                        message.chat_id, text, reply_to=message.message_id,
                        parse_mode=None, link_preview=False,
                    )
                    if not message.text.startswith('/ai_'):
                        self._audit(account_id, 'reply', '已向白名单群发送 AI 回复')

                engine = Engine(settings, store, int(me.id), ai.generate, send)
                engine.ai_slots = self._ai_slots
                handler = self._make_handler(account_id, runtime, settings, int(me.id), getattr(me, 'username', '') or '')
                runtime.settings = settings
                runtime.ai, runtime.store, runtime.engine, runtime.handler = ai, store, engine, handler
                try:
                    from telethon import events
                    await self._maybe_await(client.add_event_handler(handler, events.NewMessage()))
                except Exception:
                    runtime.handler = None
                    runtime.engine = None
                    runtime.store = None
                    runtime.ai = None
                    store.close()
                    await ai.close()
                    raise
            except ManagerError:
                raise
            except Exception as exc:
                runtime.state = 'error'
                runtime.error = self._safe_error(exc)
                self._audit(account_id, 'worker', 'AI 管家启动失败')
                raise ManagerError(runtime.error) from None
            runtime.state = 'running'
            runtime.error = ''
            runtime.worker_active = True
            self._audit(account_id, 'worker', 'AI 管家已启动')
            return self._result(runtime, 'AI 管家已启动')

    async def stop(self, account_id: str) -> dict:
        account = self._account(account_id)
        async with self._lock(account_id):
            runtime = self._runtime(account_id)
            if self.demo:
                self._require_demo_account(account)
                runtime.worker_active = False
                runtime.demo_preview = None
                runtime.state = 'offline'
                runtime.error = ''
                runtime.connected = False
                self._audit(account_id, 'worker', '演示 AI 管家已停止')
                return self._result(runtime, '演示 AI 管家已停止')

            # This must happen before handler removal/task cancellation: Engine sees
            # the pause after an in-flight AI generation and refuses to send it.
            if runtime.store is not None:
                try:
                    runtime.store.set('paused:all', '1')
                    runtime.store.set('manager:stopped', '1')
                except Exception:
                    pass
            await self._remove_handler(runtime)
            await self._cancel_event_tasks(runtime)
            runtime.worker_active = False

            ai, store = runtime.ai, runtime.store
            runtime.ai = None
            runtime.store = None
            runtime.engine = None
            if ai is not None:
                try:
                    await ai.close()
                except Exception:
                    pass
            if store is not None:
                try:
                    store.close()
                except Exception:
                    pass
            # Deliberately disconnect only.  Never call log_out and never remove a
            # session file: Telegram-device revocation belongs to the account owner.
            await self._disconnect_client(runtime)
            runtime.code_hash = None
            runtime.code_expires_at = 0.0
            runtime.state = 'offline'
            runtime.error = ''
            self._audit(account_id, 'worker', 'AI 管家已停止并断开本机连接')
            return self._result(runtime, 'AI 管家已停止')

    async def batch(self, action: str, ids: list[str]) -> list[dict]:
        if action not in {'connect', 'start', 'stop'}:
            raise ManagerError('不支持的批量操作')
        if not isinstance(ids, list):
            raise ManagerError('批量账号列表无效')
        unique_ids = list(dict.fromkeys(ids))
        semaphore = asyncio.Semaphore(self.BATCH_CONCURRENCY)
        operation = {'connect': self.connect, 'start': self.start, 'stop': self.stop}[action]

        async def run_one(account_id: str) -> dict:
            async with semaphore:
                try:
                    result = await operation(account_id)
                    return {'id': account_id, 'ok': True, 'state': result['state'], 'message': result['message']}
                except ManagerError as exc:
                    status = self.statuses().get(account_id, {'state': 'error'})
                    return {'id': account_id, 'ok': False, 'state': status['state'], 'message': exc.message}
                except Exception:
                    # This should be unreachable for manager operations, but preserves
                    # per-account batch isolation if a local dependency misbehaves.
                    status = self.statuses().get(account_id, {'state': 'error'})
                    return {'id': account_id, 'ok': False, 'state': status['state'], 'message': '操作失败，请稍后重试'}

        return list(await asyncio.gather(*(run_one(account_id) for account_id in unique_ids)))

    async def shutdown(self) -> None:
        """Stop every locally known client without touching Telegram authorization."""
        for account_id in list(self._runtimes):
            try:
                await self.stop(account_id)
            except ManagerError:
                # The account might have been deleted from Vault while shutdown is
                # running.  Still release the local resources without a Vault lookup.
                runtime = self._runtimes.get(account_id)
                if runtime is None:
                    continue
                async with self._lock(account_id):
                    if runtime.store is not None:
                        try:
                            runtime.store.set('paused:all', '1')
                        except Exception:
                            pass
                    await self._remove_handler(runtime)
                    await self._cancel_event_tasks(runtime)
                    runtime.worker_active = False
                    if runtime.ai is not None:
                        try:
                            await runtime.ai.close()
                        except Exception:
                            pass
                    runtime.ai = None
                    if runtime.store is not None:
                        try:
                            runtime.store.close()
                        except Exception:
                            pass
                    runtime.store = None
                    runtime.engine = None
                    await self._disconnect_client(runtime)
                    runtime.state, runtime.error = 'offline', ''

    def preview(self, account_id: str) -> dict | None:
        """Return only an in-memory dry-run draft; never persist or audit it."""
        self._account(account_id)
        runtime = self._runtimes.get(account_id)
        if runtime is None:
            return None
        draft = runtime.demo_preview if self.demo else (runtime.engine.preview if runtime.engine else None)
        if draft is None:
            return None
        return {'group_id': draft[0], 'text': draft[1]}

    def chat_context(self, account_id: str, group_id: int) -> list[dict]:
        """Read only local, whitelisted group history across forum threads."""
        account = self._account(account_id)
        try:
            group_id = int(group_id)
        except (TypeError, ValueError) as exc:
            raise ManagerError('群 ID 无效') from exc
        if group_id not in set(account.get('groups') or []):
            raise ManagerError('该群不在白名单中')
        settings = self._settings(account_id)
        runtime = self._runtimes.get(account_id)
        connection = runtime.store.db if runtime and runtime.store is not None else None
        close_after = False
        if connection is None:
            path = Path(settings.state_dir) / 'chat.sqlite3'
            # Do not instantiate Store here: its constructor creates a file, while a
            # history query with no worker data is explicitly required to return [].
            if not path.is_file():
                return []
            try:
                connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
                close_after = True
            except sqlite3.Error:
                return []
        try:
            # Select newest local entries first then restore chronological order.  A
            # group prefix includes every forum topic but cannot match another group.
            rows = connection.execute(
                'SELECT role,content FROM ('
                'SELECT id,role,content FROM history WHERE room LIKE ? ORDER BY id DESC LIMIT ?'
                ') ORDER BY id',
                (f'{group_id}:%', max(1, min(settings.context_messages, 100))),
            ).fetchall()
            return [{'role': role, 'content': content} for role, content in rows]
        except sqlite3.Error:
            return []
        finally:
            if close_after:
                connection.close()
