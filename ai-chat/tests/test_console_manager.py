import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tg_ai.config import Settings
from tg_ai.engine import Message
from tg_console.manager import Manager, ManagerError


# Class names intentionally match Telethon's public exceptions.  This permits a
# no-network fake client while testing Manager's third-party error sanitization.
class PhoneCodeInvalidError(Exception):
    pass


class SessionPasswordNeededError(Exception):
    pass


class PasswordHashInvalidError(Exception):
    pass


class Dialog:
    def __init__(self, group_id, title, is_group=True):
        self.id = group_id
        self.name = title
        self.is_group = is_group


class FakeClient:
    def __init__(self, *, authorized=False, user_id=100, username='steward', dialogs=None, connect_delay=0):
        self.authorized = authorized
        self.me = SimpleNamespace(id=user_id, username=username, bot=False)
        self.dialogs = dialogs or [Dialog(-1001, '已加入群'), Dialog(9, '私聊', False)]
        self.connect_delay = connect_delay
        self.factory = None
        self.code_actions = []
        self.password_actions = []
        self.requested_phones = []
        self.sign_ins = []
        self.sent = []
        self.handlers = []
        self.connects = 0
        self.disconnects = 0
        self.removed_handlers = 0

    async def connect(self):
        self.connects += 1
        if self.factory:
            self.factory.active_connects += 1
            self.factory.max_active_connects = max(self.factory.max_active_connects, self.factory.active_connects)
        try:
            if self.connect_delay:
                await asyncio.sleep(self.connect_delay)
        finally:
            if self.factory:
                self.factory.active_connects -= 1

    async def disconnect(self):
        self.disconnects += 1

    async def is_user_authorized(self):
        return self.authorized

    async def get_me(self):
        return self.me

    async def send_code_request(self, phone):
        self.requested_phones.append(phone)
        return SimpleNamespace(phone_code_hash='fake-code-hash')

    async def sign_in(self, **kwargs):
        self.sign_ins.append(kwargs)
        actions = self.password_actions if 'password' in kwargs else self.code_actions
        if actions:
            outcome = actions.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
        self.authorized = True

    def add_event_handler(self, callback, event):
        self.handlers.append((callback, event))

    def remove_event_handler(self, callback):
        self.removed_handlers += 1
        self.handlers = [(handler, event) for handler, event in self.handlers if handler is not callback]

    async def iter_dialogs(self):
        for dialog in self.dialogs:
            yield dialog

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))


class FakeFactory:
    def __init__(self, clients):
        self.clients = clients
        self.calls = []
        self.active_connects = 0
        self.max_active_connects = 0

    def __call__(self, session, api_id, api_hash, **kwargs):
        account_id = Path(session).parent.name
        client = self.clients[account_id]
        client.factory = self
        self.calls.append((account_id, session, api_id, api_hash, kwargs))
        return client


class FakeVault:
    def __init__(self, root, accounts, *, dry_run=True):
        self.root = Path(root)
        self._accounts = {account['id']: account for account in accounts}
        self.events_log = []
        self.dry_run = dry_run

    def accounts(self):
        return list(self._accounts.values())

    def account(self, account_id):
        if account_id not in self._accounts:
            raise KeyError(account_id)
        return self._accounts[account_id]

    def update_account(self, account_id, patch):
        self._accounts[account_id].update(patch)
        return self._accounts[account_id]

    def event(self, account_id, kind, message):
        self.events_log.append((account_id, kind, message))

    def settings(self, account_id):
        account = self.account(account_id)
        return replace(
            Settings(),
            groups=frozenset(account['groups']),
            reply_mode=account['reply_mode'],
            probability=account['probability'],
            cooldown=account['cooldown'],
            hourly_limit=account['hourly_limit'],
            daily_limit=account['daily_limit'],
            dry_run=account['dry_run'] if 'dry_run' in account else self.dry_run,
            api_id=12345,
            api_hash='telegram-api-hash',
            ai_key='test-ai-key',
            ai_model='test-model',
            delay_min=0,
            delay_max=0,
            state_dir=self.root / 'accounts' / account_id,
            persona=account.get('persona', Settings.persona),
        )


def account(account_id, *, groups=(-1001,), tg_user_id=None, demo=False, dry_run=True):
    return {
        'id': account_id,
        # Deliberately not a server-valid phone: Manager must leave phone format
        # validation to the API model/server layer and pass stored data to Telethon.
        'phone': 'stored-phone',
        'tg_user_id': tg_user_id,
        'username': '',
        'groups': list(groups),
        'features': ['chat'],
        'reply_mode': 'all',
        'probability': 1,
        'cooldown': 0,
        'hourly_limit': 20,
        'daily_limit': 100,
        'dry_run': dry_run,
        'persona': Settings.persona,
        'faq': '',
        **({'demo': True} if demo else {}),
    }


def run(awaitable):
    return asyncio.run(awaitable)


def test_request_code_and_invalid_code_are_safe_and_not_persisted(tmp_path):
    client = FakeClient()
    client.code_actions = [PhoneCodeInvalidError('the Telegram error must not leak')]
    vault = FakeVault(tmp_path, [account('a')])
    manager = Manager(vault, client_factory=FakeFactory({'a': client}))

    result = run(manager.request_code('a'))
    assert result == {'state': 'code', 'message': '验证码已发送，请在十分钟内验证'}
    assert client.requested_phones == ['stored-phone']

    with pytest.raises(ManagerError, match='验证码错误') as error:
        run(manager.verify_code('a', '12345'))
    assert error.value.message == '验证码错误，请重新输入'
    assert manager.statuses()['a'] == {'state': 'code', 'error': '验证码错误，请重新输入', 'connected': True}
    assert all('stored-phone' not in message and '12345' not in message for _, _, message in vault.events_log)
    assert manager._runtimes['a'].code_hash == 'fake-code-hash'


def test_authorized_request_code_becomes_ready_without_sending_an_otp(tmp_path):
    client = FakeClient(authorized=True, user_id=123)
    vault = FakeVault(tmp_path, [account('a')])
    manager = Manager(vault, client_factory=FakeFactory({'a': client}))

    result = run(manager.request_code('a'))
    assert result['state'] == 'ready'
    assert client.requested_phones == []
    assert vault.account('a')['tg_user_id'] == 123
    assert vault.account('a')['username'] == 'steward'


def test_two_factor_flow_keeps_password_transient_and_maps_error(tmp_path):
    client = FakeClient()
    client.code_actions = [SessionPasswordNeededError('secret server detail')]
    client.password_actions = [PasswordHashInvalidError('bad 2fa'), None]
    vault = FakeVault(tmp_path, [account('a')])
    manager = Manager(vault, client_factory=FakeFactory({'a': client}))

    run(manager.request_code('a'))
    assert run(manager.verify_code('a', '12345')) == {'state': 'password', 'message': '需要两步验证密码'}
    with pytest.raises(ManagerError, match='两步验证密码错误'):
        run(manager.verify_password('a', 'temporary-2fa-password'))
    assert manager.statuses()['a']['state'] == 'password'
    assert manager.statuses()['a']['error'] == '两步验证密码错误'
    assert run(manager.verify_password('a', 'temporary-2fa-password'))['state'] == 'ready'
    assert all('temporary-2fa-password' not in message for _, _, message in vault.events_log)
    assert not hasattr(manager._runtimes['a'], 'password')


def test_connect_never_requests_code_and_revoked_saved_session_is_error(tmp_path):
    client = FakeClient(authorized=False)
    vault = FakeVault(tmp_path, [account('a', tg_user_id=50)])
    manager = Manager(vault, client_factory=FakeFactory({'a': client}))

    with pytest.raises(ManagerError, match='登录会话已失效'):
        run(manager.connect('a'))
    assert client.requested_phones == []
    assert manager.statuses()['a'] == {'state': 'error', 'error': '登录会话已失效，请重新登录', 'connected': False}
    assert client.disconnects == 1


def test_duplicate_telegram_user_is_disconnected_without_logging_out(tmp_path):
    client = FakeClient(user_id=99)
    vault = FakeVault(tmp_path, [account('a'), account('other', tg_user_id=99)])
    manager = Manager(vault, client_factory=FakeFactory({'a': client, 'other': FakeClient(authorized=True, user_id=99)}))

    run(manager.request_code('a'))
    with pytest.raises(ManagerError, match='已在控制台中存在'):
        run(manager.verify_code('a', '12345'))
    assert vault.account('a')['tg_user_id'] is None
    assert client.disconnects == 1
    assert not hasattr(client, 'log_out')


def test_groups_worker_reply_audit_preview_and_whitelisted_context(tmp_path):
    client = FakeClient(authorized=True, user_id=7)
    vault = FakeVault(tmp_path, [account('a', dry_run=False)], dry_run=False)
    manager = Manager(vault, client_factory=FakeFactory({'a': client}))

    run(manager.connect('a'))
    assert run(manager.groups('a')) == [{'id': -1001, 'title': '已加入群'}]
    assert run(manager.start('a'))['state'] == 'running'
    runtime = manager._runtimes['a']
    assert runtime.engine.ai_slots is manager._ai_slots
    assert len(client.handlers) == 1

    async def answer(_history):
        return '真实发送的 AI 回复'

    runtime.engine.generate = answer
    import time
    run(runtime.engine.handle(Message(-1001, 1, 44, '你好', time.time())))
    assert client.sent and client.sent[-1][1] == '真实发送的 AI 回复'
    assert ('a', 'reply', '已向白名单群发送 AI 回复') in vault.events_log

    runtime.store.add('-1001:9', 'user', '论坛主题本地内容', time.time(), 24)
    assert manager.chat_context('a', -1001)[-1] == {'role': 'user', 'content': '论坛主题本地内容'}
    with pytest.raises(ManagerError, match='白名单'):
        manager.chat_context('a', -2002)
    assert manager.preview('a') is None
    run(manager.stop('a'))
    assert client.removed_handlers == 1
    assert client.disconnects == 1


def test_overlapping_groups_block_second_active_worker_then_allow_after_stop(tmp_path):
    clients = {'a': FakeClient(authorized=True, user_id=1), 'b': FakeClient(authorized=True, user_id=2)}
    vault = FakeVault(tmp_path, [account('a'), account('b')])
    manager = Manager(vault, client_factory=FakeFactory(clients))

    run(manager.connect('a'))
    run(manager.connect('b'))
    run(manager.start('a'))
    with pytest.raises(ManagerError, match='其他运行账号'):
        run(manager.start('b'))
    run(manager.stop('a'))
    assert run(manager.start('b'))['state'] == 'running'
    run(manager.shutdown())


def test_batch_is_deduplicated_bounded_and_isolates_account_errors(tmp_path):
    clients = {
        'a': FakeClient(authorized=True, user_id=1, connect_delay=0.01),
        'b': FakeClient(authorized=True, user_id=2, connect_delay=0.01),
        'c': FakeClient(authorized=True, user_id=3, connect_delay=0.01),
    }
    vault = FakeVault(tmp_path, [account('a'), account('b'), account('c')])
    factory = FakeFactory(clients)
    manager = Manager(vault, client_factory=factory)

    results = run(manager.batch('connect', ['a', 'b', 'a', 'missing', 'c']))
    assert [item['id'] for item in results] == ['a', 'b', 'missing', 'c']
    assert [item['ok'] for item in results] == [True, True, False, True]
    assert results[2]['message'] == '账号不存在'
    assert factory.max_active_connects == 2
    assert all(not client.requested_phones for client in clients.values())


def test_shutdown_cancels_background_tasks_removes_handlers_and_disconnects(tmp_path):
    client = FakeClient(authorized=True, user_id=7)
    vault = FakeVault(tmp_path, [account('a')])
    manager = Manager(vault, client_factory=FakeFactory({'a': client}))

    async def scenario():
        await manager.connect('a')
        await manager.start('a')
        pending = asyncio.create_task(asyncio.sleep(60))
        manager._runtimes['a'].event_tasks.add(pending)
        await manager.shutdown()
        return pending

    pending = run(scenario())
    assert pending.cancelled()
    assert client.removed_handlers == 1
    assert client.disconnects == 1
    assert manager.statuses()['a']['state'] == 'offline'


def test_demo_never_constructs_client_or_requests_real_login(tmp_path):
    vault = FakeVault(tmp_path, [account('demo', demo=True)])
    factory = FakeFactory({'demo': FakeClient()})
    manager = Manager(vault, demo=True, client_factory=factory)

    with pytest.raises(ManagerError, match='演示模式不支持'):
        run(manager.request_code('demo'))
    assert factory.calls == []
    assert run(manager.connect('demo'))['state'] == 'ready'
    assert run(manager.start('demo'))['state'] == 'running'
    preview = manager.preview('demo')
    assert preview and '演示草稿' in preview['text']
    assert run(manager.stop('demo'))['state'] == 'offline'
    assert factory.calls == []


def test_concurrent_batch_start_cannot_claim_same_group(tmp_path):
    class YieldingProfileClient(FakeClient):
        async def get_me(self):
            await asyncio.sleep(0.01)
            return self.me

    clients = {'a': YieldingProfileClient(authorized=True, user_id=1),
               'b': YieldingProfileClient(authorized=True, user_id=2)}
    vault = FakeVault(tmp_path, [account('a'), account('b')])
    manager = Manager(vault, client_factory=FakeFactory(clients))

    async def scenario():
        await manager.batch('connect', ['a', 'b'])
        try:
            results = await manager.batch('start', ['a', 'b'])
            assert [r['ok'] for r in results] == [True, False]
            assert sum(r['state'] == 'running' for r in manager.statuses().values()) == 1
            assert sum(len(c.handlers) for c in clients.values()) == 1
        finally:
            await manager.shutdown()

    run(scenario())
