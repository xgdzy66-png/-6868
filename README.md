# 库存机器人 @kucunxbot

一个使用 **Python Flask + SQLAlchemy** 的 Telegram 商品出入库机器人。库存、操作流水、管理员和 Telegram 更新去重记录保存在数据库中；Webhook 使用 Telegram 的 `secret_token` 请求头校验。生产服务由 Gunicorn 启动。

## 命令

| 命令 | 用途 |
| --- | --- |
| `/start` | 查看帮助 |
| `/myid` | 查看自己的 Telegram ID |
| `/claim 一次性代码` | 首位管理员在**私聊**中认领，认领后永久关闭此入口 |
| `/add SKU001 10` | 商品入库；商品不存在时自动创建 |
| `/remove SKU001 2` | 商品出库；库存不足则拒绝，不产生流水 |
| `/stock SKU001` | 查询单件库存 |
| `/list [页码]` | 每页列出 25 件商品；回复提示下一页命令，依次可查看全部 |
| `/delete SKU001` | 删除商品记录；历史流水仍保留 |
| `/history [SKU001]` | 查看全部或指定商品最近 20 条操作流水 |
| `/stats 2026-10-01 2026-10-07 [页码]` | 两端日期均包含，按 **UTC+7** 每页显示最多 30 天统计，最多查询 366 天 |

商品 ID 为无空格且不超过 64 字符的文本；数量是 1 至 1,000,000,000 的整数。用户只能在与机器人的私聊中操作，未认领的用户不能查询或修改库存。所有成功入库/出库在同一数据库事务中写入库存与流水；删除操作也保留一条删除记录，但不计入 `/stats`。Telegram 重试可重发回复，但不会再次增减库存。

## 本地开发

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='sqlite:///./inventory.db'
# 私下将 BotFather 提供的凭据配置为 BOT_TOKEN；不要放在命令历史、源码或仓库中。
gunicorn 'app.server:app' --bind 0.0.0.0:3000 --workers 1 --threads 4
python -m pytest -q
```

本地服务的 `GET /healthz` 为轻量存活检查，`GET /readyz` 检查 Bot Token 和数据库连通性；`GET /` 为公开的命令说明页；`POST /api/telegram/webhook` 仅接受带正确 `X-Telegram-Bot-Api-Secret-Token` 头的 Telegram 更新。Webhook 必须使用公网 HTTPS；短暂本地测试可只验证自动化测试，不能将本地 HTTP 地址直接注册给 Telegram。应用若缺少 `DATABASE_URL` 会拒绝启动，避免把持久数据意外写入临时容器文件。远程 MySQL 必须在 DSN 中配置 `ssl` 且使用可信证书完成 TLS 校验；Compose 内部的 `db` 服务是唯一显式允许不使用 TLS 的例外。

## Manus 托管上线（本项目）

项目声明了受管 server + MySQL；数据库会跨部署重启持久保存。发布时 Dockerfile 启动 Flask/Gunicorn，平台注入 `DATABASE_URL`。在项目的受保护密钥界面为运行环境设置 `BOT_TOKEN`，**绝不提交**真实密钥。推送到本项目受管主分支以保存 checkpoint，再发布对应版本，确认公开 HTTPS 地址和 `/readyz` 后，在具备该密钥的环境中执行：

```bash
BOT_WEBHOOK_URL='https://你的已发布域名' python -m scripts.register_webhook
python -m scripts.claim_code
```

将第二条命令输出的 `/claim ...` **只在与 @kucunxbot 的私聊中发送一次**。`register_webhook` 在写入前验证凭据属于 @kucunxbot，并在写入后核对 Telegram 返回的 Webhook URL；不会清空待处理更新。受管的按需服务可能在空闲后冷启动，首条回复可能较慢。**不要在两套服务上交替注册同一个机器人的 Webhook**；Telegram 同时只向当前注册 URL 投递。若更换 BotFather Token，须更新受保护密钥、重新部署并重新执行注册脚本；原认领管理员仍保存在数据库中。

## 自建服务器一键部署（Docker Compose）

准备一台安装 Docker Compose v2、Python 3、curl 的 Linux 服务器，以及解析至该服务器、开放 TCP 80/443 的公网域名。Caddy 自动申请 HTTPS 证书；MySQL 8 数据保存在 `mysql-data` Docker volume 中。配置好 DNS 后，在项目目录执行：

```bash
cp .env.example .env
chmod 600 .env
# 在 .env 中填写实际域名、BotFather Token 与两个不同的随机字母数字密码。
./scripts/deploy.sh
# 首次上线后私下查看一次性认领代码：
docker compose exec -T app python -m scripts.claim_code
```

`deploy.sh` 会构建/启动容器、等待公网 HTTPS `/readyz`，并在就绪后配置及核实 Telegram Webhook；不打印 Bot Token。自建运行时数据库地址由 Compose 在服务端生成，MySQL 仅位于与应用相通的隔离内部网络，应用容器不开放数据库端口。部署机本身必须能解析并访问自己的公网域名；某些 NAT 环境不支持此回连，需在外部确认服务就绪后按文中命令单独注册 Webhook。迁移前先备份原数据库；直接切换 Webhook 只改变消息入口，不会自动迁移库存和流水。更新代码后重跑 `./scripts/deploy.sh`。证书申请可能因 DNS、80/443 防火墙或速率限制失败，须先解决问题再重试。

## GitHub / GitLab CI/CD

本项目包含 `.github/workflows/deploy.yml` 和 `.gitlab-ci.yml` 示例。它们先运行测试，再将代码复制到你**已授权且预先配置**的 Linux 服务器，调用上述部署脚本。先在服务器的 `/srv/kucunbot/.env` 保存私密配置；在 GitHub Actions Secrets 或 GitLab Protected Variables 中配置 `DEPLOY_HOST`、`DEPLOY_USER`、`SSH_PRIVATE_KEY`、`SSH_KNOWN_HOSTS`。`SSH_KNOWN_HOSTS` 应从可信渠道核对服务器公钥指纹，勿在 CI 中临时信任未经验证的主机。服务器用户必须有 `/srv/kucunbot` 写权限和 Docker 使用权限。提交 `main` 时会触发 CI；GitHub 手动触发也只允许从 main 部署，建议为生产环境设置审批与保护分支。如果仅想手动发布，请关闭自动部署 job。托管发布与自建 CI 是**两条可选路线**，不要同时将同一个 Telegram Bot Webhook 切向不同部署。GitHub/GitLab 仓库连接需要账户所有者单独授权；这里提供可直接提交的配置，不表示已替你创建仓库。

## 安全、测试与维护

真实 `BOT_TOKEN`、密码和 `.env` 必须留在服务器/托管平台的受保护环境中；`.gitignore` 已忽略本地数据库和密钥文件。该 Token 曾在任务附件中出现，建议上线后在 [@BotFather](https://t.me/BotFather) **轮换**，更新运行环境并重新注册 Webhook。认领代码由 Token 派生，第一次认领成功后会失效；不要在群聊或公开文档分享。Webhook 签名秘钥由 Token 派生，无需另存一份。Webhook 发送 Telegram 消息发生暂时故障时，服务返回非 2xx 供 Telegram 重试；数据库的 `update_id` 唯一键阻止重复扣库，但网络无法保证回复消息绝对只出现一次。

自动化测试：`python -m pytest -q`。可用 `python -m scripts.register_webhook` 注册并随后核对状态；脚本会先执行设定，故不要仅为查询状态而在另一个环境运行。首次部署会自动创建数据表；**后续 schema 改动不能仅靠 `create_all` 升级旧表**，应在维护窗口先备份，再执行单独设计的版本化数据库迁移。库存和流水没有平台自动点时恢复承诺，定期自行导出/备份数据库。图标来源：[Solar by 480 Design](https://icon-sets.iconify.design/solar/)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。Telegram Webhook 的密钥头和重试行为依据 [Telegram Bot API](https://core.telegram.org/bots/api#setwebhook)。
