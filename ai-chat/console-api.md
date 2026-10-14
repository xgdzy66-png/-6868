# 控制台内部接口约定

## Vault

`Vault(data_dir: Path)` 初始化受限目录及 `console.sqlite3`，主密钥在 `master.key`，所有 config/account 的值整体 Fernet 加密。

- `config() -> dict`：完整内部配置，包含 api_id/api_hash/ai_key/ai_base/ai_model/ai_token_parameter/ai_extra_json；缺省 api_id=0、api_hash=''、ai_key=''、ai_base='https://api.openai.com/v1'、ai_model='gpt-5-mini'、ai_token_parameter='max_completion_tokens'、ai_extra_json='{}'。
- `update_config(patch: dict)`：合并保存。
- `accounts() -> list[dict]`、`account(id) -> dict`：内部完整记录。
- `add_account(name, phone) -> dict`：UUID32hex id，name、phone，tg_user_id=None、username=''、groups=[]、persona、faq=''、features=['chat']、reply_mode='smart'、probability=.15、cooldown=60、hourly_limit=20、daily_limit=100、dry_run=True、model=''。
- `update_account(id, patch) -> dict`：合并记录。
- `events(limit=100) -> list[dict]`、`event(account_id, kind, message)`：结构化审计事件，消息由调用者传静态状态描述，不写入密钥、验证码、用户聊天。
- `settings(id) -> tg_ai.config.Settings`：根据全局 config 与账号记录组装运行配置；每账号数据路径为 `data_dir/accounts/<id>`。
- `close()` 关闭数据库。

## Manager

`Manager(vault, demo=False, client_factory=None)`，同一事件循环调用。每账号 asyncio.Lock，最多 30 个账号，有界批量并发=2。演示不连外部账号，任何新账号登录、真实密钥写入由服务路由拒绝。

- `statuses() -> dict[id, dict]`：state 使用 offline/code/password/ready/running/error；每条包括 state、error（安全文本）、connected。
- `request_code(id) -> dict`：连接本机会话；已有授权直接 ready；否则发验证码，内存保存 code hash 和 10min过期，不持久存 OTP/2FA。
- `verify_code(id, code) -> dict`：处理 code->ready 或 code->password。
- `verify_password(id, password) -> dict`：需要 password 状态时验证，完成 ready。
- `connect(id) -> dict`：仅用保存会话重连，不发送验证码；未授权返回安全错误。
- `groups(id) -> list[{id,title}]`：仅已授权账号可查加入的群。
- `start(id) -> dict`：要求已授权、AI配置、群白名单；复用 Engine 和 ChatAI；拦截本机其它 running 账号的重叠群；未登录绝不能自动后台登录。
- `stop(id) -> dict`：移除事件处理器、暂停待发送、关闭 AI 与聊天存储、断开客户端，不调用 log_out、不删除 session。
- `batch(action, ids) -> list[{id,ok,state,message}]`：actions connect/start/stop；逐账号结果，不调用 request_code；重复id去重。
- `shutdown()` 关闭所有客户端。
- `preview(id) -> {group_id,text}|None`：返回受保护的当前试运行草稿，不写审计事件。
- `chat_context(id, group_id) -> list[dict]`：只读该账号白名单群的本机存储，不拉取其他群历史。

Manager 不处理网页管理员认证，该权限统一由 server 层控制。把运行事件写入 Vault.event，不暴露第三方异常完整文本。

## Web API（JSON）

所有 `/api/*` 除登录和 session 状态均需管理员会话。所有 POST/PATCH 需要 X-CSRF-Token 与会话绑定，输入 JSON。

- GET `/api/session` -> {authenticated,demo,csrf?,configured?}
- POST `/api/login` {password} -> {csrf}
- POST `/api/logout` -> {ok:true}
- GET `/api/dashboard` -> {accounts,stats,events,config,demo}
- GET `/api/config` -> {api_id,api_hash_set,ai_key_set,ai_base,ai_model,ai_token_parameter,ai_extra_json}
- PATCH `/api/config` 支持 api_id/api_hash/ai_key/ai_base/ai_model/ai_token_parameter/ai_extra_json；空密钥字段表示保留，不用于删除。
- POST `/api/accounts` {name,phone} -> {account}
- PATCH `/api/accounts/{id}` {name,groups,persona,faq,features,reply_mode,probability,cooldown,hourly_limit,daily_limit,dry_run,model} -> {account}
- POST `/api/accounts/{id}/code/request` {} -> {state,message}
- POST `/api/accounts/{id}/code/verify` {code} -> {state,message}
- POST `/api/accounts/{id}/password/verify` {password} -> {state,message}
- POST `/api/accounts/{id}/connect` {} -> {state,message}
- POST `/api/accounts/{id}/start` {} -> {state,message}
- POST `/api/accounts/{id}/stop` {} -> {state,message}
- GET `/api/accounts/{id}/groups` -> {groups}
- GET `/api/accounts/{id}/preview` -> {preview}
- POST `/api/batch` {action,ids} -> {results}
- POST `/api/tools` {account_id,operation:'summary'|'translate'|'rewrite'|'qa',text,language?,group_id?} -> {text,demo}

公开 account 为上述安全设置字段加 phone_masked、tg_user_id、username、state、error；不返回完整手机号或任何 session/hash/key。Dashboard.stats 使用 total/connected/running/groups/replies_today；回复数来自本机记录，不伪装统计。

Demo 使用明确标注的示例账号与事件；工具输出明确 demo=true；新账号登录及密钥写入返回403。已存在演示账号的 start/stop/connect、配置非密钥字段及模式切换可模拟状态，但永远不触发 Telegram 发送。
