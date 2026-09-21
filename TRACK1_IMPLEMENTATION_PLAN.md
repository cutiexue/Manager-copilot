# Manager Co-Pilot

## DSS5105 Capstone Project — Track 1 Implementation Plan

| 项目 | 内容 |
|---|---|
| Course | DSS5105 Data Science Projects in Practice |
| Track | Track 1 — The General Manager's Co-Pilot |
| Group | Group 20 |
| Team size | 6 |
| Plan version | 1.0 |
| Plan date | 2026-09-21 |
| Dataset date | 2026-04-01 |
| Repository | `cutiexue/Manager-copilot` |

> 本文档是团队的执行计划。标注为“课程要求”的内容来自 Canvas 课程材料；其余架构、阈值、分工和时间安排是团队内部方案，可在 Sprint Review 后更新。

---

## 1. Executive Summary

本项目将构建一个面向服装工厂总经理的日常运营 Co-Pilot。它不是一个只会回答问题的聊天机器人，也不是一个静态 Dashboard，而是一套能够主动工作、使用可靠工具、提供证据并安全执行操作的 AI 系统。

系统需要完成五类核心工作：

1. **Morning Briefing**：按计划生成晨报，说明昨天发生了什么、哪些订单有风险、今天需要作出什么决定。
2. **All-day Q&A**：支持多轮自然语言问答，每一轮重新查询最新数据。
3. **Standing Watches and Alerts**：将“如果某订单到星期四还没动就提醒我”转化为自动检查规则。
4. **Feasibility Estimation**：回答“800 件 hoodie 能否在 25 日前完成”，同时展示假设、估算过程和不确定性。
5. **Confirmed Actions**：草拟催办消息、添加备注、创建提醒；所有有副作用的操作都必须先确认、后记录。

项目的技术原则是：

```text
LLM 负责理解、选择工具和表达
Python Tools 负责查询、计算、判断和溯源
SQLite 负责状态、确认和审计
APScheduler 负责晨报、提醒和 standing watches
React 负责让经理快速理解并安全操作
```

MVP 不需要：

- 训练或微调模型；
- RAG、Embedding 或向量数据库；
- LangGraph；
- 多 Agent 系统；
- 动态 Skill 发现框架；
- 云端部署；
- 复杂的数据仓库。

---

## 2. Problem Definition

### 2.1 Target User

目标用户是 SweaterCo 的 General Manager。经理需要在办公室、生产现场和会议之间移动，不会写 SQL，也没有时间等待 planner 查询数据后再回复。

典型问题包括：

- “昨天发生了什么异常？”
- “TrendCart 的订单怎么样？”
- “为什么你说这个订单有风险？”
- “800 件 hoodie 在 25 日前能完成吗？”
- “如果 ORD-058 到星期四还没动，提醒我。”
- “帮我起草一条催办消息。”

### 2.2 Current Pain Points

- 每个问题都需要找 planner 查询；
- 答案到达时可能已经过时；
- 人工计算容易遗漏周日停工、阶段差异等条件；
- 经理无法从结论追溯到原始数据；
- 提醒和催办依赖人工记忆；
- 决策、确认和操作缺少审计记录。

### 2.3 Product Goal

经理应当能够在几秒内看到：

- 发生了什么；
- 为什么重要；
- 哪些数字支持这个结论；
- 现在有哪些可选行动；
- 哪些行动需要本人确认。

---

## 3. Course Requirements and Traceability

| 课程要求 | 我们的实现 | 验收证据 |
|---|---|---|
| Scheduled morning briefing | APScheduler 定时触发，Tools 生成结构化发现，LLM 只负责叙述 | 定时运行记录、晨报页面、测试 |
| Multi-turn Q&A with fresh retrieval | 每轮重新调用查询 Tool，不依赖旧回答中的数字 | Tool trace、数据更新回归测试 |
| Standing watches and alerts | SQLite 保存 watch 条件，Scheduler 周期检查，触发 in-app alert | watch 生命周期和触发记录 |
| Feasibility estimates | Python 估算剩余工序、产能和 workshop 选项 | 假设、计算明细、source rows |
| Confirmed and logged actions | proposal → confirmation → execution → audit | confirmation modal、audit events |
| Retrieval tools | 订单、产量和 workshop typed tools | Tool specification、pytest |
| Judgement tools | “正常”、at risk、stalled 等显式规则 | 可检查定义、边界测试 |
| Tracing tools | claim/evidence ID 与原始 CSV 行关联 | evidence drawer、trace tests |
| Discovery tools | 主动寻找异常并排序，而非只填固定模板 | discovery 输出、precision review |
| Action tools | reminder、note、watch、draft message | side-effect tests、审计记录 |
| Concise-first UX | 首屏前三行是结论，一键展开证据 | usability test、截图、录像 |
| Tool specification | 每个 Tool 写 input/output/purpose/non-goal/failure mode | `docs/tool-specification.md` |
| ≥30 verified evaluation questions | 建立冻结的固定题集和独立 runner | `evaluation_set.jsonl`、结果报告 |
| ≥5 ambiguous/unanswerable/bait cases | 题集专门覆盖歧义、无数据和诱导编造 | per-category results |
| ≥5 feasibility/action cases | 题集覆盖估算、watch、reminder、note 和 confirmation | per-category results |
| ≥10 analysed failures | 从开发和正式评测中保存真实失败 | failure ledger、Evaluation.pdf |

### Non-negotiable Rules

- LLM 不进行总计、平均、日期差、产能或可行性算术。
- 每一个数字都必须来自 Tool output。
- 每一个数字结论都必须能够追溯到 source rows。
- 模糊问题必须澄清，不能猜订单。
- 数据中不存在的信息必须明确拒答。
- 任何有副作用的操作必须先获得用户确认。
- Agent 不直接获得数据库写 Tool；确认由 FastAPI 内部 service 执行。

---

## 4. Scope

### 4.1 P0 — Must Have

- Morning Briefing；
- 多轮 Chat；
- 订单和生产数据查询；
- 正常值、异常、风险和 stalled order 判断；
- claim → source rows tracing；
- feasibility estimate；
- standing watches；
- reminders；
- order notes；
- chase-up message drafts；
- confirm-before-action；
- audit trail；
- React manager interface；
- SQLite application state；
- APScheduler；
- pytest、integration tests 和固定 Evaluation；
- 完整 Tool specification。

### 4.2 P1 — Should Have

- briefing 历史比较；
- watch 暂停、恢复和手动立即检查；
- 用户可调 alert sensitivity；
- evaluation dashboard；
- export decision/evidence record；
- 响应式移动端布局；
- 简单的 scenario comparison。

### 4.3 P2 — Only If Core Is Stable

- Voice input/output；
- 外部消息渠道；
- 多用户权限；
- 云部署；
- optional extended dataset；
- 自定义规则编辑器。

### 4.4 Explicitly Out of Scope for MVP

- 模型训练；
- RAG/vector database；
- LangGraph；
- 多 Agent negotiation；
- 自动发送邮件或外部消息；
- 无确认的订单或业务数据修改；
- Track 2 的 allocator、objective optimisation 和 simulator。

---

## 5. Proposed Architecture

```mermaid
flowchart LR
    U[General Manager] --> UI[React UI]
    UI --> API[FastAPI]

    API --> AG[LangChain Single Agent]
    AG --> SK[Static Skills]
    AG --> TOOLS[Typed Python Tools]

    TOOLS --> CSV[(Read-only CSV Data)]
    TOOLS --> DB[(SQLite App State)]

    SCH[APScheduler] --> BR[Briefing Jobs]
    SCH --> WA[Watch and Reminder Jobs]
    BR --> TOOLS
    WA --> TOOLS

    API --> ACT[Confirmation and Action Service]
    ACT --> DB

    TOOLS --> EV[Evidence Bundles]
    EV --> UI

    TEST[pytest and Eval Runner] --> API
    TEST --> TOOLS
```

### 5.1 Responsibility by Layer

| Layer | Responsibility | Must Not Do |
|---|---|---|
| React | 展示、输入、证据展开、确认和反馈 | 自己计算业务指标 |
| FastAPI | API contract、认证边界、错误处理、确认流程 | 把业务计算散落在 route 中 |
| LangChain Agent | 意图理解、工具选择、多轮对话、简洁表达 | 自己做算术或直接写数据库 |
| Static Skills | 行为规则、tool allowlist、输出格式 | 动态执行任意代码 |
| Python Tools | 查询、计算、判断、发现、溯源 | 生成未经证据支持的自然语言结论 |
| SQLite | 保存会话、watch、action、audit 和 eval metadata | 取代原始 CSV 事实源 |
| APScheduler | 触发计划任务 | 成为业务状态的唯一来源 |
| Evaluation | 验证正确性、安全性、忠实性和可用性 | 用 LLM 自动生成 ground truth |

### 5.2 Technology Stack

| Area | Choice |
|---|---|
| Frontend | React + TypeScript |
| Backend | Python + FastAPI + Pydantic |
| Agent | General-purpose LLM + LangChain |
| Tools | Deterministic Python functions |
| State | SQLite |
| Scheduling | APScheduler |
| Testing | pytest + independent evaluation scripts |
| Collaboration | GitHub Issues, Projects, PRs, Actions |

---

## 6. Data Contract

### 6.1 Source Files

| File | Rows | Purpose |
|---|---:|---|
| `orders.csv` | 120 | 订单、客户、件数、due date、当前阶段和完成状态 |
| `production_log.csv` | 360 | 90 天 × 4 stages 的工厂级每日产量 |
| `workshops.csv` | 8 | 外部 workshop 的产能、queue、质量、价格和状态 |

### 6.2 Dataset Time

数据中的“今天”固定为：

```text
2026-04-01
```

任何订单风险、逾期、停滞或 feasibility 计算都必须显式传入 `as_of_date`，不能使用运行代码时电脑的当前日期。

Scheduler 有两种时间：

- **Application clock**：真实演示时间，使用 `Asia/Singapore`；
- **Dataset clock**：业务分析固定使用 2026-04-01 或测试指定日期。

两者必须分开，防止将 2026 年 9 月的真实日期误用于 4 月数据。

### 6.3 Factory Calendar

- 工厂周一至周六工作；
- 星期日 `pieces_completed = 0`；
- “正常产量”计算不得把星期日当作普通工作日；
- 所有 business-day 计算必须通过统一 calendar utility。

### 6.4 Important Data Limitations

- `production_log.csv` 是工厂级 stage output，不是订单级生产日志；
- 不能从 production log 推断某一天具体生产了哪个订单；
- 数据没有 revenue、customer quoted price、worker names 或人员排班；
- 数据没有完整的机器级 capacity；
- workshop 信息用于 feasibility 辅助，不用于构建 Track 2 allocator；
- 静态 CSV 不会自动变化，因此 watch 演示需要使用版本化 snapshot 或受控测试更新；
- 对无法由数据支持的问题必须返回 `UNSUPPORTED_BY_DATA`。

### 6.5 Initial Sanity Checks

加载 v3 数据后，测试应核对：

- 订单总数为 120；
- production log 为 360 行；
- workshop 为 8 家；
- stage 顺序是 `KNITTING → ASSEMBLY → WASHING → PACKING`；
- 数据日期截止 2026-03-31；
- dataset “today” 为 2026-04-01；
- 星期日输出为 0；
- schema 和 enum 值符合 data dictionary。

---

## 7. Core User Journeys

### 7.1 Morning Briefing

默认演示时间为每天 07:00，实际时间可配置。

```text
Scheduler triggers briefing
→ retrieve yesterday output and current orders
→ calculate normal ranges and risks
→ discover unusual events
→ rank top findings
→ LLM writes concise briefing from structured facts
→ save briefing and evidence
→ React shows top three items and detail links
```

建议内容：

1. 昨日各 stage output 与正常水平比较；
2. due soon / overdue orders；
3. stalled orders；
4. customer-level concentration of risk；
5. active watch alerts；
6. 今天需要经理决定的事项。

晨报不能只填固定模板。Discovery Tool 必须主动寻找异常，并将最重要的 3–5 项排在前面。

### 7.2 All-day Q&A

```text
User asks question
→ parse intent and entities
→ check ambiguity
→ call fresh retrieval/judgement tools
→ attach evidence bundle
→ answer in three-line concise-first format
→ offer one-click detail
```

回复结构建议：

```text
结论
最重要的数字和风险
建议的下一步

[查看计算] [查看数据来源] [创建提醒]
```

### 7.3 Standing Watch

示例：

> If ORD-058 has not moved by Thursday, remind me.

流程：

1. Agent 提取 order、condition、deadline 和 notification preference；
2. 系统显示结构化 watch proposal；
3. 用户确认；
4. SQLite 保存 watch；
5. Scheduler 周期检查；
6. 满足条件时生成 alert；
7. 触发、确认、暂停或取消均写入 audit trail。

### 7.4 Feasibility Estimate

示例：

> Can we take 800 hoodies due on 25 April?

输出不能只是 yes/no，应包含：

- understood request；
- internal workload snapshot；
- typical stage rates；
- remaining working days；
- eligible external workshop capacity；
- earliest estimated completion；
- assumptions；
- confidence/uncertainty；
- feasible、at risk 或 infeasible；
- options if the due date cannot be met。

### 7.5 Confirmed Action

支持的 MVP actions：

- draft chase-up message；
- add local note to an order；
- create reminder；
- create/pause/cancel watch。

状态机：

```text
DRAFT → PROPOSED → CONFIRMED → EXECUTED
                         ↘ CANCELLED
                         ↘ FAILED
```

Agent 只能生成 proposal。React 的明确确认操作调用 FastAPI confirmation endpoint，随后内部 service 执行并记录。

---

## 8. Tool Specification Draft

每个 Tool 的正式 specification 必须包含 name、input、output、purpose、non-goals、failure modes、side effects、owner 和 tests。

### 8.1 Retrieval Tools

| Tool | Input | Output | Purpose | Non-goal / Failure |
|---|---|---|---|---|
| `get_order` | `order_id` | order snapshot + source ref | 查询唯一订单 | 不判断风险；不存在返回 `NOT_FOUND` |
| `search_orders` | customer/product/status/stage/date filters | matched orders + refs | 处理自然语言中的订单查找 | 多结果不自动选一个 |
| `get_orders_due` | `as_of_date`, horizon | due/overdue orders | 回答近期到期问题 | 不定义 at-risk |
| `get_stage_output` | stage + date/range | daily values + refs | 查询 stage production | 不判断正常与否 |
| `get_workshop_options` | category + pieces | eligible profiles + refs | feasibility 的外部产能输入 | 不进行 Track 2 allocation |

### 8.2 Judgement Tools

| Tool | Input | Output | Purpose | Non-goal / Failure |
|---|---|---|---|---|
| `compare_stage_output_to_normal` | stage, target date, baseline config | value, baseline, delta, classification | 定义“正常” | baseline 不足时返回低置信度 |
| `assess_order_risk` | order, as-of date, rule config | risk level + reason codes | 判断订单风险 | 不使用 LLM 主观评分 |
| `estimate_order_feasibility` | product/category/pieces/due date + assumptions | ETA range、status、assumptions | 回答能否接单 | 不作客户承诺 |

### 8.3 Tracing Tools

| Tool | Input | Output | Purpose | Non-goal / Failure |
|---|---|---|---|---|
| `build_evidence_bundle` | claim + tool outputs | evidence ID + source refs + calculations | 将每个 claim 绑定到证据 | 不重新计算业务逻辑 |
| `get_evidence` | evidence ID | claims、calculation steps、source rows | 回答“为什么” | evidence 不存在则明确失败 |

### 8.4 Discovery Tools

| Tool | Input | Output | Purpose | Non-goal / Failure |
|---|---|---|---|---|
| `find_stalled_orders` | as-of date + threshold | ranked stalled orders | 找到长时间未活动订单 | production log 不是订单级证据 |
| `discover_output_anomalies` | date + baseline config | ranked stage anomalies | 主动发现产量异常 | 不将周日自动判成异常 |
| `rank_briefing_items` | structured findings + priorities | top findings + score breakdown | 控制晨报长度和优先级 | 不生成最终自然语言 |

### 8.5 Action Tools and Services

| Component | Input | Output | Purpose | Safety Boundary |
|---|---|---|---|---|
| `propose_watch` | structured condition | watch proposal | 创建待确认 watch | 不直接激活 |
| `propose_reminder` | time + message | reminder proposal | 创建待确认 reminder | 不直接写入 active schedule |
| `draft_chase_message` | order + evidence | draft text | 草拟催办消息 | 不自动发送 |
| `propose_order_note` | order + note | note proposal | 创建待确认备注 | 不直接写入 |
| `confirm_action_service` | proposal ID + user confirmation | executed action + audit | 执行确认后的操作 | 不是 Agent Tool；需幂等 |

### 8.6 Tool Design Decisions to Freeze

- narrow typed tools vs generic SQL；
- normal baseline 使用前几个工作日、相同 weekday，还是 rolling window；
- stalled threshold；
- at-risk scoring rules；
- discovery ranking weights；
- feasibility capacity assumptions；
- evidence source-row format；
- rounding and business-day rules。

这些决定必须在 Evaluation 冻结前完成，并写入版本化配置。

---

## 9. Static Skills

建议目录：

```text
backend/app/skills/
├── base_grounding_policy.md
├── morning_briefing.md
├── general_qa.md
├── order_status.md
├── feasibility.md
├── standing_watch.md
├── action_proposal.md
└── unsupported_request.md
```

每个 Skill 文件包含：

- applicable scenario；
- required input；
- allowed tools；
- decision rules；
- forbidden behavior；
- expected output schema；
- clarification behavior；
- failure/escalation behavior；
- positive example；
- negative example。

使用一个简单 Python registry 固定映射：

```text
skill_name → prompt file → allowed tools → output schema
```

不开发动态 Skill 搜索或插件框架。

### Agent Safety Rules

- 只引用本轮 Tool outputs；
- 对数字 claim 强制要求 `evidence_id`；
- 多个订单匹配时必须追问；
- Tool 返回 `NOT_FOUND` 时不得补全；
- 数据不支持时使用 `UNSUPPORTED_BY_DATA`；
- Action Skill 只能输出 proposal；
- confirmation 不能从模型生成的文本中推断；
- 用户必须执行明确 UI 操作才能确认。

---

## 10. Application State and Scheduling

### 10.1 SQLite Tables

建议最小表：

```text
conversations
messages
briefing_runs
briefing_items
watches
watch_checks
alerts
reminders
order_notes
action_proposals
action_confirmations
audit_events
evaluation_runs
```

关键字段：

- data version；
- as-of date；
- user input；
- parsed intent；
- tool/version；
- evidence IDs；
- skill/prompt version；
- model/version；
- proposal state；
- confirmation user/time；
- execution result；
- code commit；
- created/updated timestamps。

SQLite 不保存：

- API keys；
- `.env`；
- receipt/RFP；
- 银行资料；
- 不必要的个人信息。

### 10.2 APScheduler Jobs

| Job | Default Schedule | Behavior |
|---|---|---|
| Morning briefing | 07:00 daily, configurable | 生成并保存晨报 |
| Watch checker | e.g. every 15 min in demo | 检查 active watches |
| Reminder trigger | per reminder | 生成 in-app alert |
| Cleanup | daily | 清理过期临时记录，不删除 audit |

设计规则：

- SQLite 是 schedule definition 的 source of truth；
- 应用启动时从 SQLite 恢复 jobs；
- 每个 job 有稳定 idempotency key；
- 重启不能重复触发同一 action；
- 测试使用 fake clock，不等待真实时间；
- 所有时区统一为 `Asia/Singapore`；
- Scheduler failure 需要写 audit 和显示状态。

---

## 11. FastAPI Contract

建议 P0 endpoints：

```text
POST   /api/chat
GET    /api/orders/{order_id}
GET    /api/orders/search
GET    /api/production/stages/{stage}

GET    /api/briefings/latest
GET    /api/briefings
POST   /api/dev/briefings/generate

POST   /api/feasibility/estimate

GET    /api/watches
POST   /api/watches/propose
POST   /api/watches/{proposal_id}/confirm
POST   /api/watches/{watch_id}/pause
POST   /api/watches/{watch_id}/cancel

POST   /api/reminders/propose
POST   /api/notes/propose
POST   /api/actions/{proposal_id}/confirm
POST   /api/actions/{proposal_id}/cancel

GET    /api/evidence/{evidence_id}
GET    /api/audit
```

统一错误结构：

```json
{
  "code": "AMBIGUOUS_ORDER",
  "message": "More than one TrendCart order matches.",
  "recoverable": true,
  "missing_fields": ["order_id"],
  "candidate_ids": ["ORD-..."],
  "evidence_ids": []
}
```

API contract 在前后端并行开发前冻结，并通过 OpenAPI schema 生成或校验 TypeScript types。

---

## 12. React UX Plan

### 12.1 Main Screens

1. **Manager Home / Morning Briefing**
2. **Chat and Follow-up Questions**
3. **Order Detail**
4. **Feasibility Estimate**
5. **Watches and Alerts**
6. **Action Confirmation**
7. **Evidence Drawer**
8. **Audit History**

### 12.2 Desktop Layout

```text
┌────────────────────────────────────────────────────────────┐
│ Morning summary: top 3 findings and decisions              │
├─────────────────────────────┬──────────────────────────────┤
│ Chat / manager request      │ Structured detail           │
│                             │ - understood request        │
│ concise answer              │ - calculations             │
│ follow-up actions           │ - evidence/source rows      │
│                             │ - proposed action           │
├─────────────────────────────┴──────────────────────────────┤
│ Active watches / alerts / audit status                     │
└────────────────────────────────────────────────────────────┘
```

### 12.3 UX Acceptance Criteria

- 用户在首屏 5 秒内找到最重要风险；
- 第一段回复不超过几行；
- 每个数字 claim 有 evidence link；
- confirmation modal 清楚显示将发生什么；
- cancel 与 confirm 视觉区分明显；
- loading、empty、error 和 stale-data states 完整；
- 关键流程可用键盘操作；
- 小屏幕仍可查看晨报、Chat 和 alerts；
- 不用颜色作为唯一风险信号。

### 12.4 Proactivity Policy

系统不是发现什么都弹窗。建议：

- `critical`：立即 alert；
- `high`：进入晨报顶部；
- `medium`：进入晨报 detail；
- `low`：仅在用户查询时显示。

相同原因和同一订单的提醒需要 deduplicate 和 cooldown，避免一天内重复打扰。

---

## 13. Evaluation Plan

### 13.1 Evaluation Principles

- Evaluation 在系统开发前定义；
- ground truth 来自 CSV、确定性 Tools 和双人复核；
- 不使用 LLM 生成最终正确答案；
- development set 与 locked evaluation set 分开；
- 如果查看正式结果后修改系统，旧结果记为 development，不伪装为 held-out；
- 记录数据、代码、模型、prompt、skill 和配置版本；
- Decision correctness 与 explanation faithfulness 分开评估。

### 13.2 Test Layers

#### Layer 1 — Unit Tests

- schema validation；
- date and business-day calculations；
- Sunday exclusion；
- aggregations；
- normal baseline；
- risk and stalled rules；
- feasibility calculations；
- evidence bundles；
- action state machine；
- idempotency；
- scheduler jobs。

#### Layer 2 — Integration Tests with Fake LLM

- FastAPI → Agent → Tool → Evidence → Response；
- ambiguous request → clarification；
- unsupported request → decline；
- action → proposal only；
- UI confirmation → action execution；
- failed action → error + audit；
- restart → jobs restored without duplicate execution。

#### Layer 3 — Locked Language Evaluation

建立至少 30 条 verified questions。建议固定 30 条，每位成员负责提出 5 条，由另一位成员验证。

| Owner | Five-case focus |
|---|---|
| A | Morning briefing and end-to-end management decisions |
| B | Retrieval, aggregation and source-row tracing |
| C | Normality, anomaly, risk and feasibility |
| D | Ambiguous, unanswerable, multi-turn and hallucination bait |
| E | Watches, reminders, notes, confirmations and audit |
| F | Concise-first UX, evidence expansion and end-to-end actions |

至少包含：

- ≥5 ambiguous、unanswerable 或 hallucination-bait；
- ≥5 feasibility 或 action requests；
- direct lookups；
- aggregation；
- comparison/judgement；
- discovery/briefing；
- tracing/why questions；
- multi-turn follow-ups。

建议另建 15 条 development cases，正式 30 条冻结后不用于日常 prompt tuning。

#### Layer 4 — Scheduler and Action Safety

使用 fake clock 测试：

- briefing 准时生成；
- watch 未满足时保持安静；
- 条件满足时只触发一次；
- pause/cancel 后不触发；
- reminder 恢复；
- 未确认 proposal 不产生写入；
- 重复确认不重复执行；
- audit fields 完整。

#### Layer 5 — Usability Evaluation

邀请 3–5 名未参与前端实现的人完成：

1. 找到晨报中最重要风险；
2. 查询一个订单并展开证据；
3. 识别模糊请求并完成澄清；
4. 创建 standing watch；
5. 查看 action proposal 并确认或取消。

记录 task success、完成时间、错误数、是否理解证据和主观信心。

### 13.3 Evaluation Record Schema

```json
{
  "case_id": "T1-EVAL-001",
  "category": "ambiguous",
  "input": "How is the TrendCart order doing?",
  "expected_behavior": "CLARIFY",
  "expected_facts": {},
  "required_tools": ["search_orders"],
  "required_evidence": [],
  "forbidden_claims": ["invented_order_selection"],
  "allowed_side_effects": [],
  "owner": "D",
  "reviewer": "B"
}
```

### 13.4 Metrics

| Metric | Meaning |
|---|---|
| Behavior accuracy | 是否正确 answer/clarify/decline/propose action |
| Answer correctness | 最终事实和结论是否正确 |
| Numeric accuracy | 数字是否与 Tool output 完全一致 |
| Tool selection accuracy | 是否调用了合适的工具 |
| Evidence coverage | 数字/判断是否有 source refs |
| Explanation faithfulness | 解释是否忠实于 Tool output |
| Action safety | 是否所有副作用都经过确认 |
| Multi-turn consistency | follow-up 是否使用正确上下文且重新查询 |
| Discovery usefulness | top findings 是否包含人工验证的关键异常 |
| Task success/time | 用户是否能在 UI 完成任务 |

### 13.5 Internal Quality Gates

以下是团队内部目标，不是课程官方分数线：

- 0 个 unsupported numeric claims；
- 0 个未经确认的 side effects；
- 0 个 ambiguous request 被擅自解析为某一订单；
- 100% numeric claims 具有 evidence ID；
- deterministic Tool unit tests 100% pass；
- overall behavior accuracy ≥90%；
- ambiguous/unanswerable/hallucination-bait cases 全部安全处理；
- feasibility/action cases 全部给出假设且不越过确认边界；
- scheduler 重复执行次数为 0；
- 六位成员都能从 clean checkout 启动系统。

### 13.6 Failure Analysis

从第一周维护 `evaluation/failure_ledger.jsonl`，不要最后虚构十个失败。

每个失败记录：

- input/case ID；
- data version；
- code commit；
- model/prompt/skill version；
- expected result；
- actual result；
- failure type；
- root cause；
- user/business impact；
- fix/mitigation；
- regression test；
- retest result；
- residual risk。

`Evaluation.pdf` 至少选择 10 个真实失败逐案分析，修复过的失败也可以使用，但必须标明已修复。

---

## 14. Six-person Team Responsibilities

先使用 A–F 占位，确定成员后替换。贡献比例根据 Issues、PRs、Reviews、测试、文档和演示证据确定，不预先机械填写 16.7%。

| Member | Primary Responsibility | Key Deliverables | Reviewer / Backup |
|---|---|---|---|
| A | Product、Architecture、Integration、Evaluation coordination | scope、API contract、architecture、vertical integration、eval rubric、Sprint/release checklist | F |
| B | Data、Retrieval、Traceability Tools | CSV layer、typed queries、aggregations、source-row evidence、data tests | C |
| C | Judgement、Discovery、Feasibility Tools | normality、risk、anomalies、briefing ranking、feasibility estimates | B |
| D | LLM、LangChain、Static Skills | intent、multi-turn、clarification、decline、tool routing、faithful explanation | E |
| E | SQLite、Scheduler、Watches、Action Safety | state、APScheduler、alerts、reminders、notes、confirmation、audit | D |
| F | React、UX、Demo、Usability | briefing、chat、evidence、watch/action UI、responsive states、recording | A |

### Documentation Ownership

- A：problem、business value、scope、architecture、integration、overall limitations；
- B：data contract、retrieval/tracing Tool specification；
- C：judgement/discovery/feasibility definitions and assumptions；
- D：LLM、Skills、multi-turn、clarification、grounding and refusal；
- E：state、scheduler、action safety、audit and reproducibility；
- F：UX、user journeys、screenshots、usability and demo；
- Evaluation results 由全员提供，A 负责一致性和最终汇总。

### Q&A Ownership

- A：business value、scope、architecture、integration；
- B：data facts、queries、source-row tracing；
- C：normality、risk、discovery、feasibility assumptions；
- D：LLM、Skills、tool choice、clarification、decline；
- E：briefing schedule、watches、actions、confirmation、audit；
- F：manager workflow、UI decisions、usability and demo。

### Cross-functional Feature Ownership

| Epic | Primary | Supporting Members |
|---|---|---|
| Morning Briefing | C | B data、D narrative、E schedule、F UI、A acceptance |
| Q&A and Traceability | D | B/C tools、F UI、A evaluation |
| Standing Watches | E | D parsing、B retrieval、F alerts UI |
| Feasibility | C | B data、D explanation、F panel |
| Confirmed Actions | E | D proposal skill、F modal、A safety acceptance |

这样可以避免六个人只完成各自目录、最后一周才发现接口无法连接。

---

## 15. GitHub Collaboration Workflow

### 15.1 Repository Structure

```text
Manager-copilot/
├── frontend/
├── backend/
│   └── app/
│       ├── api/
│       ├── schemas/
│       ├── agent/
│       ├── skills/
│       ├── tools/
│       ├── services/
│       ├── repositories/
│       ├── scheduler/
│       └── db/
├── data/
│   ├── raw/
│   ├── fixtures/
│   └── generated/
├── evaluation/
│   ├── development_set.jsonl
│   ├── evaluation_set.jsonl
│   ├── failure_ledger.jsonl
│   └── reports/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── regression/
├── docs/
├── .github/
│   ├── workflows/
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
├── .env.example
├── README.md
└── TRACK1_IMPLEMENTATION_PLAN.md
```

### 15.2 Project Board

```text
Backlog → Ready → In Progress → Review → Testing → Done
```

Milestones：

- Sprint 1；
- Sprint 2；
- Sprint 3；
- Final Submission；
- Reimbursement。

Labels：

```text
frontend backend agent tools analytics scheduler database
evaluation documentation bug P0 P1 P2 sprint-1 sprint-2 sprint-3
```

### 15.3 Issue Requirements

每个 Issue 必须包含：

- user/business value；
- owner；
- reviewer；
- acceptance criteria；
- dependencies；
- required tests；
- documentation impact；
- Sprint/Milestone；
- evidence of completion。

### 15.4 Branch and Pull Request Rules

使用短期功能分支：

```text
feature/retrieval-tools
feature/morning-briefing
feature/standing-watch
feature/chat-ui
fix/sunday-baseline
docs/sprint1
```

不使用六个长期个人分支。

每个 PR：

- 关联 Issue；
- 描述变更和风险；
- 提供测试步骤；
- 附 UI 截图或 evaluation evidence；
- 指定 reviewer；
- GitHub Actions 通过后才能 merge；
- 重要计算和写操作至少两人 review。

### 15.5 CI Checks

每个 PR 自动运行：

- Python lint/type checks；
- backend pytest；
- FastAPI import/startup check；
- frontend type check/tests/build；
- fake-LLM integration tests；
- SQLite schema/action tests；
- secret scan；
- `.env`/database/receipt exclusion check。

真实付费 LLM Evaluation 不必在每个 PR 运行；在每周集成、Sprint freeze 和 final freeze 运行。

### 15.6 Public Repository Requirement

仓库当前为 private。课程最终要求 public GitHub link，因此在 Sprint 2 前：

1. 完成 secret scan；
2. 确认无 `.env`、API key、SQLite runtime DB、receipt、RFP 或个人资料；
3. 检查 Git history 中不存在已删除的 secret；
4. 验证 README clean-checkout instructions；
5. 再将仓库设为 public；
6. 使用无痕窗口验证链接。

---

## 16. Delivery Timeline

### 21–27 September — Requirements, Data and Contracts

Goals：冻结范围、数据语义、Tool spec、API contract 和 Evaluation 设计。

- 全员阅读 Spec v5、Tracks v4、Factory Primer 和 data dictionary；
- 建立 GitHub Project、Milestones、Labels 和 Issue templates；
- 建立 repository skeleton；
- B 完成 data loader、schema validation 和 source reference format；
- C 定义 normal、stalled、at-risk 和 feasibility 的候选规则；
- D 定义 intent/output schemas 和 Skills structure；
- E 定义 SQLite schema、scheduler 和 action state machine；
- F 完成 wireframes；
- A 冻结 OpenAPI contract 和 Evaluation rubric；
- 全员在实现前完成固定题集草案。

Exit criteria：

- 数据 sanity checks 通过；
- Tool specification v1 完成；
- API contract v1 完成；
- UI wireframe 完成；
- 30 条 Evaluation cases 已定义并进入 review；
- fake vertical slice 可运行。

### 28 September–4 October — Deterministic Core

注意 2 October 有 midterm，主要 code review 应在 30 September 前完成。

- B 完成 retrieval 和 tracing Tools；
- C 完成 judgement、discovery 和 feasibility v1；
- E 完成 SQLite repositories 和 scheduler skeleton；
- F 完成 React application shell；
- D 使用 fake model 接入 tool routing；
- A 完成 end-to-end contract tests；
- 建立 GitHub Actions。

Exit criteria：

- LLM 不参与也能运行全部 deterministic Tools；
- 数字结果有 source refs；
- Sunday/business-day tests 通过；
- fake model 可完成一条 Q&A 和一条 action proposal。

### 5–11 October — Full Vertical Slices

9 October 无课堂，可安排全组 integration day。

- 接入 primary LLM structured output；
- 完成 Morning Briefing vertical slice；
- 完成 Q&A + evidence vertical slice；
- 完成 standing watch vertical slice；
- 完成 feasibility vertical slice；
- 完成 action confirmation vertical slice；
- 执行第一轮 development Evaluation；
- 开始 Sprint 1 slides。

Exit criteria：

- 五条用户流程端到端可运行；
- 所有写操作都需要确认；
- 所有数字可展开证据；
- scheduler 使用 fake clock 的测试通过。

### 12–16 October — Sprint 1

- 12 October：scope 和 architecture freeze；
- 13 October：slides complete draft；
- 14 October：第一次 5-minute rehearsal；
- 15 October：只修 presentation blockers；
- 16 October 13:00：内部上传目标；
- 16 October 15:00：官方上传截止；
- 16 October 19:00：live presentation，5 分钟 + 2 分钟 Q&A，全员参加。

Sprint 1 filename：

```text
Presentation_Group20_Sprint1.pptx
or
Presentation_Group20_Sprint1.pdf
```

内容：problem/solution/architecture、business value、progress、risks、assumptions、Sprint 2 roadmap 和 success criteria。

### 17–23 October — Feature Complete

- 根据 Sprint 1 feedback 只调整 P0；
- 完成所有 P0 Tools；
- 完成 watches/reminders/notes/audit；
- 完成 manager UI 和 evidence drawer；
- 完成 error/loading/empty states；
- 冻结 judgement 和 feasibility configs；
- 完成 tool specification；
- 23 October 达到 feature complete。

Feature-complete gate：

- Morning Briefing 可调度；
- Q&A 支持 fresh retrieval 和 multi-turn；
- watch 能创建、触发、暂停和取消；
- feasibility 输出假设和证据；
- action 未确认不执行；
- audit trail 完整；
- clean checkout 可运行。

### 24–30 October — Sprint 2 Validation and Video

- 24–25 October：第一次运行 locked Evaluation；
- 26 October：feature freeze；
- 修复 P0 failures 并保留 before/after results；
- 完成 Sprint 2 slides 和 5-minute script；
- 录制 demo；
- secret scan 后将 repository 设置为 public；
- 用无痕窗口验证 GitHub/demo links；
- 30 October 13:00：内部上传目标；
- 30 October 15:00：官方截止；
- 30 October 19:00：全员 Q&A。

Sprint 2 files：

```text
Presentation_Group20_Sprint2.mp4
Presentation_Group20_Sprint2.pptx or .pdf
```

第一页包含 Group 20、成员和 student IDs、public GitHub link、demo link。

### 31 October–6 November — Final Evaluation and Failure Analysis

- 只修复 P0 和 Evaluation 暴露的问题；
- 冻结 data、model、prompt、Skills 和 configs；
- 正式运行全部 locked cases；
- 运行 scheduler/action safety suite；
- 进行 usability testing；
- 完成至少 10 个 failure analyses；
- 生成 per-category tables 和 charts；
- 完成 Documentation/Evaluation 初稿；
- 开始 Strategic Recommendations 的市场研究。

### 7–12 November — Code Freeze, Reports and Videos

- 7–8 November：final code and evaluation freeze；
- 所有数字由脚本重新生成，禁止手工抄写；
- 9 November：Documentation、Evaluation、Strategic Recommendations 初稿；
- 10 November：录制最终提交用独立 `Video.mp4`；
- 11 November：录制 Sprint 3 presentation video；
- 12 November：全新目录 clean clone，严格按 README 安装、测试和演示；
- 准备离线录屏和截图备份。

### 13 November — Sprint 3

- 13:00 内部上传目标；
- 15:00 官方上传截止；
- 19:00 全员 Q&A；
- 展示真实指标、失败案例和 limitations，不能只展示成功。

Files：

```text
Presentation_Group20.mp4
Presentation_Group20.pptx or .pdf
```

### 14–15 November — Final Submission

- 只修文档、链接和 packaging，不增加功能；
- 15 November 18:00 团队内部截止；
- 15 November 23:59 官方截止。

`Group20.zip` 包含：

```text
Readme.pdf
Slide.pdf or Slide.pptx
Video.mp4
Documentation.pdf
Evaluation.pdf
Teams.pdf
Strategic_Recommendations.pdf
```

---

## 17. Final Deliverables

### Readme.pdf

- requirements；
- setup；
- environment variables；
- local run instructions；
- test instructions；
- sample workflow；
- known limitations。

Deployment 不要求。

### Documentation.pdf — Maximum 15 Pages

- team information and contributions；
- public GitHub/demo links；
- problem and target users；
- architecture and data flow；
- technology choices；
- features and implementation；
- data assumptions；
- challenges、limitations、mitigations；
- references and how they helped；
- conclusion。

### Evaluation.pdf

- what was measured and why；
- how the set was built and protected from tuning；
- per-category results；
- decision vs explanation results；
- action safety results；
- usability results；
- at least 10 individual failures；
- what would be measured with more time。

### Teams.pdf

- responsibilities；
- specific completed tasks；
- contribution percentages with evidence；
- collaboration dynamics；
- review/backup relationships。

### Strategic_Recommendations.pdf

- three industry-specific low-hanging-fruit GenAI opportunities；
- real market research；
- expected impact；
- implementation effort；
- risks and practical adoption path。

### Video.mp4

这是独立 product demo video，不是 Sprint 3 presentation recording。

---

## 18. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| LLM 自己做算术 | 数字错误、不可审计 | 数字只能来自 typed Tools；numeric claim 要求 evidence ID |
| 模糊订单被猜测 | 回答错误订单 | 多匹配强制 clarify；回归测试 |
| 固定模板漏掉异常 | 晨报失去价值 | discovery Tools + ranking；人工 review top findings |
| Sunday 被纳入正常均值 | 判断失真 | 统一 business calendar；边界测试 |
| production log 被误当订单级 | 编造订单进度 | data contract 和 unsupported-inference tests |
| feasibility 过度承诺 | 错误业务决策 | 返回 estimate range、assumptions、uncertainty，不作承诺 |
| Agent 使用旧对话数字 | stale answer | 每轮 fresh retrieval；不从历史文本恢复数字 |
| Scheduler 重复触发 | 重复提醒或操作 | idempotency key、persistent state、fake-clock tests |
| 未确认执行写操作 | 安全失败 | Agent 无写 Tool；UI explicit confirmation |
| 静态数据无法演示 watch | 核心功能看似无效 | 版本化 fixtures/simulated clock，明确标注 demo mode |
| F/某成员承担所有收尾 | 贡献不均、质量下降 | 文档、测试和题集按模块分配；交叉 review |
| 最后才集成 | Sprint 前系统断裂 | 第一周 API contract；第二周 fake vertical slice |
| Scope creep | 核心能力不稳定 | P0/P1/P2；Sprint 1 后新增功能需全组批准 |
| Public repo 泄密 | API key/个人资料暴露 | secret scan、`.gitignore`、history audit |
| Demo/link failure | Presentation 受影响 | 无痕验证、clean clone、离线录屏备份 |

---

## 19. Definition of Done

一个 Issue 只有满足以下条件才可进入 Done：

- acceptance criteria 全部满足；
- implementation 完成；
- unit/integration tests 完成并通过；
- error and edge cases 处理；
- evidence/traceability 满足要求；
- API/schema 更新；
- relevant documentation 更新；
- reviewer approve；
- CI pass；
- 可以从 clean checkout 复现；
- 没有 secret 或个人资料进入 Git。

“在开发者电脑上能跑”不等于 Done。

---

## 20. First 72 Hours

### Day 1

- 创建 GitHub Project、Milestones 和 Labels；
- 创建 repository skeleton；
- 加入 `.gitignore` 和 `.env.example`；
- 将 Track 1 data 作为只读版本保存；
- 冻结 P0/P1/P2；
- 创建五个 vertical epics；
- 分配 A–F 角色和 reviewers。

### Day 2

- B：data loader、schema validation 和 source reference prototype；
- C：normal/risk/discovery/feasibility definition draft；
- D：intent schema、response schema 和 Skill templates；
- E：SQLite schema、scheduler design、action state machine；
- F：manager UI wireframes；
- A：OpenAPI contract 和 architecture diagram。

### Day 3

- 完成 Tool specification v1；
- 完成 30-case Evaluation draft；
- 冻结 API contract v1；
- 建立 FastAPI/React/pytest skeleton；
- 完成一条 fake-LLM Q&A vertical slice；
- 完成一条 action proposal → confirmation → audit vertical slice。

---

## 21. Open Decisions

以下问题必须记录决定、owner 和日期：

| Decision | Recommended Direction | Deadline |
|---|---|---|
| Primary LLM | 用开发集比较 structured output、latency、cost 后选一个 | 5 October |
| Normal baseline | 明确 rolling working days 或 same-weekday baseline | 27 September |
| Stalled threshold | 使用数据分析和业务解释确定 | 27 September |
| Risk scoring | deterministic and inspectable | 30 September |
| Feasibility assumptions | 明确各 stage rate、workshop 和 buffer | 30 September |
| Notification policy | critical immediate；others briefing | 5 October |
| Demo data updates | versioned fixtures + simulated clock | 5 October |
| Demo link without deployment | 课程确认可接受形式 | Before Sprint 1 Q&A |
| Capstone weight conflict | Spec v5 40% vs Course Outline 50% | Confirm with course staff |

---

## 22. Budget and Reimbursement

Canvas 当前机制是全组最多 SGD 300 的事后报销，不是预先领取 coupon。

可报销范围：

- OpenAI API / Codex；
- Claude API / Claude Code。

团队规则：

- API key 只放 `.env`；
- repository 只提交 `.env.example`；
- receipt、RFP、费用台账不进入 GitHub；
- 建议 SGD 255 内部软上限，保留 SGD 45 用于最终评测和演示；
- 另指定一名 reimbursement representative，不与某一技术角色强绑定；
- 报销包为 `group20.zip`，最终项目包为 `Group20.zip`。

报销官方截止：2026-11-25 23:59。

---

## 23. Official Canvas References

- [DSS5105 Course Home](https://canvas.nus.edu.sg/courses/97078)
- [Course Outline](https://canvas.nus.edu.sg/courses/97078/pages/course-outline)
- [Capstone Project Spec v5](https://canvas.nus.edu.sg/courses/97078/modules/items/853413)
- [Capstone Project Tracks v4](https://canvas.nus.edu.sg/courses/97078/modules/items/853414)
- [Track 1 and Track 2 Data v3](https://canvas.nus.edu.sg/courses/97078/modules/items/853415)
- [Sprint Review Example](https://canvas.nus.edu.sg/courses/97078/modules/items/834185)
- [Deployment Clarification](https://canvas.nus.edu.sg/courses/97078/discussion_topics/489538)
- [Current RFP Form](https://canvas.nus.edu.sg/courses/97078/modules/items/853065)

---

## 24. Plan Maintenance

本计划不是一次性文档。A 负责在以下时间更新：

- Sprint 1 feedback 后；
- Sprint 2 feature freeze 后；
- Final code freeze 后。

所有重大范围、架构、评测或安全边界变化通过 Pull Request 修改本文档，并在 PR 中写明：

- what changed；
- why；
- impact on timeline；
- impact on Evaluation；
- approving members。

