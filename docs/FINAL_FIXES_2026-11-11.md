# 最终版本候选：本地可靠性修复记录

更新日期：2026-11-11。适用项目：Group 20，Track 1 Manager Co-Pilot。

本次修改基于分支 `sprint3-ui-and-evaluation` 的提交
`7d4f16fcd406b2eb8aa3583e69894bd7fe34a352`。修改已保存在本地工作目录，尚未 commit、push 或合并到 main。
这份记录用于团队同步以及后续 Readme.pdf、Documentation.pdf、Evaluation.pdf 的事实核对。

## 1. 本次修复的范围

保留 React + FastAPI + LangChain + Python Tools + 静态 Skills + SQLite + APScheduler 的架构。
本轮解决上一轮审查发现的状态一致性、重试、计算口径、证据展示和运行脚本问题。
没有训练或微调模型，没有读取 API key，没有调用收费模型 API。

| 问题 | 修改后的行为 | 主要位置 |
|---|---|---|
| 一轮聊天期间切换数据版本，工具可能读到不同日期的数据 | 每轮固定版本和数据日期；LangChain 工具线程使用同一上下文；新一轮才读取最新版本 | `backend/rules.py`、`service.py` |
| 历史回答使用当前 CSV/快照重新构建证据 | 保存当时的证据行、日期、版本和答案检查；重启或切换版本后仍读取已保存证据 | `backend/service.py`、`evidence_refs.py` |
| 旧会话没有记录历史版本 | 标记 `legacy_unknown`，保留原工具返回，明确提示版本未知；不补入当前 CSV 行冒充旧证据 | `backend/service.py` |
| 创建/确认请求已成功但响应丢失，再点按钮可能重复创建 | 同一弹窗、同一输入保留 `request_id` 和 `proposal_id`；后端唯一约束去重；同 ID 不同内容返回 409 | `backend/actions.py`、`api.py`；`frontend/src/proposalRetry.ts` |
| 模型生成失败或会话并发冲突后留下可确认提案 | 聊天提案先为不可确认的 `DRAFT`；与会话保存同一事务激活；失败只使本轮草稿失效，保留审计 | `backend/actions.py`、`action_tools.py`、`storage.py`、`service.py` |
| 缺少产量日志被当作产量 0，产生虚假的 −100% | 返回 `partial` / `insufficient_data`；不完整期间的总量和变化为 `null`，仅另存已记录部分的总量 | `backend/period_output.py`、`skills/general_qa.md` |
| 全部下降时仍显示“最大增长”，或部分阶段缺日志却作全局排名 | 增长只从正数、下降只从负数中选择；任一请求阶段不完整时不提供全局排名 | `backend/period_output.py` |
| 运输时间和返工日期的文字超出计算依据 | 运输为每批一次固定开销；返工到达日期是指定假设下的条件场景，不是保证的最晚日期 | `backend/outsourcing_risk.py`、`production_estimates.py` |
| 新规划仍默认从 4 月 1 日开始 | 新规划默认当前数据日；明确区分 `scenario_start_date` 与参考输入 `data_as_of`；历史规划修订保留原起始日，除非用户明确更改 | `backend/production_estimates.py`、`production_optimizer.py`、`tool_schemas.py`、`skills/feasibility.md` |
| Answer check 的界面措辞像完整事实验证 | 明确它只是部分 ID、日期和数字的出现检查，来源可包含用户请求；不保证实体对应、含义或小整数正确 | `frontend/src/components/Chat.tsx`及 README |
| Evidence 只展示工具参数，没有实际返回值 | 展示版本化来源行、数据日期和可展开的结构化结果，包括数值、假设与警告 | `frontend/src/components/EvidenceDrawer.tsx`、`types.ts` |
| 启动脚本删除源文件，依赖和评测失败处理不充分 | 不再删除源文件；新增 `--setup`、`--demo`；失败不标记安装完成；评测脚本失败停止，默认离线 | `start_app.bat`、`run_evaluation.bat` |
| 前端构建依赖审计发现问题 | Vite 升至 `6.4.6`，锁文件同步；本次 npm audit 报告 0 个已知漏洞 | `frontend/package.json`、`package-lock.json` |

此外，离线 Demo 的晨报、风险查询和 watch 默认日期也跟随选中的数据快照，避免演示路径与真实后端日期规则不一致。

## 2. 必须在文档中解释清楚的行为

### 数据时间与证据

- 业务事实使用选定的数据日期；提醒使用真实日历时间，两者仍然分开。
- 例如在 v0 查询 ORD-107，然后切换到 v1，旧回答保留 v0 的 `IN_PROGRESS` 证据；新回答读取 v1 的状态。
- 同一 CSV 行在不同版本中的引用有不同的 `id` / `row_key`，避免互相覆盖。
- 原始课程负载在可行性计算中明确引用 v0；场景开始日期可以是当前选中的较晚日期。
- 老会话未保存的证据版本不能凭空恢复。保留未知提示是正确行为，不应改写历史记录。

### 动作重试与事务

1. 用户在 UI 点击确认后，前端为该次意图生成 request ID。
2. 若创建响应丢失，再次提交同一意图会取回原提案。
3. 若确认响应丢失，再次确认原提案会返回已保存的结果，不增加第二条提醒或 watch。
4. 输入修改后属于新意图，必须使用新 request ID。
5. 聊天创建的提案在完整回答保存成功之前不可确认；失败不会执行动作。

已加入对旧 SQLite 数据库的增量迁移，不需要删除现有会话、提醒或审计记录。
新增审计事件包括提案就绪、提案失效和聊天轮次失败。

重试身份目前保存在**当前弹窗**中。关闭弹窗后重新打开、刷新页面或改动内容会产生新意图。
如果先前请求的结果不确定，应先检查 Actions；界面错误提示已说明这一点。

### 业务计算边界

- `recorded_total_pieces` 是已记录部分之和，不能当作完整期间总量。
- 完整记录中的真实 0 产量仍是 0，并可合法形成 −100% 变化；“无记录”与“记录为 0”不同。
- 缺数据时模型应解释缺失日期/阶段，不能自行填 0 或重新推导被工具置空的变化和排名。
- Workshop 的 `defect_rate` 仍按课程数据字典解释为批次缺陷概率，没有改成每件产品的缺陷率。
- `rework_scenario_arrival` 替代 `latest_arrival_if_reworked`。下游代码若曾读取旧字段，需要同步更新。
- 产能、队列、返工时间及独立性等假设必须随场景解释；结果不是生产保证或承诺交期。

### 答案检查与实际可信度

Answer check 没有被升级成语义验证器。它能找出某些未出现于工具结果/请求中的值，但仍可能漏掉：

- 把正确数值分配给错误订单；
- 用已有数值得出错误结论；
- 小整数相关错误；
- 其他超出规则识别能力的表达。

只有“没有调用工具且包含未核实值”的回答会自动重试一次。
已经调用工具的回答不因这条规则再次运行。最终模型评测仍需要独立标签和人工忠实性审查。

## 3. 已完成的验证

| 验证 | 本轮结果 | 能证明什么 |
|---|---|---|
| 完整后端 pytest | **294 passed**（修改前基线 260） | 现有行为及新增边界回归通过 |
| 前端重试测试 | **3 passed** | 创建响应丢失、确认响应丢失、编辑新意图的处理 |
| 前端 TypeScript + 生产构建 | **通过** | 类型检查和 Vite 构建可完成 |
| npm audit | **0 vulnerabilities** | 本次审计数据库未报告当前锁文件的已知漏洞；不是全面安全认证 |
| 固定题集结构检查 | 30 evaluation + 17 development；**0 verified** | 文件结构可读；标签仍需人工确认 |
| 30 题离线 fake runner | **30/30** | 评测管道、报告和规则桩可以运行；不是 LLM 成绩 |
| 真实本地 HTTP 冒烟检查 | **10 项通过** | 前后端代理、查询、聊天工具/证据、确认、审计及历史保存连通 |
| 实际网页检查 | **通过** | 可展开结构化工具结果；提醒显示保存成功；切换快照后旧回答仍显示旧证据 |
| diff 空白检查 | **通过**（允许仓库已有 CRLF） | 无新增实质空白错误 |

新增后端回归覆盖快照切换时的真实 LangChain 工具线程、历史重启、混合版本引用、旧库迁移、
并发创建去重、跨日重试、事务回滚、失败提案隔离、缺日志与真实 0、排名和规划日期等。

本地验证日志放在仓库外的 `Capstone Project/Final_Submission_Audit_2026-11-11/`：

- `fixed_pytest.log`
- `fixed_frontend_tests.log`
- `fixed_build.log`
- `fixed_http_smoke/smoke_results.json`
- `fixed_offline_evaluation/`

仓库中的历史真实模型报告、题目标签与 failure ledger 保持原样。
日志位置是本机工作目录，不是 GitHub clean checkout 的运行依赖。

## 4. 重新运行的方法

环境：Python 3.12、Node.js 22.6+（建议使用 Node 22 最新补丁版）。

从仓库根目录，macOS / Linux：

```bash
backend/.venv/bin/python -m pytest -q backend/tests
backend/.venv/bin/python evaluation/run_evaluation.py --check
backend/.venv/bin/python evaluation/run_evaluation.py --fake --no-ledger --out /tmp/copilot-offline-check
cd frontend
npm ci
npm test
npm run build
```

Windows 首次或依赖更新后：

```bat
start_app.bat --setup --demo
run_evaluation.bat
```

`start_app.bat --demo` 使用离线关键词模型。正常真实模型启动去掉 `--demo`，并按 README 配置服务器端环境变量。
`run_evaluation.bat --real` 才会显式进行真实模型调用并产生 API 用量。
这些 Windows 脚本已检查逻辑，但本机为 macOS，尚未实际执行 Windows 启动过程。

新增 `.github/workflows/checks.yml`，准备在 Linux 和 Windows 上运行后端测试、离线评测管道、前端构建及重试测试。
工作流尚未推送，因此不能声称 GitHub Actions 已通过，也不等于验证了 Windows 图形启动脚本。

## 5. 冻结最终版本前仍需完成

1. 团队 review 本地差异并确认业务假设，提交一个可追踪的最终候选 commit。
2. 用最终候选代码和 Skills 重跑真实模型评测；本次未进行。历史 29/30 与 15/17 不能充当这次修复后的结果。
3. 审核现有标签。30 题已经参与迭代，不能在事后改称独立 held-out；如报告独立泛化能力，应另建未用于调试的题集。
4. 在 Windows 实机验证启动脚本；从最终公开仓库做 clean checkout，按 README 从零运行。
5. 用最终版本重录必要的 Demo 片段，并让 Readme、Documentation、Evaluation、Slides 使用一致的版本和指标。
6. 补全至少 10 个逐一分析的失败案例、团队贡献记录和 Strategic Recommendations；这些是后续交付工作，不是本次代码测试已经完成的内容。

目前可把本目录作为本地最终候选继续联调和写文档；不要把“本地工程测试通过”写成“最终真实模型评测完成”。

## 6. 第二轮修复（2026-11-12）

依据代码检查清单（仓库外 `Final_Submission_Audit_2026-11-11/CODE_REVIEW_2026-11-11.md`）的第一档问题和几项仓库配置。仍未 commit；没有调用真实模型。

| 问题 | 修改后的行为 | 位置 |
|---|---|---|
| 加载快照后产量日志缺失，晨报 Production 显示 “0 · Nothing to flag”；同一缺口记两遍；页脚露出字段名 `data_gaps` | 检查结果新增 `not_checked`；卡片显示 “—” 和 “4 not checked”，展开后写明原因；每个工序每段只记一个缺口（8 项，原为 12 项）；警告改为写明哪些工序缺记录 | `backend/briefing.py`；`frontend/src/components/BriefingSummary.tsx`、`types.ts` |
| 回答检查把 decreased、marked、declined、separate、may 当成月份 | 只认完整月份名和标准缩写；小写 “may” 视为动词 | `backend/answer_check.py` |
| 中文回答里的数字、订单号、日期检查不到；来源行号能为任意数字作证；2000–2099 的整数被当成年份跳过 | 边界改为只看 ASCII 字符；行号只在回答写成 “row 88 / line 88 / 第88行” 时有效；年份只跳过 2020–2039 | `backend/answer_check.py` |
| “前 N 个需关注订单”同分时按 CSV 顺序 | 同分时到期早的在前（今天到期的 ORD-029 排在 4 月 4 日到期的 ORD-103 之前） | `backend/discovery.py` |
| 电脑 7:00 休眠超过一小时，当天晨报被跳过 | 晨报任务不设补跑时限；当日运行键防止重复 | `backend/scheduler.py` |
| “overdue by 1 calendar days”“due in 0 calendar days” | “1 calendar day”“due today”；首页 “1 order at risk” 单复数 | `backend/rules.py`；`Headline.tsx` |
| 证据抽屉每 30 秒抢回焦点并滚回顶部 | 只在打开时聚焦一次 | `EvidenceDrawer.tsx` |
| 晨报和订单页的证据表每行显示 “Version · Not recorded” | 只有带数据版本的聊天证据显示版本列 | `EvidenceDrawer.tsx` |
| 深色主题下底部导航数字徽标看不清（1.27:1） | 深色主题文字改深色（13.8:1） | `styles.css` |
| Watch 列表显示内部代码 `not_met` | 只显示结果说明；检查出错显示 “Check failed” | `Watches.tsx` |
| 编号列表各项之间有空行时全部显示 “1.” | 空行不打断列表；中断后续写的列表保留起始编号 | `Markdown.tsx` |
| 构造的链接（如 `#/chat/..%2Fdev%2Fdata%2Freset%3F`）点发送会重置数据快照；错误的 `%` 让页面白屏 | 请求路径里的 ID 全部编码，拒绝 “.” 和 “..”；地址里只接受 UUID 形式的会话 ID；顶层加错误边界，渲染出错时显示 Reload | `api.ts`、`route.ts`、`main.tsx`、`components/ErrorBoundary.tsx` |
| 聊天里叫 “Sources (n)”，其他地方叫 “Evidence”；只调用工具、没有引用行的回答没有按钮 | 统一为 “Evidence (n)”；调用过工具就显示 | `Chat.tsx` |
| `.bat` 是 LF 换行，GitHub ZIP 下载后 Windows 可能找不到 `goto` 标签 | 新增 `.gitattributes`：`.bat` 检出为 CRLF；CSV 和 JSONL 不做换行转换，评测报告里的数据哈希在各平台一致 | `.gitattributes` |
| 离线评测的 `-fake` 报告目录可能被误提交；`env.txt` 未忽略 | 两者加入 `.gitignore` | `.gitignore` |
| `openai` 只是间接依赖；Windows 缺时区数据 | `openai==3.49.0` 和 `tzdata`（仅 Windows）写入 `requirements.txt` | `backend/requirements.txt` |
| 5173 被占用时 Vite 悄悄换端口，启动脚本仍打开 5173 | `strictPort: true`，占用时直接报错 | `frontend/vite.config.ts` |

离线评测桩 `evaluation/fake_agent.py` 原本按 “due in” 开头筛选到期订单，已同步接受 “due today”。离线前端快照 `frontend/src/fixtures/briefing.json` 已用脚本重新生成，只有措辞和新增的 `not_checked` 字段变化。

### 验证

| 验证 | 结果 |
|---|---|
| 后端 pytest | **301 passed**（新增 7 项回归测试） |
| 前端测试、类型检查、生产构建 | 3 项通过；类型检查与构建无报错 |
| 离线 fake runner | evaluation 30/30，development 16/17（与修改前相同；不是 LLM 成绩） |
| 隔离端口 8001/5174 浏览器检查 | 上表前端各项逐一确认；证据抽屉打开 41 秒、经过一次后台刷新后焦点和滚动位置不变；控制台无报错 |

### 有意没有改的

以下涉及业务规则，需要 C 确认后再改：可行性否定结果补来源行和假设、自定义时期比较按工作日折算、重置快照后 watch 的判断。清单第二档的其余条目和第三档也未处理。

## 7. UI 审查修改（2026-11-12）

| 问题 | 修改后的行为 | 位置 |
|---|---|---|
| 订单页 “Unfinished orders by stage” 是很粗的胶囊柱，背后的浅色满高轨道像容量刻度；渐变填充；大片留白；没有悬停信息 | 改成按工序顺序（knitting → packing）的横向条形图：共用基线，条宽 16px，末端 4px 圆角；每条深色部分是有风险的订单，浅色部分是其余未完成订单，中间留 2px 间隙；数量写在条末；悬停或键盘聚焦时其余条变淡，并显示该工序的明细；去掉说明句，换成图例；深色主题有单独配色 | `frontend/src/components/OrdersPage.tsx`、`styles.css` |
| 图中每个工序的有风险数量 | 由后端统计：`GET /orders` 的 `summary.by_stage` 每项新增 `at_risk`；前端只按它画宽度，不自行计数 | `backend/order_search.py`；`frontend/src/types.ts` |
| 底部导航的 Conversations 只弹出一个小浮层；没有对话时只有一行字，看起来像没反应 | 改为独立页面 `#/chats`：按 Today / Previous 7 days / Older 分组列出全部对话，可筛选，显示时间，点开继续对话；任何屏幕宽度都可用；打开某个对话时，底部导航仍标在 Conversations | `components/Conversations.tsx`、`Dock.tsx`、`route.ts`、`App.tsx`、`sessions.ts` |
| 会话时间是不带时区的 UTC 文本，浏览器按本地时间解析，新加坡 0–8 点的对话被归到 “Previous 7 days”；新建对话在第一条回答返回前归在 “Older” | 按 UTC 解析；新建对话先按当前时间归入 Today | `frontend/src/sessions.ts`、`App.tsx` |

两种颜色用数据可视化校验脚本检查过：
- 两者差异：浅色主题 ΔE 22，深色主题 ΔE 29.5，色觉障碍模拟下也能区分。
- 对比度：深色主题两者都达到 3:1；浅色主题的灰色部分为 2.3:1，每条都写了数量，下面也有订单表，所以可以接受。

验证：
- 后端 302 项测试通过，新增每个工序有风险数量的测试。
- 前端测试、类型检查和生产构建通过。
- 在隔离端口检查了亮色、深色和手机宽度（390px）；空状态、悬停提示、对话页面的分组和打开都正常；控制台无报错。

## 8. 提醒分寸写成规则、语音输入输出（2026-11-12）

### 提醒分寸

原来的做法（只有经理自己设的 watch 和提醒会打断，其余发现等晨报）现在写成了规则，代码和界面也按这条规则统一。

| 位置 | 修改 |
|---|---|
| `README.md` 新增 “Alerts: what interrupts and what waits” | 列出每类事件是否打断、经理在哪里看到，以及这样分的四个理由：经理自己选择、数据没有实时更新、每个原因只提醒一次、不发到应用外。也写明没做的：按严重程度提醒、可调灵敏度 |
| `backend/actions.py` | 新常量 `INTERRUPTING_ALERTS = ("reminder", "watch")`。`counts()` 的 `unread_alerts` 只数这两类；新增 `unread_notices` 数晨报通知。原来晨报通知也算进底部导航 Watches 的数字，和规则不一致 |
| `frontend/src/components/Watches.tsx` | 两组提醒按同一规则划分；标题下写明各自的规则：“Your watches and reminders · counted on the dock”、“New briefings · not counted” |
| `backend/skills/standing_watch.md` | 加一条：只有确认过的 watch 和到期提醒会提醒；用户要求 “有风险就告诉我” 时，说明会等晨报，并提议对具体订单设 watch 或设提醒 |
| `docs/TRACK1_IMPLEMENTATION_PLAN.md` 12.4 | 加实现说明：没有按严重程度弹提醒，以及原因 |
| 测试 | `test_actions.py`、`test_chat_actions.py` 改为检查两个计数：数据推进一天后 watch 提醒计 1、晨报通知计 1；读掉 watch 提醒后为 0 和 1 |

### 语音

用浏览器自带的 Web Speech API，后端不接收音频，不加依赖。

| 功能 | 行为 |
|---|---|
| 语音输入 | 输入框旁的麦克风按钮；说话时文字实时填进输入框，停顿后自动停止；**不会自动发送**，订单号听错可以先改。输入框下选说话的语言：85 个语言和地区，用各自的语言显示名称，浏览器自己的语言排最前，默认跟浏览器语言；选择只存在本浏览器。浏览器的语音识别不能自动判断语言，所以必须选 |
| 朗读 | 每条回答下有 “Read aloud”，朗读时变成 “Stop”；勾选 “Read answers aloud” 后新回答自动朗读。**每条回答按它自己的语言朗读**，与语音输入选的语言无关：先看文字系统（中日韩、西里尔、阿拉伯、泰文、印度各文字等 20 多种），拉丁字母的语言用常见词和特有字母区分（英、法、西、葡、意、德、荷、马来、印尼、菲律宾、越南、土耳其、波兰等 20 种）；分不清时（马来语和印尼语）以选的语言为准。简体、繁体、粤语分别用对应语音。本机没有该语言的语音时显示 “No Chinese voice on this device”，不用错的语音硬读。去掉 Markdown 符号，表格逐行读，代码块跳过；按句切成不超过 200 字的段落排队朗读（Chrome 长句约 15 秒会中断） |
| 互相打断 | 开始语音输入、发送新问题、离开当前对话都会停止朗读；发送时正在进行的语音输入会取消，不会把迟到的识别结果写回输入框 |
| 浏览器支持 | 语音输入：Chrome、Edge、Safari；Firefox 只有朗读。不支持的浏览器不显示对应按钮。语音输入的音频会交给浏览器厂商的语音服务（Chrome 是 Google，Edge 是 Microsoft，Safari 是 Apple），README 已写明 |
| 后端 | 不用改：`base_grounding_policy` Skill 已要求 “Reply in the user's language”，模型调用前也没有只认英文的规则 |
| 代码 | 纯函数 `frontend/src/voice.ts`（12 项测试 `tests/voice.test.ts`，识别样例覆盖 22 种语言，含简繁中文和粤语）；React 部分 `useVoice.ts`；`Chat.tsx` 接入；`Icon.tsx` 新增 mic、speaker、stop |

### 顺带修复：手机宽度页面被撑宽

检查手机宽度（375px）时发现：顶栏的品牌名、“Data as of 2026-04-01” 和搜索按钮都不换行，最小宽度 404px，把整个页面撑宽，右侧被裁掉，聊天的 Send 按钮只露出一半。与本次修改无关，之前就存在。
- 页面外框改为单列且不超过屏幕宽度。
- 手机上数据日期标签只显示日期，读屏仍读 “Data as of”。
- 修改后首页、晨报、订单、Actions、Watches、对话页在 375px 下都没有超出屏幕的内容。

### 验证

| 验证 | 结果 |
|---|---|
| 后端 pytest | 302 passed |
| 前端测试、类型检查、生产构建 | 15 项通过（新增 12 项语音测试）；无报错 |
| 隔离端口 8001/5174 浏览器检查 | Watches 页规则文字显示正常，底部 Watches 不再因晨报通知显示数字。语音用替身对象测试，不发声、不请求麦克风：输入时文字实时出现、停止后不自动发送；朗读按钮切换 Stop / Read aloud；自动朗读读的是新回答。用中文（简、繁）、日、韩、法、西、阿拉伯语提问，回答都配到本机对应语言的语音；去掉中文语音后显示 “No Chinese voice on this device”；选马来语后语音识别收到 ms-MY。本机（macOS）有 39 种语言的语音。亮色、深色、手机宽度都检查过 |
| 没有测的 | 真实麦克风识别和真实发声没有在本机测，需要在 Chrome 或 Safari 打开 5174 手动试一次 |

## 9. 最终候选版四项边界修复（2026-11-12）

本轮仅处理代码审查中已复现的四项问题；不新增业务功能，不修改历史模型评测成绩，不调用真实模型 API。

| 问题 | 修改后的行为 | 回归证据 |
|---|---|---|
| 聊天已提交但响应丢失，Retry 生成第二轮及第二张提案 | 客户端保留逻辑请求 ID；后端短事务登记请求，已完成请求返回已保存的回答与证据；会话保存、提案激活、响应登记同一事务提交；并发处理中返回可重试冲突。新建会话响应丢失也复用原会话。后台续租及 owner 校验防止过期执行覆盖新请求 | `backend/tests/test_chat_retries.py`、`frontend/tests/chatRetry.test.ts` |
| 晨报计算与原始证据使用不同快照 | 晨报计算、完整 payload、调度保存及相关订单/产量/估算视图固定一次数据上下文；嵌套调用继承上层版本；下一次请求才读取新的数据日 | `backend/tests/test_briefing_snapshot_race.py`：真实 HTTP 并发切换快照及调度/视图回归 |
| CSV 行号为 88 时，同答案中的错误“88 个订单”也被豁免 | 保留原文数字位置，只豁免真实引用处的数字；中文必须包含“行”；业务数字与行号分开检查，引用顺序不会影响结果 | `backend/tests/test_answer_check.py`：新增 16 个参数化用例 |
| 旧订单筛选请求迟到，覆盖当前列表或错误状态 | 更换筛选时立即隐藏旧列表；取消旧请求的成功和失败回调发布；搜索 debounce、重试及卸载同样受保护；保留全量下拉选项 | `frontend/tests/orderLoad.test.ts`：5 项回归；浏览器中人为延迟 unfinished 响应 8 秒，Complete 始终保持 86 个已完成、0 个未完成、0 个风险订单 |

### 适用边界

- 聊天重试保护依赖相同 `request_id`；旧 CLI/API 调用仍兼容，但不传 ID 不具备该保护。前端刷新或离开会话会清除本地重试身份，应先查看会话历史及 Actions。
- 同一 ID 改内容返回 `REQUEST_CONFLICT`；正在处理返回 `REQUEST_IN_PROGRESS`。失败可同 ID 重试；进程崩溃后等待旧租约过期再恢复。
- 答案检查仍为启发式数值检查，不是完整语义验证；本轮只消除行引用导致的错误豁免。
- 浏览器回归使用临时数据库和隔离测试服务；不触碰现有用户会话或提醒。真实模型、语音识别、独立 held-out 评测不属于这轮工程回归。

### 本轮最终验证

| 检查 | 结果 |
|---|---|
| 后端全量 `python -m pytest -q` | **339 passed**；较本轮前新增 37 项（聊天重试 16、晨报/视图快照 5、答案行号检查 16） |
| 前端 `npm test` | **24 passed**；较本轮前新增 9 项（订单请求 5、聊天重试 4） |
| 前端 `npm run build` | TypeScript 检查和 Vite 生产构建通过 |
| 评测定义 `--check` | 30 evaluation + 17 development 定义有效；仓库的独立审核标记仍为 0 verified，本轮未改评测标签 |
| 离线 `--fake --no-ledger` | 30/30 流程通过；不是 LLM 或 held-out 成绩，不覆盖历史真实报告 |
| 订单筛选实际浏览器回归 | 已确认旧 unfinished 请求晚于 Complete 响应返回；页面仍显示 86 个已完成订单，统计与筛选一致 |

重放已完成聊天请求时，只刷新提案的当前 `EXECUTED / CANCELLED / EXPIRED` 等状态；原回答、工具结果和历史证据保持不变。相关回归也包含在 339 项中。

本地检查日志和订单截图保存在课程目录 `Capstone Project/Local_Fixes_2026-11-12/`。本轮未执行 Git commit、push 或真实模型调用；最终真实模型评测及公开仓库 clean-checkout 验证仍需在发布时完成。
