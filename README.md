# CFP Keeper · 科研会议截稿日历助手

面向「医学多模态 + AI」研究者的本地截稿日历：**什么时候截、投哪个赛道、还差什么材料、什么时候该动手**。
数据每天自动抓取（Lexmount Web Fetch），过安全边界的候选直接入库，其余留人工判断。

## 快速开始

```powershell
cd cfp-assistant
python scripts/seed.py        # 首次：生成完整候选集（47 条，含推测值）
python app/server.py          # 打开 http://127.0.0.1:8770/
```

- 纯 Python 标准库，无需 `pip install`；仅监听 `127.0.0.1`。
- 端口被占用时自动顺延并打印实际 URL。
- 测试：`python -m unittest discover -s tests -t .`

## 数据维护

当前库：**47 条**（24 个会议 + 23 个期刊）。**所有条目都保留**，只是按证据程度标不同状态：

| 状态 | 含义 |
|---|---|
| 人工核验 | **你本人**在详情页表单里录入的 |
| 自动核验 | 程序（含浏览器采集）读取官网原文核对通过 |
| 第三方来源 | 来自 CCFDDL 数据集，官网未读到 |
| 官网未公布 | 已访问官网，该日期尚未发布（待核验） |
| 官网不可达 | 站点打不开/反爬，暂缓 14 天再试 |
| 待核验 / 会期 | 按历年规律推测（尚未核对） |

```powershell
python scripts/seed.py               # 重新生成完整候选集
python scripts/verify_offline.py     # 用已采集页面做一次核验
python scripts/report_verified.py    # 输出「有证据的截止」清单
```

可选（默认不执行）：`scripts/prune_unverified.py` / `prune_deadlines.py` 会删掉没有证据的条目，`scripts/restore_removed.py` 负责加回。备份在 `data/backups/`。

## 展示规则（可信度可视化）

| 状态 | 日期列 | 剩余天数 |
|---|---|---|
| 自动核验 / 人工核验 | 精确日期 + 北京时间 | **黑色加粗** |
| 第三方来源（CCFDDL） | 精确日期 | 灰色（非官网） |
| 官网未公布 / 待人工核验 / 会期 | 模糊（如「约 2027 年 1 月中旬」）+ 推测值在 tooltip | **灰色** |

模糊粒度按上/中/下旬；未核验的日期不当作精确值使用。

状态列下方还会显示 **核验于 MM-DD HH:mm**；如果官网和库里对不上，会多一个红色 **数据不一致** 徽章（悬停可看官网日期与差异天数）。
期刊行标注「经验值，未经核验」——审稿周期是经验数据，没有官方来源。

移动端：≤760px 时表格自动变成卡片，每张卡显示名称、截止类型、剩余天数、状态与跳转按钮。

## 页面结构

顶部固定导航栏：**日历 / 全部 / 关注**，右侧是下一场倒计时、设置入口与服务状态灯。

```
┌ 日历 │ 全部 │ 关注 ────────── 下一场 10 天 · CVPR 全文截止   [设置] ● ┐
├ 日历：全年日历（全部/仅关注），截止日高亮 + 彩色圆点               │
├ 全部：领域分类 + 类型/时间/主题/搜索 + 全量列表                     │
└ 关注：收藏的会议/期刊                                             ┘
```

- 视图切换会同步 URL hash（`#all` / `#watch`），可以收藏或直接打开某个视图。
- 导航栏右侧常驻一行「下一场 N 天 · 会议 截止」，任何页面都能看到最近的死线（悬停显示原始时区）。
- 日历上，有截止的日期是**浅蓝底 + 加粗日期数字 + 圆点**：实心＝已核验，空心＝未核验（推测）。默认只显示「已核验」，可切到「含推测」；年份默认取最近一个截止的年份。
- 星标（☆）是唯一收藏入口，收藏结果立刻出现在「关注」页。

| 操作 | 结果 |
|---|---|
| 点行 | 打开详情抽屉 |
| 行内 `官网↗` / `CFP↗` / `DBLP 往届↗` | 新标签页打开，不误触发行点击 |
| 星标 ☆ | 收藏，立刻反映到「关注」页 |
| 点日历某天 | 弹出当天全部截止，点条目直达详情 |
| 主题下拉 | 按主题筛选，命中主题在行内高亮 |

## 三个容易翻车的点

### 1. AoE 不是北京时间

`23:59 AoE`（UTC-12）换算成北京时间要**加 20 小时**：

| 原始写法 | 北京时间 |
|---|---|
| 2026-12-07 23:59 AoE | 2026-12-08 19:59 |
| 2026-12-07 23:59 PST | 2026-12-08 15:59 |

工具里每个截止都**双时区并排**显示，日历按北京时间落点。

### 2. 「推测」不等于「核验」

每个截止有四种状态，区别是**有没有来源证据**：

| 状态 | 含义 | 来源 |
|---|---|---|
| `confirmed` | 人工核验 | 人点过官网，附 URL + 时间 + 原文片段 |
| `verified` | 自动核验 | 系统刚访问官网比对过，"待复核"变成它 |
| `scraped` | 自动抓取 | 抓取写入，但还没核验 |
| `unpublished` | 官网未公布 | 已访问官网但页面上没有该日期，**保留推测值，待核验** |
| `blocked` | 官网不可达 | 试过但站点访问不了（海外站），**保留推测值** |
| `predicted` | 待核验 | 按历年规律推测，**从未核对过官网** |

抓取失败**绝不覆盖**已有数据；`confirmed` 的行永远不会被自动改写。
点导航栏的 **核验** 按钮，就把所有 `predicted` / `scraped` / `unpublished` 的条目拿去官网比对一遍。

### 3. 会议和期刊不是一回事

期刊是滚动投稿，没有 deadline：不进日历、不触发提醒，单独显示审稿周期。

## 期刊核验

期刊没有截止日期，所以核验的是**其他字段**，来源分两级：

| 字段 | 来源 | 性质 |
|---|---|---|
| 全称 / 出版社 / ISSN | **Crossref**（`api.crossref.org`） | 权威注册数据 |
| 影响因子 / 审稿周期 / 录用比例 / 是否 OA | **LetPub**（`letpub.com.cn`） | 第三方，网友分享经验值 |

- 入口：设置页「立即核验期刊」，或 `POST /api/journals/verify`。
- 每个期刊存 `identity`（Crossref）与 `metrics`（LetPub），各自带 `source` / `url` / `checked_at`。
- LetPub 限流很凶（返回「访问速度过快」小页面），客户端做了 3 秒节奏 + 退避重试；没有数据的字段留空，不写成 `：`。

## 核验（把「待复核」变得可信）

信源优先级：**官网当届页面 > CCFDDL 数据集（标注「第三方来源」）> 官网未公布**。
CCFDDL（ccfddl.github.io，383 个 CCF 会议）提供每届的官方链接和日期时间线，用来发现当届页面、并在官网无数据时兜底。

两条路径，都走 Lexmount：

1. **手动**：导航栏「核验」→ 核对全部待复核条目；抽屉里的「立即核验」→ 只核这一个会议。
2. **自动**：每天 **10:00**（设置页可改）后台跑一次，结果写 `data/runs/verify-*.json`。

每个截止的判定：

| 判定 | 条件 | 动作 |
|---|---|---|
| `verified` | 官网日期与库中一致 | 状态升为「自动核验」，记录来源与检查时间 |
| `updated` | 差异 ≤ 容差（默认 30 天） | 采用官网日期 + 升状态 + 写审计日志 |
| `mismatch` | 差异 > 容差 | **不改**，留给人工判断 |
| `not_found` | 页面上找不到该类型 | 不改，保持原状 |

## 用到的 Lexmount 能力

| 能力 | 用途 | 调用 |
|---|---|---|
| **Web Fetch**（`webfetch-cli extract`） | 默认路径：读 CFP 页面正文（`lightmount_*` 引擎，秒级） | `extract --url <url> --format json` |
| **Cloud Browser**（`browser-cli`） | 兜底：页面是 JS 渲染或 Web Fetch 返回 `thin_content` 时，真开一个云浏览器取 `innerText` | `session create → action open-url → action eval → session close` |

链路封装在 `adapters/fallback_fetcher.py`：先 Web Fetch，判定「失败或正文 < 200 字」才走 Browser，所以日常成本仍是秒级。开关在设置页「渲染兜底」。

每次抓取/核验的证据都落盘：引擎名、request_id / session_id、耗时、正文长度、warnings、错误码。

## 自动抓取

每天 **09:00** 自动执行（设置页可改，改完 30 秒内生效）。

- 服务在 09:00 后启动会**立即补跑**；已跑过的标记落盘，重启不重复。
- 抓取途中进程被杀（有标记无运行记录）→ 下一轮识别为「丢失」并重试。
- 每次运行写 `data/runs/<run_id>.json`：耗时、HTTP 状态、引擎、request_id、正文长度、warnings、错误码、候选数、自动写入/拒绝明细。

### 自动写入的 7 条守卫

| 守卫 | 原因码 |
|---|---|
| 日期必须在未来 | `not_in_future` |
| 类型必须是该会议已声明的 | `kind_not_declared` |
| 不覆盖人工核验 | `human_verified` |
| 新值须在当前值 ±90 天内 | `outside_guard_window` |
| 只允许 abstract/full_paper/supplementary/notification/camera_ready | `kind_not_auto` |
| 同一类型只能有一个不同日期 | `ambiguous` |
| 值与现状相同则跳过 | `unchanged` |

每次自动写入追加到 `data/auto_applied.jsonl`（before/after 全量记录，可手工回滚）。

## 设置页

右上角「设置」：自动抓取开关与时间、下次/上次运行、立即抓取一次、自动写入与安全窗口、提醒阈值与周报时间、桌面通知，以及 **`.ics` 导出**（90 天 / 180 天 / 一年 / 三年）。

导出事件为 UTC 时间、含提前 7/3/1 天提醒；期刊不导出。

## 数据模型（`data/venues.json`）

```jsonc
{
  "id": "miccai-2027", "abbr": "MICCAI", "edition": "2027",
  "type": "conference",            // conference | journal
  "rolling": false,                // 期刊为 true
  "areas": ["medical-imaging", "ai"],
  "topics": ["影像分割", "多模态融合"],
  "tracks": [{ "name": "主会", "kind": "main", "note": "8+4 页 LNCS" }],
  "acceptance": { "display": "约 32%", "percent": 32.0, "scope": "主会", "year": "2023",
                  "note": "近年统计值，逐年波动；投稿前以官网为准" },
  "submission": { "system": "CMT", "preprint": "allowed", "code": "encouraged",
                  "access": "registration", "attendance": "in-person", "rounds": "2 轮" },
  "deadlines": [{ "kind": "full_paper", "date": "2027-02-25", "time": "23:59", "tz": "AoE",
                  "track": "主会", "source_status": "predicted", "source": {} }],
  "materials": ["摘要", "全文"], "page_limit": "8+4 pages", "blind": "double",
  "review_cycle_weeks": null
}
```

支持的 `tz`：`AoE`(-12)、`UTC`、`PST`(-8)、`PDT`(-7)、`EST`(-5)、`EDT`(-4)、`CET`(+1)、`CEST`(+2)、`JST`/`KST`(+9)、`Asia/Shanghai`/`CST`(+8)。

## 已知限制

1. 不做夏令时推断：`PST` 永远 -8，需要 -7 时标 `PDT`。
2. `CST` 按中国标准时间（+8）处理。
3. 抓取成功率受网络限制：海外被墙站点（CVPR 的 thecvf.com 等）会 `browser_fetch_failed`，已记录错误码并保留旧数据。
4. 抽取是启发式的：首页新闻日期可能被误抽；自动写入有 7 条守卫，其余转人工。
5. 无鉴权、单用户；不要反代到公网。
6. 种子数据除 IPMI 2027 外均为 `predicted`，首次使用应逐个核对官网。
7. 自动抓取需要进程常驻；关掉窗口就不会跑（要真正的后台执行需注册计划任务）。

## 代码结构

四层，依赖只向内：

```
app/
  ports.py              接口定义（Clock / Fetcher / Notifier / Repository / ConfigStore）
  domain/               纯规则，无 I/O，可单独测试
    deadlines.py        时区换算与倒计时（AoE 的坑都在这里）
    cfp_parser.py       页面文本 → 候选日期
    guards.py           自动写入策略：哪些候选能覆盖数据库
    views.py            会议 → 视图模型（下一条截止、待复核）
    ics.py              .ics 生成
    schema.py           字段白名单与校验
  services/             用例编排，只依赖 ports
    catalog.py          查询/筛选/关注/确认
    scraper.py          抓取→解析→守卫→写入→审计
    reminders.py        阈值提醒 + 每日周报
    scheduler.py        每日自动抓取的时机判断
  adapters/             具体实现，可整体替换
    json_store.py       JSON 文件存储（原子写 + .bak）
    cli_fetcher.py      Lexmount CLI 子进程
    windows_toast.py    Windows 通知
    json_config.py      config.json
    clock.py            系统时钟
  api/
    application.py      组合根：装配适配器与服务
    handlers.py         路由与 JSON 编解码
  server.py             入口（python app/server.py）
web/                    index.html app.js style.css
tests/                  domain / services / adapters / api 四层各自的测试 + fakes.py
scripts/                seed.py verify-nav.js
docs/                   architecture.md evidence.md screenshots/
```

换存储只需实现 `Repository` 并在 `application.py` 改一行；换抓取后端同理。详见 [架构说明](docs/architecture.md)。

## 测试

```powershell
python -m unittest discover -s tests -t .
```

118 个用例，按层组织：

| 层 | 文件 | 覆盖 |
|---|---|---|
| domain | `test_deadlines` `test_cfp_parser` `test_guards` `test_views` `test_ics` `test_verification` `test_link_discovery` | 纯规则，无依赖 |
| adapters | `test_json_store` `test_fallback_fetcher` | 存储与抓取链路 |
| services | `test_scraper` `test_verifier` `test_reminders` `test_scheduler` | 用 `tests/fakes.py` 的内存实现 |
| api | `test_api` | 真实 HTTP 服务 + 假适配器 |

服务层测试不碰文件系统、不联网、不起线程，整套 < 1 秒。

浏览器端回归：`node scripts/verify-nav.js`（需要服务在跑）。
