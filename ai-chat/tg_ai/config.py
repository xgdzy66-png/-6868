from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


def ids(value: str) -> frozenset[int]:
    try:
        return frozenset(int(v.strip()) for v in value.split(',') if v.strip())
    except ValueError as exc:
        raise ConfigError('群 ID 和管理员 ID 必须是逗号分隔的整数') from exc


@dataclass(frozen=True)
class Settings:
    groups: frozenset[int] = frozenset()
    owners: frozenset[int] = frozenset()
    reply_mode: str = 'smart'
    probability: float = 0.15
    cooldown: float = 60
    hourly_limit: int = 20
    daily_limit: int = 100
    delay_min: float = 2
    delay_max: float = 5
    context_messages: int = 24
    retention_hours: int = 24
    max_message_age: int = 120
    max_reply_chars: int = 500
    dry_run: bool = True
    api_id: int = 0
    api_hash: str = ''
    ai_key: str = ''
    ai_base: str = 'https://api.openai.com/v1'
    ai_model: str = ''
    ai_token_parameter: str = 'max_completion_tokens'
    ai_output_tokens: int = 1200
    ai_extra_json: str = '{}'
    state_dir: Path = Path('data')
    persona: str = '你是群里的 AI 管家，友好、自然、简短，使用与对方相同的语言。'

    @classmethod
    def load(cls, env_path: str = '.env') -> Settings:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
        e = os.environ
        def value(key, default, cast):
            return cast(e.get(key, str(default)))
        dry_run_value = e.get('CHAT_DRY_RUN', 'true').lower()
        if dry_run_value not in ('true', '1', 'yes', 'false', '0', 'no'):
            raise ConfigError('CHAT_DRY_RUN 必须是 true 或 false')
        try:
            result = cls(
                groups=ids(e.get('TG_ALLOWED_GROUPS', '')),
                owners=ids(e.get('TG_OWNER_IDS', '')),
                reply_mode=e.get('CHAT_REPLY_MODE', 'smart').lower(),
                probability=value('CHAT_REPLY_PROBABILITY', 0.15, float),
                cooldown=value('CHAT_COOLDOWN_SECONDS', 60, float),
                hourly_limit=value('CHAT_HOURLY_LIMIT', 20, int),
                daily_limit=value('CHAT_DAILY_LIMIT', 100, int),
                delay_min=value('CHAT_DELAY_MIN', 2, float),
                delay_max=value('CHAT_DELAY_MAX', 5, float),
                context_messages=value('CHAT_CONTEXT_MESSAGES', 24, int),
                retention_hours=value('CHAT_RETENTION_HOURS', 24, int),
                max_message_age=value('CHAT_MAX_MESSAGE_AGE', 120, int),
                max_reply_chars=value('CHAT_MAX_REPLY_CHARS', 500, int),
                dry_run=dry_run_value in ('true', '1', 'yes'),
                api_id=int(e.get('TG_API_ID', '0') or '0'),
                api_hash=e.get('TG_API_HASH', ''),
                ai_key=e.get('AI_API_KEY', ''),
                ai_base=e.get('AI_BASE_URL', 'https://api.openai.com/v1').rstrip('/'),
                ai_model=e.get('AI_MODEL', ''),
                ai_token_parameter=e.get('AI_TOKEN_PARAMETER', 'max_completion_tokens'),
                ai_output_tokens=value('AI_OUTPUT_TOKENS', 1200, int),
                ai_extra_json=e.get('AI_EXTRA_JSON', '{}'),
                state_dir=Path(e.get('CHAT_STATE_DIR', 'data')),
                persona=e.get('CHAT_PERSONA', cls.persona),
            )
        except ValueError as exc:
            raise ConfigError('配置包含非法数字，请检查 .env') from exc
        result.validate()
        return result

    def validate(self, credentials: bool = False, groups: bool = False) -> None:
        import math
        if self.reply_mode not in ('mentions', 'smart', 'all'):
            raise ConfigError('CHAT_REPLY_MODE 只能是 mentions、smart 或 all')
        if not all(math.isfinite(v) for v in (self.probability, self.cooldown, self.delay_min, self.delay_max)):
            raise ConfigError('概率与时间必须是有限数字')
        if not 0 <= self.probability <= 1:
            raise ConfigError('回复概率必须在 0 到 1 之间')
        if self.cooldown < 0 or not 0 <= self.delay_min <= self.delay_max:
            raise ConfigError('冷却时间或回复延迟无效')
        if any(v <= 0 for v in (self.hourly_limit, self.daily_limit, self.context_messages,
                                self.retention_hours, self.max_message_age,
                                self.max_reply_chars, self.ai_output_tokens)):
            raise ConfigError('配额、记忆长度和保留时间必须大于 0')
        if self.context_messages > 100 or self.max_reply_chars > 3000:
            raise ConfigError('上下文最多 100 条，回复最多 3000 字符')
        if any(g >= 0 for g in self.groups) or any(o <= 0 for o in self.owners):
            raise ConfigError('Telegram 群 ID 应为负数，用户 ID 应为正数')
        if self.ai_token_parameter not in ('max_tokens', 'max_completion_tokens'):
            raise ConfigError('AI_TOKEN_PARAMETER 不合法')
        if not self.ai_base.startswith(('https://', 'http://localhost:', 'http://127.0.0.1:')):
            raise ConfigError('AI_BASE_URL 必须使用 HTTPS（本机调试除外）')
        try:
            extra = json.loads(self.ai_extra_json)
        except json.JSONDecodeError as exc:
            raise ConfigError('AI_EXTRA_JSON 必须是 JSON 对象') from exc
        reserved = {'model', 'messages', 'stream', 'tools', 'tool_choice', 'max_tokens', 'max_completion_tokens'}
        if not isinstance(extra, dict) or reserved.intersection(extra):
            raise ConfigError('AI_EXTRA_JSON 不能覆盖模型、消息、工具或输出长度')
        if groups and not self.groups:
            raise ConfigError('先设置 TG_ALLOWED_GROUPS 白名单，再启动自动聊天')
        if credentials:
            if self.api_id <= 0 or not self.api_hash:
                raise ConfigError('普通账号需要 TG_API_ID 和 TG_API_HASH')
            if not self.ai_key or not self.ai_model:
                raise ConfigError('需要配置 AI_API_KEY 和 AI_MODEL')
