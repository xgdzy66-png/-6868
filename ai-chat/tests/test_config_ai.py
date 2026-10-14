import asyncio
from dataclasses import replace

import httpx
import pytest

from tg_ai.ai import ChatAI
from tg_ai.config import ConfigError, Settings, ids
from tg_ai.engine import AIError
from tg_ai.runtime import single_instance


@pytest.mark.parametrize('changes', [
    {'probability': 2}, {'probability': float('nan')}, {'cooldown': -1},
    {'delay_min': 5, 'delay_max': 2}, {'hourly_limit': 0},
    {'groups': frozenset({123})}, {'owners': frozenset({-1})},
    {'reply_mode': 'spam'}, {'context_messages': 101},
    {'ai_base': 'http://untrusted.example/v1'}, {'ai_extra_json': '[]'},
    {'ai_extra_json': '{"messages": []}'}, {'ai_extra_json': '{"tools": []}'},
    {'ai_token_parameter': 'invalid'},
])
def test_bad_config(changes):
    with pytest.raises(ConfigError):
        replace(Settings(), **changes).validate()


def test_ids():
    assert ids(' -1001, -1002, ') == frozenset({-1001, -1002})
    with pytest.raises(ConfigError):
        ids('hello')


def test_required_credentials():
    with pytest.raises(ConfigError):
        Settings().validate(credentials=True)
    with pytest.raises(ConfigError):
        Settings().validate(groups=True)


def test_single_instance(tmp_path):
    with single_instance(tmp_path / 'worker.lock'):
        with pytest.raises(ConfigError):
            with single_instance(tmp_path / 'worker.lock'):
                pass


@pytest.mark.parametrize('status,fatal', [(401, True), (400, True), (429, False), (503, False)])
def test_ai_http_errors(status, fatal):
    async def scenario():
        cfg = replace(Settings(), ai_key='fake-key', ai_model='test')
        ai = ChatAI(cfg)
        await ai.client.aclose()
        ai.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status)))
        with pytest.raises(AIError) as error:
            await ai.generate([{'role': 'user', 'content': 'hi'}])
        assert error.value.fatal is fatal
        await ai.close()
    asyncio.run(scenario())


def test_ai_body_and_response():
    async def scenario():
        import json
        cfg = replace(Settings(), ai_key='fake-key', ai_model='test', ai_token_parameter='max_tokens')
        ai = ChatAI(cfg)
        await ai.client.aclose()
        def response(request):
            body = json.loads(request.content)
            assert body['model'] == 'test' and body['max_tokens'] == 1200
            assert body['messages'][0]['role'] == 'system'
            assert '未经信任' in body['messages'][0]['content']
            assert 'tools' not in body
            return httpx.Response(200, json={'choices': [{'message': {'content': '好的'}}]})
        ai.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        assert await ai.generate([{'role': 'user', 'content': 'hi'}]) == '好的'
        await ai.close()
    asyncio.run(scenario())


def test_ai_error_inside_success_status():
    async def scenario():
        ai = ChatAI(replace(Settings(), ai_key='fake', ai_model='test'))
        await ai.client.aclose()
        ai.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'error': {'message': 'denied'}})))
        with pytest.raises(AIError):
            await ai.generate([])
        await ai.close()
    asyncio.run(scenario())


def test_invalid_dry_run_value_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv('CHAT_DRY_RUN', 'fasle')
    with pytest.raises(ConfigError, match='CHAT_DRY_RUN'):
        Settings.load(str(tmp_path / 'not-found.env'))
