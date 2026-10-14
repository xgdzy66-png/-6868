# Telegram 普通账号 AI 群聊管家

这是独立的 Python 程序，使用你自己的 **普通 Telegram 账号**，不是 BotFather 机器人。首次通过手机号登录，之后复用本机登录会话，在指定群中根据最近对话自动接话。不会修改同一仓库里的库存机器人，也不会注册或覆盖 Bot Webhook。

**当前交付是可配置运行的程序，不代表你的 Telegram 账号已登录，也不代表已经在群里发过消息。**

## 支持的功能

- 在群白名单内聊天；不自动加群，不处理陌生私聊，不向其他群发送。
- 支持 @本人、回复本人时回应，也支持按概率参与普通群聊。
- 每个群保留最近 24 条上下文；论坛群按主题隔离。上下文默认保留 24 小时，在处理活跃群消息时清理过期内容。
- 默认每群冷却 60 秒，每群每小时最多 20 次尝试，每滚动 24 小时最多 100 次尝试。AI 试运行草稿和网络状态不明的发送也占用配额。
- 默认先试运行：生成草稿但不发群回复。账号本人在收藏夹发送 `/ai_preview` 查看最近草稿。
- 管家人设、模型、回复概率、长度和延迟可配置。
- 管理员可暂停、恢复、切换模式或清除本地记忆。暂停状态重启后仍保留。
- 排除本人普通发言与 Bot 消息；活跃群不积压待回复任务；AI 或 Telegram 出错不向群里发错误文本。

## 运行环境

Python 3.11 或更新版本，Linux 或 macOS。Windows 请在 WSL2 的 Ubuntu 中运行。电脑或服务器必须能正常访问 Telegram 和你的 AI 服务。

该程序是常驻进程，需要运行设备一直在线。这里没有为你开通或部署全天在线服务；普通临时沙盒可能休眠，不能当作 24 小时服务器。已有 Linux 服务器可用下方 systemd 配置持续运行。

## 1. 安装

下载压缩包并解压。如果使用 GitHub 仓库，请进入 `ai-chat` 子目录；压缩包用户则进入 `tg-ai-steward` 目录。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

在 [Telegram 应用管理页面](https://my.telegram.org/apps) 创建你自己的 API 应用，取得 `api_id` 和 `api_hash`，填入 `.env`：

```dotenv
TG_API_ID=你的数字API_ID
TG_API_HASH=你的API_HASH
AI_API_KEY=你的AI服务密钥
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-5-mini
```

必须使用自己的 AI 服务凭据。示例模型名只是配置示例，请确认你的服务支持该模型。程序不会自动获得 Manus 内置凭据，压缩包里也不包含任何真实密钥。兼容服务的 `AI_BASE_URL` 通常包含 `/v1`，不要包含 `/chat/completions`。

GPT 接口默认使用 `AI_TOKEN_PARAMETER=max_completion_tokens`。其他兼容模型如果不支持这个参数，可改成 `max_tokens`。可通过 `AI_EXTRA_JSON` 传入服务特定参数，例如 `{"reasoning":{"effort":"minimal"}}`；不能覆盖消息、模型或工具配置。

## 2. 首次手机号登录

```bash
python -m tg_ai login
```

在**你自己的交互终端**输入含国家区号的手机号，然后输入 Telegram 收到的验证码；如果账号开启了两步验证，再输入两步验证密码。验证码和密码输入时不会回显。不需要也不应把这些内容发到聊天或 GitHub。

会话保存在 `data/account.session`，以后启动无需再次登录。该文件相当于账号登录凭据，绝不能分享。程序运行时必须使用已建立的普通账号会话，不会在后台自动询问验证码。

## 3. 选择群

账号要先自行加入你想使用的群。获取已加入群列表：

```bash
python -m tg_ai groups
```

将目标群 ID 填入 `.env`，例如：

```dotenv
TG_ALLOWED_GROUPS=-1001234567890,-1009876543210
```

这些是示例，必须替换为真实群 ID。白名单为空时不能启动聊天。本账号本人始终可管理；需要其他人控制时，把其数字用户 ID 填入 `TG_OWNER_IDS`，多人用英文逗号分隔。不需要授权时保持为空。

## 4. 先试运行，再开启发言

```bash
python -m tg_ai check
python -m tg_ai run
```

`check` 只验证配置格式，不向 Telegram 登录，也不验证 API 密钥是否真实有效。默认 `CHAT_DRY_RUN=true`：收到触发消息后生成草稿，但不向群发送 AI 回复。在 Telegram **收藏夹（Saved Messages）**发送 `/ai_preview` 查看最新草稿。

确认语气合适后，停止程序，把 `.env` 改为：

```dotenv
CHAT_DRY_RUN=false
```

再启动 `python -m tg_ai run`。按 Ctrl+C 停止。也可运行 `./start.sh`，它会准备虚拟环境并检查配置，但**不会自动登录或关闭试运行**。

管理命令的反馈由程序正常发送，试运行仅阻止 AI 群聊回复，因此群内管理命令仍会产生控制反馈；建议在收藏夹管理。

## 回复模式与语气

`CHAT_REPLY_MODE=mentions` 只在别人 @本账号，或回复本账号的消息时参与。

`CHAT_REPLY_MODE=smart` 同样响应 @和回复；对普通群聊按 `CHAT_REPLY_PROBABILITY` 概率接话。默认 0.15，也就是每条符合条件的普通消息有 15% 的触发机会，不是保证回复其中 15%。账号没有用户名时，仍支持 Telegram 的指名提及实体和回复触发。

`CHAT_REPLY_MODE=all` 每条符合条件的消息都可能触发。所有模式仍受冷却、配额、暂停与 AI 的 `[SKIP]` 选择约束，不保证每条都回复。

修改 `.env` 后需重启。示例：

```dotenv
CHAT_PERSONA="你是群里的 AI 管家，友好随和，像日常聊天一样简短自然，适时幽默，避免反复自我介绍，不刷广告。"
CHAT_REPLY_MODE=smart
CHAT_REPLY_PROBABILITY=0.15
CHAT_COOLDOWN_SECONDS=60
CHAT_HOURLY_LIMIT=20
CHAT_DAILY_LIMIT=100
CHAT_MAX_REPLY_CHARS=500
```

程序不主动定时发起话题，而是在新消息到来时参与，避免无人聊天时持续刷屏。上下文只来自启动后实际处理的新消息，不会拉取整个历史群聊；超过默认 120 秒的旧消息忽略。

## 管理命令

在收藏夹发送以下命令最方便：

```text
/ai_help
/ai_status
/ai_pause all
/ai_resume all
/ai_pause -1001234567890
/ai_resume -1001234567890
/ai_mode mentions all
/ai_mode smart -1001234567890
/ai_clear -1001234567890
/ai_preview
/ai_id
```

在群内发送 `/ai_pause` 或 `/ai_resume`，默认作用于当前群；在私聊或收藏夹发送，默认作用于全部群。全局暂停未解除时，单独恢复某个群不会越过全局暂停；`/ai_resume all` 会同时解除全局和各群暂停。

`/ai_clear` 必须明确一个群，清除的是本机上下文，不会删除 Telegram 消息。配额不会因清除记忆而重置。`/ai_preview` 仅可在收藏夹或授权管理员私聊查看，且草稿只保留在当前进程内存中。

默认只有账号本人有权限，群成员不能通过聊天文本授予自己管理权限。控制反馈也限速，连续命令建议间隔至少 2 秒。群内命令不带 Bot 用户名后缀，例如不要写 `/ai_pause@some_bot`。

## Linux 服务器持续运行

先把程序放在 `~/tg-ai-steward`，按前述步骤安装、登录、配置并试运行。确认可以正常运行后安装随附的**用户级** systemd 服务：

```bash
mkdir -p ~/.config/systemd/user
cp tg-ai-steward.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tg-ai-steward
journalctl --user -u tg-ai-steward -f
```

如果实际安装目录不是 `~/tg-ai-steward`，先修改 service 中的路径。若希望 SSH 退出后继续运行，可自行执行 `sudo loginctl enable-linger "$USER"`。不要同时启动手动进程和 systemd 服务；相同数据目录有单实例锁。

停止与重启：

```bash
systemctl --user stop tg-ai-steward
systemctl --user restart tg-ai-steward
```

## 隐私与限制

指定群的部分文本会发送给你配置的 AI 服务，并保存在本机 SQLite 中。只在你获准使用自动账号、且允许这样处理消息的群启用，必要时提前向成员说明 AI 自动回复。草稿不写入普通日志，日志仅包含状态和群 ID；本地上下文仍属于敏感数据。

`.env`、`data/` 和 session 文件已经加入忽略规则。整个数据目录仅当前用户可访问；备份时保持相同权限。不要把登录文件上传到公共仓库。要终止该程序的账号访问，可先停止进程，再在 Telegram「设置 → 设备」中撤销对应会话；设备页面的显示名可能是 Telethon，需核对登录时间和设备信息。

Telegram 可能对自动化账号限流或限制使用。冷却机制可以减少刷屏，但**不能保证不被限流或封禁**。程序不实现隐瞒 AI 身份、规避检测或账号批量养号。

网络无法保证发送绝对一次。程序会记录已处理消息，发送状态不明时不自动重发；这偏向避免重复，可能漏掉一条回复。AI 临时失败后当前群冷却 60 秒；配置或授权错误会暂停所有群，修复后需重启并发送 `/ai_resume all`。

## 测试和离线演示

```bash
pip install pytest==8.4.2
python -m pytest -q
python -m tg_ai demo
```

`demo` 使用固定模拟回复，不连接 Telegram，不调用真实 AI，不发送消息。自动测试同样不需要账号和真实密钥。仓库根目录的 `pytest` 仍只运行原库存机器人测试，AI 模块测试在此目录独立运行。

交付时已经通过新模块和原库存模块的本地回归测试；没有用真实 Telegram 账号进行群内端到端发送测试。

## 参考

[1]: https://docs.telethon.dev/en/stable/basic/signing-in.html "Telethon 登录、API 凭据和会话说明"
[2]: https://docs.telethon.dev/en/stable/modules/client.html "Telethon TelegramClient API 文档"

普通账号接入和会话复用基于 Telethon。[1] [2]
