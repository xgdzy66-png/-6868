# 网页后台接入依据

核验日期：2026-10-14。

- Telethon 1.45 官方 TelegramClient 文档：https://docs.telethon.dev/en/stable/modules/client.html
  - `send_code_request(phone)` 返回验证码流程所需的 `phone_code_hash`。
  - `sign_in(phone, code, phone_code_hash=...)` 完成验证码验证；需要两步验证时会抛出 `SessionPasswordNeededError`，随后调用 `sign_in(password=...)`。
  - `is_user_authorized()` 可核验已保存会话；`disconnect()` 仅断开本机连接。
  - `log_out()` 会撤销当前登录并删除 session，因此本后台的普通「停止」不能调用它。
  - 网页后台必须保留这些真实验证步骤，不能声称首次多个账号无需验证码即可登录。验证码不得通过 Telegram 聊天发送给其他人。

- Telegram API 应用获取官方说明：https://core.telegram.org/api/obtaining_api_id
  - 自行取得 API ID 与 API Hash。该程序不会附送或共享真实应用凭据。

- Microsoft WSL systemd 说明：https://learn.microsoft.com/en-us/windows/wsl/systemd
  - WSL 服务仍受 Windows 和 WSL 实例生命周期影响；不能用演示预览或 WSL 后台界面宣称已保证全天在线。

网页预览只用于演示，真实账号验证只能在用户自己的受保护后台进行。多账号运行保留群白名单与冷却，不实现批量加群、群发广告、规避平台限制或绕过验证码。
