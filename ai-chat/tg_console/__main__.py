from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from pathlib import Path

from .security import hash_password
from .vault import Vault


DEMO_PASSWORD = 'atelier-demo-2026'


def initialize(vault, reset=False):
    if vault.admin_hash() and not reset:
        print('管理员已经初始化；如需重设，执行 python -m tg_console reset-password。')
        return
    if not sys.stdin.isatty():
        raise ValueError('请在自己的交互终端初始化管理员密码')
    print('正在启用本机管理员密码保护。该密码不是 Telegram 两步验证密码。')
    password = getpass.getpass('设置管理员密码（至少 12 位，输入不显示）：')
    confirm = getpass.getpass('再次输入管理员密码：')
    if password != confirm:
        raise ValueError('两次输入不一致')
    vault.set_admin_hash(hash_password(password))
    vault.event(None, 'security', '已初始化或重设本机管理员密码')
    print('管理员已设置，密码仅保存为加密数据库中的慢哈希。')


def seed_demo(vault):
    if vault.config()['api_hash'] or vault.config()['ai_key']:
        raise ValueError('演示不能使用含真实密钥的数据目录，请换一个独立目录')
    if any(not a.get('demo') for a in vault.accounts()):
        raise ValueError('演示不能使用真实账号目录，请换一个独立目录')
    vault.set_admin_hash(hash_password(DEMO_PASSWORD))
    if vault.accounts():
        return
    samples = [
        ('社群小助手', '+10000000001', [-1001001], '友好自然，适时接话，帮助群友解答日常问题。', ['chat']),
        ('产品答疑管家', '+10000000002', [-1001002], '专业、简明，优先使用知识库回答产品问题。', ['chat', 'faq']),
        ('双语交流助手', '+10000000003', [-1001003], '帮助群友跨语言交流，回答简短清晰。', ['chat']),
    ]
    for name, phone, groups, persona, features in samples:
        a = vault.add_account(name, phone)
        vault.update_account(a['id'], {'demo': True, 'groups': groups, 'persona': persona, 'features': features,
                                      'faq': '演示知识：这是示例知识库，不对应任何真实业务。', 'dry_run': True})
    vault.event(None, 'demo', '当前为演示数据，不连接 Telegram，不保存真实密钥')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='TG Atelier 多账号 AI 管家后台')
    parser.add_argument('action', choices=('init', 'serve', 'reset-password'))
    parser.add_argument('--data-dir', default=None)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--demo', action='store_true', help='仅演示，不登录真实 Telegram')
    parser.add_argument('--https-cookie', action='store_true', help='公开 HTTPS 代理使用 Secure Cookie')
    parser.add_argument('--public-origin', default=None, help='明确的公开 HTTPS 来源，用于跨站请求校验')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logging.getLogger('telethon').setLevel(logging.ERROR)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    vault = None
    try:
        if not 1024 <= args.port <= 65535:
            raise ValueError('端口必须在 1024 至 65535 之间')
        if args.public_origin and not args.public_origin.startswith('https://'):
            raise ValueError('公开来源必须是 HTTPS 地址')
        if args.host not in ('127.0.0.1', 'localhost', '::1') and not args.demo and not (args.https_cookie and args.public_origin):
            raise ValueError('真实后台默认仅监听本机；公网运行需要 HTTPS 代理及 --https-cookie --public-origin')
        directory = Path(args.data_dir or ('console-demo-data' if args.demo else 'console-data'))
        vault = Vault(directory)
        if args.demo:
            seed_demo(vault)
        if args.action in ('init', 'reset-password'):
            initialize(vault, reset=args.action == 'reset-password')
            return
        if not vault.admin_hash():
            raise ValueError('请先执行 python -m tg_console init 设置管理员密码')
        from tg_ai.runtime import single_instance
        from .server import create_app
        import uvicorn
        with single_instance(vault.data_dir / 'console.lock'):
            app = create_app(vault, demo=args.demo, https_cookie=args.https_cookie,
                             public_origin=args.public_origin)
            print('TG Atelier 后台：http://127.0.0.1:' + str(args.port))
            if args.demo:
                print('仅演示模式；演示密码：' + DEMO_PASSWORD)
            uvicorn.run(app, host=args.host, port=args.port, access_log=False)
    except KeyboardInterrupt:
        print('\n已停止后台。')
    except Exception as exc:
        # 只打印已知验证错误，不打印第三方请求、账号或密钥。
        if isinstance(exc, ValueError):
            parser.exit(2, f'配置错误：{exc}\n')
        parser.exit(1, f'后台启动失败（{type(exc).__name__}），请检查配置和端口。\n')
    finally:
        if vault:
            vault.close()


if __name__ == '__main__':
    main()
