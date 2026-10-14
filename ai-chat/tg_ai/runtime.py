from __future__ import annotations

import asyncio
import getpass
import logging
import os
import re
import sys
import time
from contextlib import contextmanager

from .ai import ChatAI
from .config import ConfigError, Settings
from .engine import Engine, Message
from .storage import Store

log = logging.getLogger(__name__)


@contextmanager
def single_instance(path):
    import fcntl
    handle = open(path, 'a+')
    os.chmod(path, 0o600)
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConfigError('同一数据目录已有程序运行，请先停止旧进程') from exc
        yield
    finally:
        handle.close()


async def run(settings: Settings, action: str):
    from telethon import TelegramClient, events
    from telethon.tl.types import MessageEntityMentionName

    if settings.api_id <= 0 or not settings.api_hash:
        raise ConfigError('先配置 TG_API_ID 和 TG_API_HASH；在 my.telegram.org 获取')
    if action == 'run':
        settings.validate(credentials=True, groups=True)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    settings.state_dir.chmod(0o700)
    with single_instance(settings.state_dir / 'worker.lock'):
        client = TelegramClient(str(settings.state_dir / 'account'), settings.api_id, settings.api_hash,
                                flood_sleep_threshold=0, request_retries=0,
                                auto_reconnect=True, connection_retries=5)
        ai = None
        store = None
        try:
            await client.connect()
            if not await client.is_user_authorized():
                if action == 'run':
                    raise ConfigError('尚未登录。先在交互终端运行 python -m tg_ai login')
                if not sys.stdin.isatty():
                    raise ConfigError('首次登录需要交互终端，请在自己的电脑或服务器执行 login')
                await client.start(
                    phone=lambda: input('Telegram 手机号（含国家区号，如 +86…）：').strip(),
                    code_callback=lambda: getpass.getpass('Telegram 验证码（输入不显示）：'),
                    password=lambda: getpass.getpass('Telegram 两步验证密码（没有时不会询问）：'),
                )
            me = await client.get_me()
            if me.bot:
                raise ConfigError('当前会话是 Bot，请使用普通账号登录；不要共用其他程序的 session 文件')
            for p in settings.state_dir.glob('account.session*'):
                p.chmod(0o600)
            print(f'普通账号已登录，用户 ID：{me.id}')
            if action == 'login':
                print('登录会话已保存于受限 data 目录。下一步：python -m tg_ai groups')
                return
            if action == 'groups':
                print('已加入的群（群 ID 用于 TG_ALLOWED_GROUPS）：')
                async for dialog in client.iter_dialogs():
                    if dialog.is_group:
                        print(f'{dialog.id}\t{dialog.name}')
                return
            username = me.username or ''
            ai = ChatAI(settings)
            store = Store(settings.state_dir / 'chat.sqlite3')

            async def send(m: Message, text: str):
                await client.send_message(m.chat_id, text, reply_to=m.message_id,
                                          parse_mode=None, link_preview=False)

            engine = Engine(settings, store, me.id, ai.generate, send)
            owner_ids = settings.owners | {me.id}
            command_times = {}

            @client.on(events.NewMessage())
            async def on_message(event):
                # 不读取不在白名单中的群内容，私聊仅用于已授权用户的控制命令。
                if event.is_private:
                    if event.sender_id not in owner_ids or not event.raw_text.startswith('/ai_'):
                        return
                elif not event.is_group or event.chat_id not in settings.groups:
                    return
                if event.out and not event.raw_text.startswith('/ai_'):
                    return
                if event.raw_text.startswith('/ai_') and event.sender_id in owner_ids:
                    # 控制命令也限速，防止管理员误连点触发平台限流。
                    now = time.monotonic()
                    key = (event.chat_id, event.sender_id)
                    if now - command_times.get(key, -1e30) < 2:
                        return
                    command_times[key] = now
                try:
                    sender = await event.get_sender()
                    direct = bool(username and re.search(r'(?<!\w)@' + re.escape(username) + r'\b', event.raw_text, re.I))
                    direct |= any(isinstance(entity, MessageEntityMentionName) and entity.user_id == me.id
                                  for entity in (event.message.entities or []))
                    if event.message.reply_to:
                        reply = await event.get_reply_message()
                        direct |= bool(reply and reply.sender_id == me.id)
                    # Telegram 论坛群按主题隔离上下文；发送仍直接回复当前消息。
                    reply_header = event.message.reply_to
                    thread = ((reply_header.reply_to_top_id or reply_header.reply_to_msg_id)
                              if reply_header and getattr(reply_header, 'forum_topic', False) else 0)
                    m = Message(
                        chat_id=event.chat_id, message_id=event.id, sender_id=event.sender_id or 0,
                        text=event.raw_text, at=event.date.timestamp(),
                        sender_name=getattr(sender, 'first_name', None) or '群友',
                        thread_id=thread or 0, private=event.is_private, outgoing=event.out,
                        sender_bot=bool(getattr(sender, 'bot', False)), direct=direct,
                    )
                    await engine.handle(m)
                except Exception as exc:
                    # 不输出包含请求 URL、手机号、文本或密钥的完整异常。
                    log.warning('处理消息失败（%s）', type(exc).__name__)

            print('AI 管家运行中。试运行：' + ('开启（不发群回复）' if settings.dry_run else '关闭（会发群回复）'))
            print('在 Telegram 收藏夹发送 /ai_help 查看命令；Ctrl+C 停止。')
            await client.run_until_disconnected()
        finally:
            await client.disconnect()
            if ai:
                await ai.close()
            if store:
                store.close()
