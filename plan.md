# 库存出入库 Telegram 机器人实施计划

## 目标与范围

在 @kucunxbot 上提供 `/start`、`/add 商品ID 数量`、`/remove 商品ID 数量`、`/stock 商品ID`、`/list`、`/delete 商品ID` 和 `/stats 开始日期 结束日期`。入库自动创建商品；出库不得产生负库存；删除商品不删除历史日志。每次成功入库/出库保存操作类型、商品ID、数量、操作时间和操作者，日期汇总按 Asia/Bangkok（UTC+7）计算。交付 Flask 源码、自动化测试、容器配置、GitHub/GitLab 与自建部署说明，并在本项目发布 HTTPS 服务和注册 Telegram Webhook。

## 实施方案

- **运行方式：** Flask 接收 Telegram Webhook；Gunicorn 启动生产 HTTP 服务，监听 `$PORT`（默认 3000）。Telegram 使用 `secret_token` 请求头认证，密钥由服务端 Bot Token 用 HMAC 派生，不写入源代码。公开 `/healthz` 用于部署健康检查。
- **持久化：** SQLAlchemy 管理 Manus MySQL（`DATABASE_URL`）；独立部署可通过 `DATABASE_URL` 指定 MySQL 或 SQLite。`products` 表保存商品ID及非负数量；`movements` 表保存不可随商品删除而删除的出入库流水；`processed_updates` 原子预占唯一键去重 Telegram 重试；`owners` 表保存首位授权 Telegram 用户。事务内处理库存与日志，行锁防止并发超卖。远程 MySQL 强制验证 TLS，自建 Compose 内网为显式例外。
- **权限：** 默认禁止未授权用户查看或修改库存。首次所有者通过私聊 `/claim 一次性代码` 认领，代码由 Bot Token 派生，不存放在 Git 中；已有管理员后认领关闭。`/myid` 可帮助用户获取 Telegram ID。Webhook 拒绝不匹配密钥的请求，只处理私聊。删除仅删除商品记录，明确确认回复。
- **时间/回复：** `YYYY-MM-DD` 双端包含；数据库按 UTC+7 聚合每日入库与出库；`/list` 每页 25 件，`/stats` 每页 30 天并提示后续页，确保单次 Webhook 回复有界；错误消息采用中文。
- **部署：** Managed WebDev 的 server/database 功能已启用（单向）；Dockerfile 构建 Flask 服务，受保护环境变量注入 `BOT_TOKEN`，保存 checkpoint 后手动 Publish；完成公网 `/readyz`（数据库+Token）检查后调用 Telegram `setWebhook`，验证 `getWebhookInfo`。托管资源是按需唤醒，空闲后的首条消息可能冷启动；不启用付费常驻模式。

## 项目结构

- `app/`: Flask Webhook 入口、Telegram 命令分发、库存数据库模型与业务事务。
- `tests/`: 库存、日志、统计、权限、Webhook 签名和重试幂等性自动测试。
- `scripts/`: 管理员/部署辅助工具（不包含凭据）。
- `Dockerfile`, `requirements.txt`, `.env.example`: 可移植构建及环境变量示例。
- `README.md`: 命令使用、GitHub/GitLab 与自建服务器发布和迁移说明。
- `static/`: 授权来源的简洁箱子图标；根页面只提供公开使用说明，不暴露库存。

## 页面设计（极简服务说明页）

- **Design Movement:** 轻量工业功能主义；页面辅助说明，主要操作留在 Telegram。
- **Core Principles:** 信息分层清晰、无库存数据暴露、移动端优先、指令一目了然。
- **Color Philosophy:** 深墨绿体现仓储稳定性，淡米白留白，暖黄色标记操作。
- **Layout Paradigm:** 左侧竖向品牌与状态，右侧命令卡片；移动端自然堆叠。
- **Signature Elements:** 盒子线描标志、终端风格命令行、细线分隔。
- **Interaction Philosophy:** 点击 Telegram 跳转，页面无库存写操作；动画仅限轻微悬停。
- **Animation:** 150–200ms 的颜色/阴影过渡，遵循 reduced-motion。
- **Typography System:** 系统中文无衬线标题与正文，等宽字体展示命令。
- **Brand Essence:** “让小团队用 Telegram 快速记准每一次库存变动”；专业、简洁、可靠。
- **Brand Voice:** 直接、准确；如“每笔出入库，都有迹可循”“从一条命令开始管理库存”。
- **Wordmark & Logo:** 简线货箱搭配“库存机器人”；标志仅装饰公开首页。
- **Signature Brand Color:** 深松绿 `#174A3B`。
