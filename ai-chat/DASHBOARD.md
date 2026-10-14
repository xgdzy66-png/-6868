# TG Atelier 多账号 AI 管家后台

这份程序在原单账号脚本上增加网页管理后台，可在 Windows WSL2 或 Linux 服务器运行。配置从网页集中填写，不再需要逐个账号编辑 `.env`。

真实 Telegram API ID/API Hash 和 AI 密钥不会随程序提供，也不会从任务环境中复制。首次添加每个普通 Telegram 账号仍需正常验证手机号、验证码，以及必要的两步验证密码。**一键连接指复用已完成登录的会话，不是绕过首次验证。**

## 后台能做什么

账号中心支持添加最多 30 个普通账号，单独登录、连接、启动或停止，也支持多选账号后一键连接、启动或停止。多个账号拥有独立会话文件、群白名单、上下文记忆与试运行草稿。批量操作会逐账号执行并返回成功或待处理状态，不把一部分成功误报成全部成功。

每个账号可以设置人设、FAQ 知识库、模型覆盖、mentions/smart/all 回复模式、回复概率、冷却、小时和每日上限。默认试运行：生成草稿但不向群发送 AI 回复。为减少账号互相触发，本机后台不允许多个运行账号接管同一个群；可以为不同账号分配不同群。

AI 工作台提供问答、摘要、翻译和润色。摘要可使用手工输入的文本，或指定账号白名单群已经保存在本机的上下文。工作台始终输出草稿，不自动向 Telegram 发消息。

系统配置集中保存 Telegram API 应用和 AI 服务配置；密码输入框中的已有密钥不会回显，留空表示保留。账号中心显示连接状态，运行记录仅显示安全状态事件。今日回复按服务器本地日期统计真实成功发送的 AI 回复，不包含试运行、失败尝试或管理员命令反馈。

## 后台登录保护

当前实现提供**本机管理员密码**保护，适合自建部署。首次启用时由你在自己的终端设置至少 12 位管理员密码。它不是 Telegram 两步验证密码。密码保存为慢哈希；网页会话最长 8 小时，操作带 CSRF 校验，登录失败有频率限制。

首次执行初始化命令即明确启用该模式。若你希望使用 Manus 账号登录而不是本机密码，需要另行提供可用于自建域名的 OAuth 配置；本程序不会静默假装已有此类平台身份凭据。

## Windows WSL2：首次启动

如果 WSL2 尚未安装，在管理员 PowerShell 安装 Ubuntu 并按提示重启：

```powershell
wsl --install -d Ubuntu-24.04
```

打开 Ubuntu，设置 Linux 用户名和密码。在 Ubuntu 中执行：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip unzip
```

把本次完整压缩包放进 Linux 主目录并解压。最简单的复制方式是在 Ubuntu 执行 `cd ~`、`explorer.exe .`，把压缩包复制到打开的文件夹，再执行：

```bash
unzip "$HOME/tg-ai-dashboard.zip" -d "$HOME"
cd "$HOME/tg-ai-steward"
bash ./start-dashboard.sh
```

启动脚本会创建虚拟环境、安装固定版本依赖，然后在终端让你设置管理员密码；已有管理员时不会覆盖密码。浏览器打开：

**http://127.0.0.1:8080**

在 Windows 浏览器中输入刚设置的管理员密码登录。若你复制了压缩包中的 `start-dashboard-windows.cmd` 到 Windows，后续可以双击该文件启动已放在 WSL `~/tg-ai-steward` 的程序。发行版实际名称若不是 `Ubuntu-24.04`，请修改 CMD 文件默认值，或从 CMD 调用时传入发行版名称。

Windows 休眠、关机、关闭前台终端或停止 WSL 可能使程序中断。长期运行使用 Linux 服务器，不把 WSL 当作不受 Windows 生命周期影响的服务器。

## Linux 服务器：首次启动

以下以 Ubuntu 24.04 和普通 SSH 用户为例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip unzip
unzip "$HOME/tg-ai-dashboard.zip" -d "$HOME"
cd "$HOME/tg-ai-steward"
bash ./start-dashboard.sh
```

程序要求 Python 3.11 或更新版本。默认只监听 `127.0.0.1:8080`，不会把账号管理接口直接暴露到公网。

从自己的 Windows PowerShell 建立 SSH 隧道：

```powershell
ssh -N -L 18080:127.0.0.1:8080 用户名@服务器IP
```

把用户名和 IP 换成自己的真实值，保持该 SSH 窗口打开。在 Windows 浏览器访问：

**http://127.0.0.1:18080**

这样管理流量通过 SSH 加密，不需要开放服务器 8080 端口。首次连接服务器应通过可信渠道核对 SSH 主机指纹。不要将密码或私钥发给别人。

如果你以后需要公开 HTTPS 域名访问，应另外配置 TLS 反向代理，并使用 `--https-cookie --public-origin https://你的域名`。真实后台直接绑定非环回地址但没有明确 HTTPS 设置时，程序会拒绝启动。不要为了方便关闭认证或 CSRF。

## 网页中的首次配置和登录

1. **系统配置**：填写自己的 Telegram API ID、API Hash、AI Key、AI Base URL 和模型。OpenAI 官方接口的 Base URL 是 `https://api.openai.com/v1`；示例模型为 `gpt-5-mini`，需确认你的账户支持。其他厂商必须一起使用其对应的密钥、地址和 API 模型 ID。
2. **添加账号**：输入显示名称与 `+国家区号手机号`。不要包含空格或短横线。
3. **请求验证码**：按 Telegram 官方流程接收并在网页输入当前验证码。开启两步验证时，网页会接着要求输入相应密码。验证码和两步验证密码不写入数据库、日志或浏览器长期存储。
4. **群白名单**：已登录账号点击「加载已加入群组」，勾选它获准接管的群。程序不自动加群。
5. **账号分工**：选择群聊 AI 或 FAQ 问答，配置人设、FAQ、回复模式和配额。先保持试运行开启。
6. **启动**：单独启动账号，或多选已完成登录的账号后批量启动。未完成登录的账号不能靠批量按钮绕过验证码。
7. **查看草稿**：让另一位群友 @账号或回复它的消息，再在后台账号详情查看试运行草稿。本人普通群发言不会触发自言自语。
8. **正式发送**：确认草稿语气和群使用授权后，先停止账号，取消试运行、保存设置，再启动。已有账号改配置前需要先停止，避免新旧配置混用。

关闭登录向导后，可以在账号详情点击「验证登录」或「继续验证」，不需要重复添加手机号。已有会话则用「连接」直接重连。

## Linux 后台常驻运行

先完成管理员初始化与账号登录，按 Ctrl+C 停止手动后台进程。然后用相同普通 SSH 用户安装用户级服务：

```bash
cd ~/tg-ai-steward
mkdir -p ~/.config/systemd/user
cp tg-ai-dashboard.service ~/.config/systemd/user/
systemctl --user daemon-reload
sudo loginctl enable-linger "$USER"
systemctl --user enable --now tg-ai-dashboard
systemctl --user status tg-ai-dashboard --no-pager
```

查看日志、停止和重启：

```bash
journalctl --user -u tg-ai-dashboard -f
systemctl --user stop tg-ai-dashboard
systemctl --user restart tg-ai-dashboard
```

管理员密码和账号配置会保留，但后台重启后**不会自动启动账号群聊**。重新进入后台后选择「连接」和「启动」，避免重启时静默恢复群发言。不要同时在 Windows 和服务器运行同一账号接管同一个群。

## 管理员密码重设

先停止后台服务，再在该机器程序目录执行：

```bash
source .venv/bin/activate
python -m tg_console reset-password
```

输入新密码，再重启服务。不要通过网页公开注册入口重设密码。主密钥丢失会导致加密配置无法读取，不能仅靠重设密码恢复。

## 数据保存与安全边界

真实后台数据默认在 `console-data/`，包括 `console.sqlite3`、`master.key` 和每个账号的独立会话目录。API 配置和账号资料整体加密，主密钥保存在当前用户受限目录；这不能防御已完全控制该服务器的攻击者。Telethon session 和群上下文数据库依赖文件权限保护，不应被公开下载。整个目录已加入 Git 忽略规则。

备份前先停止服务，通过自己的安全渠道备份整个 `console-data/`，保持目录权限。不要把它或真实 `.env` 放入本程序压缩包、公共仓库或聊天附件。程序没有提供 session 导出或下载接口。

「停止」或「断开」仅停止本机工作，不调用 Telegram 的 `log_out()`，不会撤销账号授权。永久撤销需由你在 Telegram「设置 → 设备」中操作。

群消息会发送给你配置的 AI 服务，并保留有限本地上下文。仅在你拥有使用权限、且允许这种数据处理的群启用。Telegram 仍可能限制自动化账号；限流和配额不是不被限制的保证。本后台不提供批量加群、广告广播或绕过 Telegram 验证。

## 演示预览的限制

演示使用明确标注的示例账号，使用正常管理员登录与 CSRF 流程，但演示密码公开，仅用于查看演示。演示环境拒绝真实手机号、验证码、两步验证密码和服务配置写入；不会连接 Telegram，工具输出是标注过的固定演示草稿，不是真实 AI 结果。

可以在本机独立启动演示：

```bash
python -m tg_console serve --demo
```

演示管理员密码：`atelier-demo-2026`。这个密码不会在真实后台自动设置；真实后台管理员必须自行初始化。

## 检查与测试

```bash
source .venv/bin/activate
pip install pytest==8.4.2
python -m pytest -q
python -m tg_ai demo
```

测试不需要真实 Telegram 账号，登录状态用假客户端验证。交付时已验证实际演示网页的管理员登录、批量连接、AI 草稿，并用模拟响应验证手机号 → 验证码 → 两步验证 → 完成的页面流程。没有登录用户真实账号或发送真实群消息。

原单账号 CLI `python -m tg_ai ...` 仍可使用，原库存机器人代码和部署没有因后台而改变。
