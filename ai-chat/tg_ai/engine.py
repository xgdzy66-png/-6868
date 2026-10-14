from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from .config import Settings
from .storage import Store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    chat_id: int
    message_id: int
    sender_id: int
    text: str
    at: float
    sender_name: str = '群友'
    thread_id: int = 0
    private: bool = False
    outgoing: bool = False
    sender_bot: bool = False
    direct: bool = False

    @property
    def room(self) -> str:
        return f'{self.chat_id}:{self.thread_id}'


class AIError(Exception):
    def __init__(self, fatal: bool = False):
        self.fatal = fatal
        super().__init__('AI 服务请求失败')


class Engine:
    def __init__(self, settings: Settings, store: Store, self_id: int,
                 generate: Callable[[list[dict]], Awaitable[str]],
                 send: Callable[[Message, str], Awaitable[None]],
                 clock=time.time, sleep=asyncio.sleep, rng=None):
        self.cfg, self.store, self.self_id = settings, store, self_id
        self.generate, self.send = generate, send
        self.clock, self.sleep, self.rng = clock, sleep, rng or random.Random()
        self.locks: dict[int, asyncio.Lock] = {}
        self.ai_slots = asyncio.Semaphore(2)
        self.blocked_until: dict[int, float] = {}
        self.preview: tuple[int, str] | None = None

    def paused(self, group: int) -> bool:
        return self.store.get('paused:all') == '1' or self.store.get(f'paused:{group}') == '1'

    def available(self, group: int, now: float) -> bool:
        last, hourly, daily = self.store.limits(group, now)
        return (not self.paused(group) and now >= self.blocked_until.get(group, 0)
                and now - last >= self.cfg.cooldown
                and hourly < self.cfg.hourly_limit and daily < self.cfg.daily_limit)

    async def command(self, m: Message) -> bool:
        if not m.text.startswith('/ai_'):
            return False
        # 普通账号无需通过群文本授予权限：仅本人及显式配置的用户可管理。
        if m.sender_id not in self.cfg.owners | {self.self_id}:
            return True
        if not m.private and m.chat_id not in self.cfg.groups:
            return True
        parts = m.text.split()
        cmd = parts[0]
        if '@' in cmd:
            return True  # 不吞其他 Bot 的定向命令。
        if cmd == '/ai_id':
            await self.send(m, f'群/会话 ID：{m.chat_id}\n你的用户 ID：{m.sender_id}')
            return True
        if cmd == '/ai_help':
            await self.send(m, 'AI 管家命令：\n/ai_status\n/ai_pause [群ID|all]\n/ai_resume [群ID|all]\n/ai_mode mentions|smart|all [群ID|all]\n/ai_clear [群ID]\n/ai_preview（仅收藏夹或管理员私聊）\n/ai_id\n在群内默认操作当前群；在私聊/收藏夹暂停与恢复默认操作 all。')
            return True
        if cmd == '/ai_preview':
            if not m.private:
                await self.send(m, '请在收藏夹或管理员私聊查看试运行草稿。')
            else:
                await self.send(m, f'最近试运行草稿（群 {self.preview[0]}）：\n{self.preview[1]}' if self.preview else '暂无试运行草稿。')
            return True
        if cmd == '/ai_status':
            rows = []
            for g in sorted(self.cfg.groups):
                _, h, d = self.store.limits(g, self.clock())
                mode = self.store.get(f'mode:{g}', self.store.get('mode:all', self.cfg.reply_mode))
                rows.append(f'{g}：{"暂停" if self.paused(g) else "启用"} / {mode} / 本小时 {h} / 24小时 {d}')
            await self.send(m, f'普通账号 AI 管家\n试运行：{"是（不向群发送 AI 回复）" if self.cfg.dry_run else "否"}\n' + '\n'.join(rows))
            return True
        if cmd not in ('/ai_pause', '/ai_resume', '/ai_mode', '/ai_clear'):
            await self.send(m, '未知命令，请发送 /ai_help')
            return True
        mode = None
        if cmd == '/ai_mode':
            if len(parts) < 2 or parts[1] not in ('mentions', 'smart', 'all'):
                await self.send(m, '用法：/ai_mode mentions|smart|all [群ID|all]')
                return True
            mode = parts[1]
            args = parts[2:]
        else:
            args = parts[1:]
        if len(args) > 1:
            await self.send(m, '一次只能指定一个群 ID 或 all。')
            return True
        target = args[0] if args else ('all' if m.private else str(m.chat_id))
        if target != 'all':
            try:
                target = str(int(target))
            except ValueError:
                await self.send(m, '目标必须是群 ID 或 all。')
                return True
            if int(target) not in self.cfg.groups:
                await self.send(m, '该群不在白名单，请修改本机 .env 并重启。')
                return True
        if cmd == '/ai_clear':
            if target == 'all':
                await self.send(m, '清除记忆请明确指定一个群 ID。')
                return True
            self.store.clear(int(target))
            await self.send(m, f'已清除群 {target} 的本地上下文；不会删除 Telegram 消息。')
        elif cmd == '/ai_mode':
            self.store.set(f'mode:{target}', mode)
            if target == 'all':
                for g in self.cfg.groups:
                    self.store.set(f'mode:{g}', mode)
            await self.send(m, f'{target} 的模式已设为 {mode}，冷却和配额仍生效。')
        else:
            value = '1' if cmd == '/ai_pause' else '0'
            self.store.set(f'paused:{target}', value)
            if target == 'all' and value == '0':
                for g in self.cfg.groups:
                    self.store.set(f'paused:{g}', '0')
            await self.send(m, f'{target} 已{"暂停" if value == "1" else "恢复"}。' + ('试运行仍开启，不会发 AI 群回复。' if value == '0' and self.cfg.dry_run else ''))
        return True

    async def handle(self, m: Message):
        now = self.clock()
        if now - m.at > self.cfg.max_message_age or m.at > now + 60:
            return
        if not self.store.claim(f'{m.chat_id}:{m.message_id}', now):
            return
        if await self.command(m):
            return
        if (m.private or m.chat_id not in self.cfg.groups or m.outgoing
                or m.sender_id == self.self_id or m.sender_bot or not m.text.strip()
                or m.text.startswith('/')):
            return
        self.store.prune(now, self.cfg.retention_hours)
        if self.paused(m.chat_id):
            return
        content = json.dumps({'群友': m.sender_name[:80], '消息': m.text[:2000]}, ensure_ascii=False)
        self.store.add(m.room, 'user', content, now, self.cfg.context_messages)
        if not self.available(m.chat_id, now):
            return
        mode = self.store.get(f'mode:{m.chat_id}', self.store.get('mode:all', self.cfg.reply_mode))
        triggered = m.direct or mode == 'all' or (mode == 'smart' and self.rng.random() < self.cfg.probability)
        if not triggered:
            return
        lock = self.locks.setdefault(m.chat_id, asyncio.Lock())
        if lock.locked():
            return  # 活跃群只保留上下文，不排队刷屏。
        async with lock:
            await self.sleep(self.rng.uniform(self.cfg.delay_min, self.cfg.delay_max))
            async with self.ai_slots:
                if not self.available(m.chat_id, self.clock()):
                    return
                try:
                    answer = (await self.generate(self.store.history(m.room))).strip()
                except AIError as exc:
                    if exc.fatal:
                        self.store.set('paused:all', '1')
                        log.error('AI 配置或授权错误，已暂停全部群。请检查配置后重启，并用 /ai_resume all 恢复。')
                    else:
                        self.blocked_until[m.chat_id] = self.clock() + 60
                        log.warning('AI 临时失败：群 %s 冷却 60 秒，不发送错误文本。', m.chat_id)
                    return
            if not answer or answer == '[SKIP]' or not self.available(m.chat_id, self.clock()):
                return
            answer = answer[:self.cfg.max_reply_chars]
            if self.cfg.dry_run:
                self.preview = (m.chat_id, answer)
                self.store.record_reply(m.chat_id, self.clock())
                log.info('试运行生成草稿：群 %s（用 /ai_preview 查看；未发送群回复）', m.chat_id)
                return
            # 先占用发送额度；网络状态不明时不重试，避免重复发言。
            self.store.record_reply(m.chat_id, self.clock())
            try:
                await self.send(m, answer)
            except Exception as exc:
                self.blocked_until[m.chat_id] = self.clock() + max(60, getattr(exc, 'seconds', 0))
                log.warning('Telegram 发送失败（%s），不自动重发。', type(exc).__name__)
                return
            self.store.add(m.room, 'assistant', answer, self.clock(), self.cfg.context_messages)
            log.info('已发送 AI 回复：群 %s', m.chat_id)
