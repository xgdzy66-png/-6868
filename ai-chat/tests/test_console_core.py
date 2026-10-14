from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tg_console.security import Security, hash_password, verify_password
from tg_console.server import create_app
from tg_console.vault import Vault, public_config


class FakeManager:
    def __init__(self, vault):
        self.vault = vault
    def statuses(self):
        return {}
    async def shutdown(self):
        pass
    def chat_context(self, account_id, group_id):
        return []
    def preview(self, account_id):
        return None
    async def batch(self, action, ids):
        return []


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / 'console')
    v.set_admin_hash(hash_password('a-very-long-test-password'))
    yield v
    v.close()


@pytest.fixture
def client(vault):
    with TestClient(create_app(vault, FakeManager(vault))) as client:
        yield client


def login(client):
    r = client.post('/api/login', json={'password': 'a-very-long-test-password'})
    assert r.status_code == 200
    return {'X-CSRF-Token': r.json()['csrf']}


def test_secret_config_is_encrypted(vault):
    vault.update_config({'api_hash': 'private-hash', 'ai_key': 'private-ai-secret'})
    row = vault.db.execute("SELECT value FROM vault WHERE key='config'").fetchone()[0]
    assert b'private-hash' not in row and b'private-ai-secret' not in row
    assert vault.config()['ai_key'] == 'private-ai-secret'
    assert 'ai_key' not in public_config(vault.config())


def test_phone_is_encrypted(vault):
    a = vault.add_account('管家', '+8613800000000')
    row = vault.db.execute('SELECT value FROM vault WHERE key=?', ('account:' + a['id'],)).fetchone()[0]
    assert b'+8613800000000' not in row
    assert vault.account(a['id'])['phone'] == '+8613800000000'


def test_duplicate_phone(vault):
    vault.add_account('one', '+8613800000000')
    with pytest.raises(ValueError):
        vault.add_account('two', '+8613800000000')


def test_settings_are_independent(vault):
    a = vault.add_account('one', '+8613800000000')
    b = vault.add_account('two', '+8613800000001')
    vault.update_account(a['id'], {'groups': [-1001], 'features': ['faq'], 'faq': '退货期限 7 天'})
    assert vault.settings(a['id']).groups == frozenset({-1001})
    assert not vault.settings(b['id']).groups
    assert '退货期限' in vault.settings(a['id']).persona
    assert vault.settings(a['id']).state_dir != vault.settings(b['id']).state_dir


def test_path_traversal_rejected(vault):
    with pytest.raises(KeyError):
        vault.account('../../secret')


def test_password_hash_and_verify():
    encoded = hash_password('a-very-long-test-password')
    assert verify_password('a-very-long-test-password', encoded)
    assert not verify_password('wrong', encoded)
    assert not verify_password('password', 'broken')
    with pytest.raises(ValueError):
        hash_password('short')


def test_authentication_required(client):
    assert client.get('/api/dashboard').status_code == 401
    assert client.get('/api/config').status_code == 401
    assert client.get('/healthz').status_code == 200


def test_login_cookie_and_logout(client):
    headers = login(client)
    assert client.get('/api/session').json()['authenticated']
    assert client.get('/api/dashboard').status_code == 200
    assert client.post('/api/logout', json={}, headers=headers).status_code == 200
    assert client.get('/api/dashboard').status_code == 401


def test_csrf_required(client):
    login(client)
    assert client.patch('/api/config', json={'ai_model': 'test'}).status_code == 403


def test_cross_origin_rejected(client):
    assert client.post('/api/login', json={'password': 'a-very-long-test-password'}, headers={'Origin': 'https://evil.example'}).status_code == 403


def test_bad_password_rate_limited(client):
    for _ in range(5):
        assert client.post('/api/login', json={'password': 'wrong'}).status_code == 401
    assert client.post('/api/login', json={'password': 'wrong'}).status_code == 429


def test_validation_does_not_echo_sensitive_input(client):
    r = client.post('/api/login', json={'password': 'x' * 300})
    assert r.status_code == 422 and 'x' * 300 not in r.text


def test_account_api_hides_phone(client):
    headers = login(client)
    r = client.post('/api/accounts', json={'name': 'test', 'phone': '+8613800000000'}, headers=headers)
    assert r.status_code == 200 and '+8613800000000' not in r.text
    assert 'phone_masked' in r.json()['account']


def test_illegal_groups_rejected(client, vault):
    headers = login(client)
    a = vault.add_account('one', '+8613800000000')
    r = client.patch('/api/accounts/' + a['id'], json={'groups': [123]}, headers=headers)
    assert r.status_code == 422


def test_secret_write_not_returned(client, vault):
    headers = login(client)
    secret = 'unique-private-api-key'
    r = client.patch('/api/config', json={'api_id': 12345, 'api_hash': 'a' * 32, 'ai_key': secret}, headers=headers)
    assert r.status_code == 200 and secret not in r.text and 'a' * 32 not in r.text
    assert r.json()['ai_key_set'] and r.json()['api_hash_set']
    assert vault.config()['ai_key'] == secret
    r = client.patch('/api/config', json={'api_hash': '', 'ai_key': ''}, headers=headers)
    assert r.status_code == 200 and vault.config()['ai_key'] == secret


def test_invalid_api_base_rejected(client):
    headers = login(client)
    assert client.patch('/api/config', json={'ai_base': 'https://api.example/v1/chat/completions'}, headers=headers).status_code == 400


def test_demo_rejects_real_credentials(vault):
    with TestClient(create_app(vault, FakeManager(vault), demo=True)) as c:
        h = login(c)
        assert c.patch('/api/config', json={'ai_key': 'real-key'}, headers=h).status_code == 403
        assert c.post('/api/accounts', json={'name': 'real', 'phone': '+8613800000000'}, headers=h).status_code == 403


def test_demo_tool_produces_marked_draft(vault):
    a = vault.add_account('demo', '+8613800000000')
    with TestClient(create_app(vault, FakeManager(vault), demo=True)) as c:
        h = login(c)
        r = c.post('/api/tools', json={'account_id': a['id'], 'operation': 'summary', 'text': 'meeting'}, headers=h)
        assert r.status_code == 200 and r.json()['demo'] is True and '演示' in r.json()['text']


def test_tool_cannot_read_non_whitelisted_group(vault):
    a = vault.add_account('demo', '+8613800000000')
    with TestClient(create_app(vault, FakeManager(vault), demo=True)) as c:
        h = login(c)
        r = c.post('/api/tools', json={'account_id': a['id'], 'operation': 'summary', 'group_id': -999}, headers=h)
        assert r.status_code == 400


def test_request_body_limit(client):
    assert client.post('/api/login', content='x' * 70000, headers={'Content-Type': 'application/json'}).status_code == 413


def test_sessions_expire(vault):
    now = [1000]
    s = Security(vault, clock=lambda: now[0])
    token, _ = s.login('a-very-long-test-password', 'local')
    assert s.session(token)
    now[0] += 9 * 3600
    assert s.session(token) is None
