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

## 管理员网页后台（本次扩展）

### 范围与认证

- 在现有 Flask 服务的 `/admin` 增加中文响应式库存后台；不改变 Telegram 命令、数据库已有表或 Webhook 路径。复用当前 `products`、`movements` 与 UTC+7 汇总规则。默认只允许已认领 Telegram 机器人的所有者操作。
- 默认采用平台提供的 **Manus OAuth** 登录。以浏览器实际 `window.location.origin` 传递回调来源，服务器仅接受当前生产域名与项目 Preview 域名（或显式配置的可信域名）；单次随机 state 与短时 SameSite=None/Secure/HttpOnly cookie 绑定。服务端兑换 OAuth code、获取 openId，并使用项目 JWT 密钥签发/验证限定项目与到期时间的 `webdev_app_session`。所有 API 再校验数据库里被授权的 openId，不能只依赖门户登录或 Preview 注入的身份。
- 首次绑定须登录 Manus 后在后台获取五分钟有效的随机代码，并由**已认领的 Telegram 所有者**在机器人私聊发送 `/bind 代码`。后台使用独立表持久化已绑定的单一 openId 和代码摘要；第二个 Manus 账号不能夺取已绑定管理权。未绑定者看不到库存。会话采用 HttpOnly/Secure/SameSite=None；写操作要求自定义 CSRF 请求头并检查 Origin。所有敏感响应禁缓存；首次绑定后无需因 Bot Token 轮换重新绑定。
- 后台首页显示 SKU 数、当前总件数、今日入/出库量；商品可搜索、分页，入库/出库与 Bot 使用同一业务事务，出库不允许负数；删除商品须二次确认且保留流水。流水按最近优先分页，支持商品过滤；日报选择日期范围并显示 UTC+7 入/出库合计。页面不向未授权访问者返回库存 JSON。
- OAuth 与 Preview 的浏览器登录需在独立新标签页进行，避免跨站 iframe 的第三方 cookie 策略使回调丢失；后台页面在未登录、已登录未绑定、已授权三种状态分别提供明确引导。自建部署若没有平台 OAuth 环境变量，机器人仍可用，但后台登录不可用，并在说明中明确。

### 模块结构

- `app/admin_auth.py`：OAuth 起始/回调、JWT 验签、绑定请求与权限/CSRF 辅助。
- `app/admin_api.py`：概览、商品、出入库事务、流水与日报的 JSON API。
- `app/storage.py`：新增 `admin_identities`、`pending_admin_binds` 表，不改旧表数据。
- `app/bot.py`：新增只有 Telegram 所有者可用的 `/bind`，完成网页管理员绑定。
- `static/admin.html`、`static/admin.css`、`static/admin.js`：无凭据的后台壳、功能界面和交互。
- `tests/test_admin.py`：覆盖 OAuth state/签名、绑定、授权、CSRF、事务、统计与数据隔离。

### 后台视觉设计

- **Design Movement:** 仓储台账与当代编辑式仪表盘的结合，延续公开页的轻工业功能主义。
- **Core Principles:** 信息密度有序、操作可回溯、私密数据先认证、手机与桌面同等可用。
- **Color Philosophy:** 以米白和墨绿营造可信台账感，浅灰层级区分数据，单一暖琥珀强调关键库存动作和警示。
- **Layout Paradigm:** 桌面为窄侧栏导航与宽主工作区，顶部横向指标带、下方商品主表与流水侧列；移动端变成顶部横向导航和堆叠表格卡，不做拥挤的等宽宫格。
- **Signature Elements:** 细线编号和单据分割、绿色货箱标记、等宽库存数字及低库存琥珀提示。
- **Interaction Philosophy:** 搜索、日期筛选、分页无整页刷新；写操作提交后更新概览和列表，删除前明确确认。首次登录以显著步骤引导管理员在 Telegram 私聊授权。
- **Animation:** 120–180ms 状态淡入及按钮反馈，不做装饰性浮动；尊重 prefers-reduced-motion。
- **Typography System:** 中文以系统无衬线（PingFang SC / Noto Sans CJK SC）为主，英数和 SKU 采用等宽（IBM Plex Mono/系统 monospace）构成台账视觉。
- **Brand Essence:** “让店铺库存与出入库记录在一个安全、清楚的地方同步呈现”；可信、敏捷、克制。
- **Brand Voice:** 简练的操作型语气，例如“库存，一眼有数。”“每次变动，都留得住。”避免空泛欢迎语。
- **Wordmark & Logo:** 复用已有货箱图标，旁配竖线字标“库存 / 管理台”，避免额外品牌资产。
- **Signature Brand Color:** 深松绿 `#174A3B`，暖琥珀 `#D99735` 仅用于提示与强调。
