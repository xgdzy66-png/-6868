import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from tg_ai.config import Settings
from tg_ai.engine import AIError, Engine, Message
from tg_ai.storage import Store


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / 'state.db')
    cfg = replace(Settings(), groups=frozenset({-1001, -1002}), reply_mode='all',
                  dry_run=False, delay_min=0, delay_max=0)
    sent, histories = [], []
    now = [10000.0]
    async def generate(history):
        histories.append(history)
        return '你好，我是 AI 管家。'
    async def send(m, text):
        sent.append((m.chat_id, text))
    engine = Engine(cfg, store, 1, generate, send, clock=lambda: now[0])
    yield engine, store, sent, histories, now
    store.close()


def msg(mid=1, group=-1001, **kwargs):
    return Message(chat_id=group, message_id=mid, sender_id=kwargs.pop('sender_id', 2),
                   text=kwargs.pop('text', '今天聊点什么？'), at=kwargs.pop('at', 10000), **kwargs)


def handle(engine, message):
    asyncio.run(engine.handle(message))


def test_sends_reply_with_context(setup):
    e, s, sent, histories, _ = setup
    handle(e, msg())
    assert sent == [(-1001, '你好，我是 AI 管家。')]
    assert '今天聊点什么' in histories[0][0]['content']
    assert s.history('-1001:0')[-1]['role'] == 'assistant'


@pytest.mark.parametrize('message', [
    msg(group=-999), msg(private=True), msg(outgoing=True),
    msg(sender_id=1), msg(sender_bot=True), msg(text=''),
    msg(text='/start'), msg(at=9000), msg(at=10100),
])
def test_ignored_messages(setup, message):
    e, _, sent, histories, _ = setup
    handle(e, message)
    assert not sent and not histories


def test_deduplication(setup):
    e, _, sent, _, now = setup
    handle(e, msg())
    now[0] += 61
    handle(e, msg(at=now[0]))
    assert len(sent) == 1


def test_cooldown_independent_groups(setup):
    e, _, sent, _, _ = setup
    handle(e, msg())
    handle(e, msg(2))
    handle(e, msg(3, group=-1002))
    assert [g for g, _ in sent] == [-1001, -1002]


def test_hourly_limit(setup):
    e, s, sent, _, _ = setup
    for i in range(20):
        s.record_reply(-1001, 9000 + i)
    handle(e, msg())
    assert not sent


def test_daily_limit(setup):
    e, s, sent, _, _ = setup
    for i in range(100):
        s.record_reply(-1001, 5000 + i)
    handle(e, msg())
    assert not sent


def test_dry_run_no_group_send(setup):
    e, s, sent, histories, _ = setup
    e.cfg = replace(e.cfg, dry_run=True)
    handle(e, msg())
    assert histories and not sent and e.preview[1]
    assert s.limits(-1001, 10000)[1] == 1
    handle(e, msg(2, group=1, sender_id=1, text='/ai_preview', private=True, outgoing=True))
    assert '草稿' in sent[0][1]


def test_mentions_mode(setup):
    e, _, sent, _, _ = setup
    e.cfg = replace(e.cfg, reply_mode='mentions')
    handle(e, msg())
    assert not sent
    handle(e, msg(2, direct=True))
    assert sent


def test_smart_probability_zero(setup):
    e, _, sent, _, _ = setup
    e.cfg = replace(e.cfg, reply_mode='smart', probability=0)
    handle(e, msg())
    assert not sent
    handle(e, msg(2, direct=True))
    assert sent


def test_owner_only_pause(setup):
    e, s, sent, _, _ = setup
    handle(e, msg(text='/ai_pause all'))
    assert s.get('paused:all') == '' and not sent
    handle(e, msg(2, group=1, sender_id=1, private=True, outgoing=True, text='/ai_pause all'))
    assert s.get('paused:all') == '1'
    handle(e, msg(3))
    assert len(sent) == 1


def test_group_resume_does_not_override_global_pause(setup):
    e, s, _, _, _ = setup
    s.set('paused:all', '1')
    handle(e, msg(1, sender_id=1, text='/ai_resume'))
    assert e.paused(-1001)


def test_restore_all_clears_group_pause(setup):
    e, s, _, _, _ = setup
    s.set('paused:all', '1')
    s.set('paused:-1001', '1')
    handle(e, msg(1, sender_id=1, text='/ai_resume all'))
    assert not e.paused(-1001)


def test_pause_while_generating_prevents_send(setup):
    e, s, sent, _, _ = setup
    async def generate(history):
        s.set('paused:all', '1')
        return '不应发送'
    e.generate = generate
    handle(e, msg())
    assert not sent


def test_busy_group_not_queued(setup):
    e, _, sent, histories, _ = setup
    async def scenario():
        e.locks[-1001] = asyncio.Lock()
        await e.locks[-1001].acquire()
        await e.handle(msg())
        e.locks[-1001].release()
    asyncio.run(scenario())
    assert not sent and not histories


def test_ai_skip(setup):
    e, _, sent, _, _ = setup
    async def generate(history):
        return '[SKIP]'
    e.generate = generate
    handle(e, msg())
    assert not sent


@pytest.mark.parametrize('fatal', [False, True])
def test_ai_error(setup, fatal):
    e, s, sent, _, _ = setup
    async def generate(history):
        raise AIError(fatal=fatal)
    e.generate = generate
    handle(e, msg())
    assert not sent
    assert e.paused(-1001) == fatal
    assert fatal or e.blocked_until[-1001] == 10060


def test_send_failure_is_not_retried(setup):
    e, s, _, _, _ = setup
    calls = []
    async def send(m, text):
        calls.append(1)
        raise OSError('network')
    e.send = send
    handle(e, msg())
    handle(e, msg(2))
    assert len(calls) == 1
    assert s.limits(-1001, 10000)[1] == 1


def test_topics_are_isolated(setup):
    e, s, _, _, now = setup
    handle(e, msg(thread_id=10))
    now[0] += 61
    handle(e, msg(2, thread_id=20, at=now[0]))
    assert len(s.history('-1001:10')) == 2
    assert len(s.history('-1001:20')) == 2


def test_clear_requires_specific_group(setup):
    e, s, sent, _, _ = setup
    s.add('-1001:0', 'user', 'secret', 10000, 24)
    handle(e, msg(group=1, sender_id=1, private=True, outgoing=True, text='/ai_clear'))
    assert s.history('-1001:0')
    handle(e, msg(2, group=1, sender_id=1, private=True, outgoing=True, text='/ai_clear -1001'))
    assert not s.history('-1001:0')


def test_mode_and_status(setup):
    e, s, sent, _, _ = setup
    handle(e, msg(sender_id=1, text='/ai_mode mentions all'))
    assert s.get('mode:-1001') == 'mentions'
    handle(e, msg(2, sender_id=1, text='/ai_status'))
    assert 'mentions' in sent[-1][1]


def test_no_group_preview(setup):
    e, _, sent, _, _ = setup
    e.preview = (-1001, 'private draft')
    handle(e, msg(sender_id=1, text='/ai_preview'))
    assert 'private draft' not in sent[-1][1]


def test_context_bounded_and_pruned(tmp_path):
    s = Store(tmp_path / 's.db')
    for i in range(30):
        s.add('-1001:0', 'user', str(i), i, 24)
    assert len(s.history('-1001:0')) == 24
    s.prune(100000, 24)
    assert not s.history('-1001:0')
    s.close()


def test_pause_persisted(tmp_path):
    path = tmp_path / 's.db'
    s = Store(path)
    s.set('paused:all', '1')
    s.close()
    s = Store(path)
    assert s.get('paused:all') == '1'
    s.close()
