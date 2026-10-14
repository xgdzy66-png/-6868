from __future__ import annotations

import json
from dataclasses import replace

from tg_ai.ai import ChatAI


async def run_tool(vault, manager, request, slots, demo=False) -> dict:
    account = vault.account(request.account_id)
    text = request.text.strip()
    if request.group_id is not None:
        if request.operation != 'summary':
            raise ValueError('群上下文仅用于摘要功能')
        if request.group_id not in account['groups']:
            raise ValueError('只能总结此账号白名单中的群')
        context = manager.chat_context(request.account_id, request.group_id)
        if not context:
            raise ValueError('该群尚无本机上下文，请先运行账号接收新消息')
        text = json.dumps(context[-24:], ensure_ascii=False)
    if not text:
        raise ValueError('请先输入要处理的文本')
    if demo:
        labels = {'summary': '摘要', 'translate': '翻译', 'rewrite': '润色', 'qa': '问答'}
        samples = {
            'summary': '核心信息：讨论内容需要进一步明确时间、参与人员和下一步行动。建议将确定事项与待确认事项分开记录。',
            'translate': f'这是目标语言「{request.language}」的演示输出。真实服务将使用你配置的 AI 接口翻译输入内容。',
            'rewrite': '建议先明确目标与时间，再用简短句子表达具体安排，让群友更容易理解和回应。',
            'qa': '演示管家已收到问题。配置自己的 AI 密钥后，这里会基于输入内容与账号知识库生成真实回答。',
        }
        return {'text': f'【演示{labels[request.operation]}，未调用真实 AI】\n' + samples[request.operation], 'demo': True}
    cfg = vault.settings(request.account_id)
    cfg.validate(credentials=True)
    instructions = {
        'summary': '请总结用户提供的文本，区分已确定事项、待确认问题与下一步行动。不要补充原文不存在的事实。',
        'translate': f'将用户提供的文本准确翻译为{request.language}。保留人名和数字，不改变含义。只输出译文。',
        'rewrite': '润色用户提供的文本，使其更自然、清晰、简短。保留原意，不添加承诺或新事实。只输出润色正文。',
        'qa': '根据用户问题提供有帮助且准确的回答；需要时使用账号所有者提供的知识库。不确定时如实说明。',
    }
    cfg = replace(cfg, persona=cfg.persona + '\n当前任务：' + instructions[request.operation],
                  max_reply_chars=3000, ai_output_tokens=1800)
    ai = ChatAI(cfg)
    try:
        async with slots:
            output = await ai.generate([{'role': 'user', 'content': text}])
        if not output.strip() or output.strip() == '[SKIP]':
            raise ValueError('AI 未返回可用草稿，请调整输入后重试')
        vault.event(request.account_id, 'tool', 'AI 工作台已生成草稿，未向 Telegram 发送')
        return {'text': output[:3000], 'demo': False}
    finally:
        await ai.close()
