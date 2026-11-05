# 过程证据 · CFP Keeper

## 1. 任务

研究者需要持续跟踪两类信息：会议（硬 deadline、时区各异、赛道多）与期刊（滚动投稿）。现有日历工具不处理 AoE、不区分「官网核验」与「往年推测」、也不记录赛道与材料要求。

## 2. 做法

```
webfetch-cli extract        ┐
       │  ① 抓取（记录 engine / request_id / 耗时 / warnings）
       ▼
app/domain/cfp_parser.py   ② 强关键词锚定 + 日期正则 → 候选
       │
       ├─ 抓取路径 → guards（7 条守卫）→ 自动写入（scraped）+ 审计
       └─ 核验路径 → verification（4 种判定）→ 升状态 / 更新 / 不动
                     │
                     └─ 页面没日期时：dump-dom 找 Important Dates → 跟一步
```

两条路径共用同一套抓取链：**Web Fetch 优先，`thin_content` 时用 Cloud Browser 兜底**。

## 3. 实测结果（2026-11-04）

### 3.1 自动抓取（09:00 补跑）

| 指标 | 值 |
|---|---|
| 目标 | 24 个配置了 CFP 页的会议 |
| 成功 / 失败 | 18 / 6 |
| 候选 | 15 |
| 自动写入 | 1（ISBI full_paper 2027-01-15 → 2027-02-26） |
| 拒绝 | human_verified ×3 · kind_not_auto ×4 · kind_not_declared ×3 · outside_guard_window ×2 · ambiguous ×2 |

### 3.2 全量核验（手动触发，18:21）

| 指标 | 值 |
|---|---|
| 目标 / 抓到 / 失败 | 24 / 18 / 6 |
| 首页跟链（Important Dates） | 6 |
| 一致（verified） | 0（本次无同值条目） |
| 更新（updated） | 3 |
| 不一致（mismatch） | 2 |
| 页面上没有（not_found） | 21 → 标记为「官网未公布」 |
| 无法访问（blocked） | 4 → 标记为「官网不可达」 |

最终状态分布（47 条会议/期刊的 60 个截止）：人工核验 9 · 自动核验 4 · 官网未公布 22 · 官网不可达 5 · 会期 20。
**没有「待复核」了**，但也没有把没证据的条目谎称「已核验」。

失败 6 例仍是海外站：`browser_fetch_failed`（NeurIPS / EMNLP / MLHC / ICHI）与 `http_status_not_ok`（AMIA / ACM BCB）。

## 4. 踩到的两个误判（都已修）

### 4.1 「论文注册截止」被当成「全文截止」

CVPR 2027 页面有三个日期：Paper Enrollment（11-10）、Submission（11-16）、Supplementary（11-23）。
第一版抽取器没有关键词就默认 `full_paper`，于是把 11-10 写成了全文截止。

**修复**：`classify_kind` 找不到关键词时返回 `None`（该日期直接丢弃），并把 registration / enrollment / bidding 这类milestone单独归类，不参与论文截止的核验。

### 4.2 「OpenReview 账号创建日」被当成投稿截止

CHIL 的 Important Dates 是一张表：

```
Milestone                         Date
OpenReview accounts created       Friday, January 15, 2027
Submissions due                   Wednesday, February 3, 2027
```

第一版把 1-15 也识别成 full_paper（因为它附近出现了 "submission" 字样）。

**修复**：关键词必须在日期**之前**（`rfind(keyword, 0, date_pos)`），不再允许「日期后面跟着的词」参与分类。修复后 1-15 被丢弃，2-03 正确识别。

### 4.3 附带教训：我自己也误判了一次

看到 CVPR 被改成 11-11 时，我按「历年 11 月中」的直觉认定正确值是 11-13 并回滚。后来直接读官网原文：

```
Important Dates
Paper Enrollment Deadline* Nov 10, 2026 11:59 PM AOE
Submission Deadline*        Nov 16, 2026 11:59 PM AOE
Supplementary Materials Deadline Nov 23, 2026 11:59 PM AOE
```

真实全文截止是 **11-16**，我的「回滚」才是错的。已改为 confirmed 并把种子数据一并修正。
教训：**回滚也必须以来源为准**，不能凭印象。

## 4.4 为什么"核验不了"：三个真实原因（2026-11-04 排查）

| 原因 | 证据 | 处理 |
|---|---|---|
| **Web Fetch 配额耗尽** | 连续跑了几轮全量核验（每轮 ~100 次 fetch + dump-dom），CLI 返回 `webfetch_quota_exhausted`（HTTP 502） | 加配额熔断：命中即中止整轮，不再浪费浏览器时间；改用浏览器采集做当轮证据 |
| **当届 CFP 还没发布** | CCFDDL 数据集里 24 个会议只有 6 个有 2027 日期；MICCAI 官网原话 "Important Dates ... will be announced soon" | 记「官网未公布」，每日自动重试 |
| **存的 URL 是首页 + 站点是 JS 渲染** | 24 个 `cfp_url` 里 18 个是首页；ICML/NeurIPS 等正文在 JS 里 | 用 CCFDDL 的 **当届链接** 替换首页；必要时 Cloud Browser 渲染 |

另外修了两个逻辑缺陷：
1. **mismatch 守卫过严**：当届官网给出的日期与旧推测差 >30 天时被拒绝。现在来自「当届链接」的页面被信任，直接更正。
2. **届次写错**：ICLR 的 id/edition 写成了 2028，导致查不到当届数据。已改为 2027。
3. **解析误判**："Application deadline"（学会奖项申请）被当成论文截止。已把 application/award/grant/school 归为 other。

## 5. 关键工程决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 时区 | 固定偏移表 | AoE 不在 IANA 库；DST 自动推断会静默改错 |
| 抓取写入 | 默认自动，但过 7 条守卫 | 官网首页会把新闻日期误抽成候选 |
| 核验更新 | 写成 `scraped` 并注明原值 | 官网是证据不是证明，改值必须留痕待确认 |
| 人工核验 | 任何自动路径都不覆盖 | 人读过官网，置信度最高 |
| 浏览器兜底 | 只在 `thin_content` 时触发 | 海外站硬失败开浏览器也只是白等 20 秒 |
| 进程被杀 | 标记 + 同名当日运行记录双条件 | 只写标记会导致当天不再重试 |

## 6. 验证

```
单元测试   118 passed（域规则 / 适配器 / 服务 / HTTP 四层）
UI 渲染    47 行、12 个月、badge 四态、无 console 错误
核验链路   Web Fetch 18 次成功，Cloud Browser 兜底 1 次（demo 通过）
导出       /api/ics 返回 text/calendar，含 3 个 VALARM
```

## 7. 局限

1. 种子数据除 CVPR / IPMI 外均为 `predicted`，首次使用应逐个核对官网。
2. 抽取仍是启发式：`not_found` 占多数说明很多 `cfp_url` 指向的是首页而非 CFP 页，跟一步只能缓解。
3. 不支持夏令时自动推断；`CST` 固定按 +8。
4. 自动抓取/核验需进程常驻，关掉窗口即停。
5. 海外被墙站点（NeurIPS 等）目前无解，除非平台提供出口代理。
