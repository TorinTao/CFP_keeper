# 架构说明

目标：**一层的代码只依赖接口，不依赖具体实现**。换存储、换抓取器、换通知方式，都不需要改业务代码。

```
              ┌──────────────────────────────┐
   HTTP 请求 → │  api/       路由 + JSON 编解码 │
              └──────────────┬───────────────┘
                             │ 只调用服务
              ┌──────────────▼───────────────┐
              │  services/  用例编排          │
              │  catalog / scraper /          │
              │  reminders / scheduler        │
              └──────────────┬───────────────┘
                             │ 只依赖 Protocol
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼────┐         ┌─────▼─────┐        ┌─────▼─────┐
   │  ports  │◄────────┤  domain   │        │ adapters  │
   │ 接口定义 │         │ 纯规则     │        │ 具体实现   │
   └─────────┘         └───────────┘        └───────────┘
```

依赖方向永远向内：`api → services → ports ← adapters`，`domain` 谁都可以用，但它不 import 任何东西。

## 模块职责

| 层 | 模块 | 职责 | 允许依赖 |
|---|---|---|---|
| domain | `deadlines.py` | 时区换算（AoE/PST）、倒计时、数据新鲜度 | 标准库 |
| domain | `cfp_parser.py` | 从页面文本抽取候选日期（正则 + 关键词锚定） | `deadlines` |
| domain | `guards.py` | 自动写入策略：哪些候选可以覆盖数据库 | 标准库 |
| domain | `views.py` | 会议 → 视图模型（下一条截止、是否待复核） | `deadlines`, `schema` |
| domain | `verification.py` | 核验判定：页面 vs 库中日期 → verified/updated/mismatch/not_found | 标准库 |
| domain | `ics.py` | 生成 .ics 文本 | `deadlines` |
| domain | `schema.py` | 字段白名单与校验 | `deadlines` |
| services | `catalog.py` | 查询/筛选、关注状态、确认截止时间 | `ports`, `domain` |
| services | `scraper.py` | 抓取→解析→守卫→写入→审计，产出运行记录 | `ports`, `domain` |
| services | `verifier.py` | 核验：抓取→解析→判定→升状态/更新→审计；首页会跟一步到 Important Dates | `ports`, `domain` |
| services | `reminders.py` | 阈值提醒 + 每日周报，去重 | `ports`, `domain` |
| services | `scheduler.py` | 每日自动抓取的时机判断 | `ports` |
| adapters | `json_store.py` | 用 JSON 文件实现 Repository（原子写 + .bak） | `ports`, `domain` |
| adapters | `cli_fetcher.py` | Lexmount Web Fetch（`extract` + `dump-dom`）实现 Fetcher | `ports` |
| adapters | `browser_fetcher.py` | Lexmount Cloud Browser：session create/open-url/eval/close | `ports` |
| adapters | `fallback_fetcher.py` | 链式 Fetcher：正文过短时才开浏览器 | `ports` |
| adapters | `windows_toast.py` | 用 PowerShell 实现 Notifier | `ports` |
| adapters | `json_config.py` | config.json ↔ AppConfig | `ports` |
| adapters | `clock.py` | 系统时钟 | `ports`, `domain` |
| api | `application.py` | 组合根：装配适配器与服务，处理设置与并发 | 全层 |
| api | `handlers.py` | 路由、状态码、JSON 编解码 | 只调 `application` |

## 端口（可替换点）

| 端口 | 方法 | 现在 | 换成什么 |
|---|---|---|---|
| `Repository` | load/save venues、state、candidates、runs、reminders、audit | JSON 文件 | SQLite、Postgres、远端 API |
| `Fetcher` | `fetch(url) → FetchResult` | Lexmount CLI | HTTP 直连、Playwright、第三方抓取 API |
| `Notifier` | `notify(title, msg)` | Windows toast | 邮件、Slack、企业微信 |
| `Clock` | `now()` / `to_local()` | 系统时钟 | 测试用固定时钟、时区改写 |
| `ConfigStore` | `load()` / `save()` | config.json | 环境变量、KMS、数据库 |

替换步骤（以 SQLite 为例）：
1. 新写 `app/adapters/sqlite_store.py`，实现 `Repository` 的方法；
2. 在 `app/api/application.py` 里把 `JsonStore(...)` 换成 `SqliteStore(...)`；
3. 业务代码、测试一行不用改。

## 鲁棒性约定

1. **适配器不抛异常**：`Fetcher.fetch` 永远返回 `FetchResult(ok=False, error_code=...)`；`Notifier.notify` 返回 `(False, detail)`。失败被记录，不中断流程。
2. **写库前校验**：`JsonStore.save_venues` 调用 `domain.schema.validate_venues`，非法文档拒绝落盘。
3. **原子写 + 备份**：临时文件 → `os.replace`，旧版本留 `.bak`；损坏时自动回退并标记 `degraded`。
4. **决策与执行分离**：`guards.plan_auto_apply` 是纯函数，返回「写入哪些 / 拒绝哪些 + 原因」，写库由 service 完成，因此策略可以单独测试。
5. **审计**：每次自动写入都写 `auto_applied.jsonl`（before/after），可回溯。
6. **线程边界**：只有 `ReminderService` 和 `DailyScraper` 是线程，且 `tick()` 同步可测；HTTP 抓取在独立 daemon 线程，用锁保证单飞。

## 测试布局（73 个用例）

| 层 | 文件 | 覆盖 |
|---|---|---|
| domain | `test_deadlines.py` | AoE/PST 换算、跨日、异常输入、新鲜度 |
| domain | `test_cfp_parser.py` | 中英日期、workshop 不误判、时区识别、去重 |
| domain | `test_guards.py` | 7 条守卫逐条覆盖 |
| domain | `test_views.py` | 下一条截止、待复核、无效日期、排序 |
| domain | `test_verification.py` | verified/updated/mismatch/not_found、pending_only |
| domain | `test_link_discovery.py` | 从首页找 Important Dates 链接 |
| domain | `test_ics.py` | 结构、UTC、3 个 VALARM、折行、转义 |
| adapters | `test_json_store.py` | 原子写、备份恢复、非法文档拒绝、审计 |
| adapters | `test_fallback_fetcher.py` | 正文过短才走浏览器、失败不盲目开浏览器 |
| services | `test_scraper.py` | 成功/失败、自动写入、人工核验保护、歧义、venue 过滤 |
| services | `test_verifier.py` | 一致→verified、漂移→updated、大偏差→mismatch、首页跟链 |
| services | `test_reminders.py` | 阈值去重、周报时间、通知失败降级、期刊跳过 |
| services | `test_scheduler.py` | 到点触发、当天去重、补跑、丢失重试、禁用 |
| api | `test_api.py` | 健康检查、列表/详情/404、关注、设置校验、ICS、静态与路径穿越 |

服务层测试全部使用 `tests/fakes.py` 里的内存实现（`InMemoryRepository`、`FakeFetcher`、`FakeNotifier`、`FakeClock`），**不碰文件系统、不联网、不起线程**，所以整套测试 < 1 秒。

## 常见改动怎么做

| 想做的事 | 改哪里 |
|---|---|
| 新增一个会议 | `scripts/seed.py` 的 `CONF` 列表，重跑脚本 |
| 调整自动写入策略 | `app/domain/guards.py`（+ 对应测试） |
| 换抓取后端 | 新增 `Fetcher` 实现 → 在 `application.py` 换一行 |
| 换存储 | 新增 `Repository` 实现 → 换一行 |
| 新增 API | `app/api/handlers.py` 加路由 → 逻辑放 service |
| 改提醒规则 | `app/services/reminders.py`（+ 测试） |
