from __future__ import annotations

import argparse
import asyncio
import logging
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from .config import ConfigError, Settings


async def demo():
    from .engine import Engine, Message
    from .storage import Store
    with TemporaryDirectory() as d:
        store = Store(Path(d) / 'demo.db')
        cfg = replace(Settings(), groups=frozenset({-1001234567890}), reply_mode='all',
                      dry_run=False, delay_min=0, delay_max=0)
        async def fake_ai(history):
            return '听起来不错！你们准备什么时候开始？'
        async def fake_send(m, text):
            print('AI 管家：' + text)
        engine = Engine(cfg, store, 1, fake_ai, fake_send, clock=lambda: 1000)
        print('离线演示：不连接 Telegram，不调用 AI，不发送真实消息。')
        print('群友：我们周末约个聚会吧')
        await engine.handle(Message(-1001234567890, 1, 2, '我们周末约个聚会吧', 1000))
        await engine.handle(Message(1, 2, 1, '/ai_pause all', 1000, private=True, outgoing=True))
        print('再次发群消息：已被暂停控制拦截。')
        await engine.handle(Message(-1001234567890, 3, 2, '还能回复吗？', 1000))
        store.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='Telegram 普通账号 AI 群聊管家')
    parser.add_argument('action', choices=('login', 'groups', 'run', 'check', 'demo'))
    parser.add_argument('--env', default='.env', help='配置文件路径')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    # 第三方网络库不记录请求 URL，避免意外显示会话或凭据。
    logging.getLogger('telethon').setLevel(logging.ERROR)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    try:
        if args.action == 'demo':
            asyncio.run(demo())
            return
        settings = Settings.load(args.env)
        if args.action == 'check':
            settings.validate(credentials=True, groups=True)
            print(f'配置检查通过：普通账号 / {len(settings.groups)} 个白名单群 / {settings.reply_mode}')
            print('试运行：' + ('开启' if settings.dry_run else '关闭'))
            print('仅检查配置格式；未验证真实账号和 AI 密钥。')
        else:
            from .runtime import run
            asyncio.run(run(settings, args.action))
    except ConfigError as exc:
        parser.exit(2, f'配置错误：{exc}\n')
    except KeyboardInterrupt:
        print('\n已停止。')
    except Exception as exc:
        parser.exit(1, f'运行失败（{type(exc).__name__}）。请检查网络与凭据；出于隐私不打印完整请求。\n')


if __name__ == '__main__':
    main()
