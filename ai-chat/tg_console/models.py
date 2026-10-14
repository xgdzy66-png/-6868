from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Input):
    password: str = Field(min_length=1, max_length=256)


class ConfigPatch(Input):
    api_id: int | None = Field(default=None, ge=1)
    api_hash: str | None = Field(default=None, max_length=128)
    ai_key: str | None = Field(default=None, max_length=512)
    ai_base: str | None = Field(default=None, max_length=300)
    ai_model: str | None = Field(default=None, min_length=1, max_length=100)
    ai_token_parameter: Literal['max_tokens', 'max_completion_tokens'] | None = None
    ai_extra_json: str | None = Field(default=None, max_length=2000)


class NewAccount(Input):
    name: str = Field(min_length=1, max_length=60)
    phone: str = Field(pattern=r'^\+[1-9][0-9]{7,14}$')

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError('账号名称不能为空')
        return value.strip()


class AccountPatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    groups: list[int] | None = Field(default=None, max_length=30)
    persona: str | None = Field(default=None, min_length=1, max_length=3000)
    faq: str | None = Field(default=None, max_length=12000)
    features: list[Literal['chat', 'faq']] | None = Field(default=None, max_length=2)
    reply_mode: Literal['mentions', 'smart', 'all'] | None = None
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    cooldown: float | None = Field(default=None, ge=10, le=3600, allow_inf_nan=False)
    hourly_limit: int | None = Field(default=None, ge=1, le=100)
    daily_limit: int | None = Field(default=None, ge=1, le=500)
    dry_run: StrictBool | None = None
    model: str | None = Field(default=None, max_length=100)

    @field_validator('groups')
    @classmethod
    def negative_groups(cls, value):
        if value is not None and any(g >= 0 for g in value):
            raise ValueError('群 ID 必须是负整数')
        return list(dict.fromkeys(value)) if value is not None else value

    @field_validator('name', 'persona')
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError('内容不能为空')
        return value.strip() if value is not None else value


class Code(Input):
    code: str = Field(pattern=r'^[0-9]{3,10}$')


class Password(Input):
    password: str = Field(min_length=1, max_length=256)


class Batch(Input):
    action: Literal['connect', 'start', 'stop']
    ids: list[str] = Field(min_length=1, max_length=30)


class ToolRequest(Input):
    account_id: str
    operation: Literal['summary', 'translate', 'rewrite', 'qa']
    text: str = Field(default='', max_length=12000)
    language: str = Field(default='中文', min_length=1, max_length=40)
    group_id: int | None = Field(default=None, lt=0)
