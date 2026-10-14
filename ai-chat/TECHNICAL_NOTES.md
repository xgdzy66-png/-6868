# 技术说明

本次开发依据用户确认的「普通 Telegram 账号（手机号登录）」实现 MTProto 客户端，不采用 BotFather Token，不更改现有库存 Bot 的 Webhook。

官方参考：

- https://docs.telethon.dev/en/stable/basic/signing-in.html ：应用需自行取得 API ID 和 API Hash，普通账号登录可复用本地 session；session 属于登录凭据。检索于 2026-10-14。
- https://docs.telethon.dev/en/stable/modules/client.html ：TelegramClient 事件、发送消息、登录和群对话 API。检索于 2026-10-14。
- https://core.telegram.org/bots/faq ：Bot API 与普通账号接入不同；现有库存 Bot 的 Webhook 不应被普通账号程序替换。检索于 2026-10-14。

实现采用 Telethon 1.45.0、httpx 0.28.1 和 python-dotenv 1.1.1，并提供固定版本依赖。AI 通过用户自行配置的 OpenAI-compatible Chat Completions 接口调用，不随程序分发任何平台密钥。

测试分为离线引擎及模拟 HTTP 接口测试、原库存机器人回归和一次真实 AI 接口冒烟调用。没有登录用户 Telegram 账号，没有发送真实群消息，没有部署常驻服务；手机号、验证码、两步验证密码需用户在自己的终端输入。
