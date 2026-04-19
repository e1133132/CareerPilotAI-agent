# 功能开发计划（Qdrant 向量检索 + 自动初始化）

## 1) 目标
- [x] 将 `jobs.jsonl` 与 `learning_resources.jsonl` 从“每次请求实时向量化”改为“预先入库 + 查询时仅向量化 query”，减少接口超时。
- [x] 保持现有 API 返回结构不变（`/api/careerpilot/run` 输出字段不变），仅优化检索实现与性能。
- [x] 支持组员本地一键运行：若未部署 Qdrant，可自动启动（Docker）并自动完成向量化初始化。

### 可衡量成功标准
- [ ] 首次冷启动（含建库）可在可接受时间内完成（目标：<= 2 分钟，视网络而定）。
- [ ] 二次请求（已建库）`/api/careerpilot/run` 平均耗时较当前版本明显下降（目标：下降 40%+）。
- [ ] 无 Qdrant 环境下执行项目，不需要手工建库命令即可完成初始化并返回结果。

## 2) 非目标
- [x] 本阶段不改业务 Prompt 逻辑与报告字段语义。
- [x] 本阶段不引入付费托管向量服务（仅本地/自托管免费 Qdrant）。
- [x] 本阶段不做大规模数据扩容优化（当前以已有数据集为主）。

## 3) 需求清单
- [x] 新增 Qdrant 配置项（URL、collection 名称、自动初始化开关、启动开关）。
- [x] 启动时检查 Qdrant 可用性；不可用时自动尝试通过 Docker 启动 Qdrant。
- [x] 首次运行自动将 `data/jobs.jsonl` 与 `data/learning_resources.jsonl` 向量化并 upsert 到对应 collection。
- [x] 数据版本检查（至少基于文件 hash 或更新时间），数据变更时可自动重建/增量更新。
- [x] `job_matching` 与 `learning_rag` 优先走 Qdrant 检索；失败时保留 keyword fallback，避免服务中断。
- [x] 增加可观测日志（初始化耗时、入库条数、检索命中数、fallback 触发原因）。

## 4) 验收标准
- [ ] Given 本机无 Qdrant 容器，When 启动 API 并发起首次请求，Then 系统自动拉起 Qdrant、自动建库并成功返回结果。
- [ ] Given Qdrant 已启动且库已建，When 连续发起请求，Then 不再重复全量向量化，响应时间明显降低。
- [ ] Given Qdrant 临时不可用，When 发起请求，Then 系统记录告警并走本地 fallback，不出现服务崩溃。
- [ ] Given 当前测试数据，When 对比改造前后返回结构，Then 关键字段兼容（`candidate_profile`、`recommended_jobs`、`study_plan` 等）。

## 5) 技术方案
- [x] 新增向量存储模块（建议 `tools/vector_store_qdrant.py`）封装：
- [x] `ensure_qdrant_ready()`：健康检查 + 自动启动容器（可配置开关）。
- [x] `ensure_collections()`：创建 `jobs` / `learning_resources` collection（vector size 自动探测）。
- [x] `index_jobs_if_needed()` / `index_learning_resources_if_needed()`：文件 hash 变更检测 + 批量 upsert。
- [x] `search_jobs()` / `search_learning_resources()`：query embedding 后向量检索并返回 top-k。
- [x] 改造 `tools/semantic_match.py` 与 `tools/learning_rag.py`：优先调用 Qdrant 检索，失败 fallback 到现有 keyword 方案。
- [x] `api.py` 启动阶段增加轻量初始化钩子（避免首次请求完全阻塞，可选懒加载）。
- [x] `docker-compose.yml` 增加 `qdrant` 服务、volume 持久化和应用服务依赖关系。

### 依赖与兼容性
- [x] 新增依赖：`qdrant-client`。
- [x] 默认保持无侵入：若关闭 Qdrant 开关，系统行为回退到当前逻辑。
- [x] 保持 `OPENAI_EMBEDDING_MODEL` 与索引一致，模型变更触发重建提示。

## 6) 风险与回滚
- [ ] 风险 1：Docker 不可用导致自动启动失败。
- [ ] 风险 2：首次索引构建耗时较长，首请求体验仍慢。
- [ ] 风险 3：embedding 维度/模型切换导致 collection 不兼容。
- [ ] 回滚触发：Qdrant 初始化失败率高或检索结果异常。
- [ ] 回滚策略：关闭 Qdrant 开关，切回现有本地检索与 keyword fallback 实现。

## 7) 任务拆分（小批次）
- [x] T1（配置与基础设施）
  - 新增配置项与依赖；补充 Docker Compose 的 Qdrant 服务和持久化卷。
  - 实现 Qdrant 健康检查与可选自动启动机制。
- [x] T2（数据索引初始化）
  - 实现 jobs / learning_resources 的入库、版本校验、重建逻辑。
  - 在应用启动或首次请求前完成 `ensure indexed`。
- [x] T3（检索路径接入）
  - `job_matching` 与 `study_planning` 检索改为优先 Qdrant。
  - 保留并验证 fallback 路径，保证可用性。
- [x] T4（验证与文档）
  - 增加本地验证步骤、性能对比记录、README 部署说明。
  - 确认组员“仅运行项目”可完成自动初始化和本地测试。

## 8) 简历分析提速（LLM输入与检索性能）
### 目标
- [x] 降低每次请求非必要控制台 IO（`agents/resume_analysis.py`、`tools/resume_io.py`）
- [x] Qdrant 失败/无结果时默认走 `keyword` fallback（避免逐条 embedding 的 O(N) 路径）
- [x] 缓存 `data/jobs.jsonl` 与 `data/learning_resources.jsonl` 的解析结果（减少磁盘 IO）
- [x] 对发给大模型的输入长度做配置化截断（降低 LLM 延迟/超时概率）
- [x] 为 OpenAI 请求增加 `request_timeout` 与 `max_retries`（默认 0 重试）
- [x] 支持“Study Plan 分阶段返回”：先返回其余部分，plan 后台完成后再拉取展示（避免 UI 因 `stage=plan` 阻塞）

### 可衡量成功标准
- [ ] 以同一份简历连续调用 `/api/careerpilot/run` 10 次，平均耗时较改造前下降明显（目标：40%+）
- [ ] 低 Qdrant 可用性/失败场景下不再出现“极慢逐条 embedding 回退”（超时率下降）
- [ ] 前端使用 `run_partial + 轮询 result/{run_id}`：应当能在 plan 未完成时先看到 profile/jobs/gaps，plan 完成后自动补齐显示

---

## 9) Explainability（可解释性 + API `explainability` 区块）

### 9.0 非回归约束（实现时必须遵守，不得影响原有功能与体验）

- **业务逻辑不变**：不改变各 agent 的推荐/打分/排序规则、Prompt 语义、检索 top-k 与 fallback 触发条件；explainability 只做**旁路记录与响应挂载**，不参与决策分支。
- **契约兼容**：现有响应中的顶层字段名、含义、结构保持不变；仅**新增**可选字段（如 `explainability`）。旧客户端忽略新字段即可，行为与改造前一致。
- **性能与可靠性**：不新增 LLM 调用；用户可读 **`rationale`** 须遵守 9.3「实现策略」（从已有输出派生或合并进该步现有结构化输出）；轨迹与 meta 为内存组装或轻量字段拷贝，避免明显延迟或超时风险；不得因记录失败而中断管线（失败时可省略 `explainability` 或填空结构，并打日志）。
- **分阶段 API**：`run_partial` / `result/{run_id}` 的既有阶段语义、轮询约定、`ok`/`error` 行为保持不变；仅在成功响应中附加说明性数据。
- **测试**：除为 `explainability` 增加断言外，对核心业务路径保留或补充回归断言，确保推荐结果结构未被无意改写。

### 9.1 目标
- [ ] 在 API 响应中增加 **`explainability`** 区块，使「每个 agent 的中间结果如何推导出最终推荐」可被前端展示与答辩说明。
- [ ] **面向用户的「为何如此分析」**：除技术轨迹外，为各核心阶段提供**简短、可读**的原因说明（例如：为何从简历读出这些要点、为何推荐这些岗位、为何判定这些技能缺口、学习计划为何围绕这些资源），便于用户理解「系统为什么这么分析」，而非仅看到结果列表。
- [ ] **向后兼容**：保留现有顶层字段（`candidate_profile`、`recommended_jobs`、`skill_gaps`、`study_plan`、`full_state` 等），在新增字段中补充轨迹；集成测试可按新契约更新断言。

### 9.2 非目标
- 不实现完整 XAI 模型内部归因（如 attention 可视化）。
- 不强制修改 Prompt 语义；仅在结构化输出层增加轨迹与降级说明。
- 前端 UI 的具体样式由前端仓库负责；本仓库提供稳定 JSON 契约。

### 9.3 概念设计

#### `pipeline_trace`（阶段轨迹）

有序列表，每条对应一次「编排步 + agent 执行」，建议字段：

| 字段 | 说明 |
|------|------|
| `stage` | 与 orchestrator 一致：`resume` / `match` / `gap` / `plan` |
| `agent` | `resume_analysis` / `job_matching` / `skill_gap` / `study_planning` |
| `summary` | 一句话说明本步产出（偏技术/调试；英文或中英均可） |
| `rationale` | **面向终端用户**：本步「为何这样分析 / 为何给出该结果」的简短说明（与 `summary` 区分：`rationale` 给用户看，`summary` 可给开发或并列展示） |
| `output_keys` | 本步写入 state 的键名列表，如 `["candidate_profile","resume_evidence"]` |
| `duration_ms` | 可选，本步耗时 |
| `timestamp` | ISO8601 可选 |

#### `fallback_events`（降级与可解释性）

当 Qdrant 失败、走 keyword、或 skill_gap 走 rule-based 时追加一条：

| 字段 | 说明 |
|------|------|
| `component` | `job_matching` / `learning_rag` / `skill_gap` 等 |
| `from` | 期望路径，如 `qdrant` |
| `to` | 实际路径，如 `keyword` |
| `reason` | 简短原因（不含敏感信息） |

#### `limitations`（固定短文本，可选）

- 例如：结果依赖简历可解析文本、岗位数据集范围、LLM 随机性等（1～3 条字符串）。

#### 用户可读原因与现有字段的关系

- 与现有 **`resume_evidence`**、岗位 **`score` / `score_method`**、**`skill_gaps`** 等**互补**：`rationale` 用自然语言串起来说明「为什么」，证据与分数仍在原字段中；避免在 `explainability` 里重复粘贴整段简历或全文检索结果。
- **实现策略（遵守 9.0）**：优先从**当前 agent 已有输出**摘要或结构化生成 `rationale`（例如在现有 JSON 解析结果上填 1～3 句），**不**为 explainability 单独增加一次「仅写解释」的 LLM 调用；若课程要求必须从模型生成解释，应**合并进该步现有 prompt 的一次性结构化输出**，而非额外 round-trip。

### 9.4 代码修改清单（按文件）

**`state.py`**
- 在 `State` 中增加可选字段：`pipeline_trace`、`fallback_events`（或仅在 `api` 内组装，见下）。
- **推荐**：不在 TypedDict 里用复杂 `Annotated[..., operator.add]`，而在 **`api.py` 的 `_run_pipeline` / `_run_pipeline_until_gap` 内**维护局部列表，循环结束后写入 `state["pipeline_trace"]` 与 `state["fallback_events"]`，避免大规模改 `participant` 返回值格式。

**`api.py`**
- **`_run_pipeline`**：在 `while` 循环内，每次 `orchestrator` 之后、`participant` 之后：记录 `stage`、`agent`、`output_keys`、可选 `time.perf_counter` 差。
- **`_run_pipeline_until_gap`**：对三步 participant 同样追加 trace（共用辅助函数或传入 `trace` 列表）。
- **`_finish_study_plan`**：study_plan 完成后合并 trace（若 background 任务单独跑，从 `partial_state` 复制已有 trace 再追加 plan 步）。
- **`run_careerpilot` / `run_careerpilot_partial` / `get_careerpilot_result`**：在 JSON 响应根级增加 `explainability: { pipeline_trace, fallback_events, limitations }`；`full_state` 内也可包含相同键；**`pipeline_trace` 每条尽量带 `rationale`（用户可读「为何如此分析」）**。

**`agents/resume_analysis.py`（可选但建议）**
- 在结构化输出或 `explainability_meta` 中提供**简短用户向说明**：例如依据简历中哪些类型的信息推断出 `candidate_profile` 要点（无需泄露敏感原文）。

**`tools/semantic_match.py` / `tools/learning_rag.py`**
- 在确定走 keyword / local embedding fallback 时，除日志外需让上层可见：**优先在 `agents/job_matching.py` / `agents/study_planning.py` 的 `run` 返回**中增加 `explainability_meta`（如 `retrieval_method`），由 api 合并进 `fallback_events`；避免全局 contextvar，除非改动面过大。

**`agents/job_matching.py` / `agents/study_planning.py`**
- 除 `explainability_meta`（检索路径）外，提供 **`rationale` 或用于生成 `rationale` 的要点**（例如：与用户画像/目标岗位对齐的匹配思路），供 API 写入对应 `pipeline_trace[].rationale`，**给用户看「为什么推荐这些岗位 / 为什么选这些学习资源」**。

**`agents/skill_gap.py`**
- 若走 langchain 缺失时的 rule-based 分支，在返回 dict 中增加 `explainability_meta`（如 `mode: "rule_based_fallback"`），便于写入 `fallback_events`。
- 提供用户向 **`rationale`**（或生成要点）：**为何判定这些缺口、优先级依据**（可与 `missing_skills[].reason` 呼应，避免重复可只做汇总句）。

**`tools/explainability.py`**
- `default_limitations()`、`build_explainability_block()`、各步 `rationale` 与 fallback 辅助函数；集中管理 `limitations` 文案。

**`tests/integration/test_api.py`**
- 断言响应含 `explainability`；`pipeline_trace` 长度与阶段一致或 ≥ 1；**关键条目含非空 `rationale`（或约定占位策略）**；mock 路径不依赖真实 LLM。

**`CHANGELOG_DEV.md`**
- 记录本次功能与 API 契约变更。

### 9.5 API 响应示例（目标形状）

```json
{
  "ok": true,
  "candidate_profile": {},
  "explainability": {
    "pipeline_trace": [
      {"stage": "resume", "agent": "resume_analysis", "summary": "...", "rationale": "We inferred your profile from your stated roles and skills because ...", "output_keys": ["candidate_profile", "resume_evidence"]},
      {"stage": "match", "agent": "job_matching", "summary": "...", "rationale": "These jobs align with your target role and skill overlap because ...", "output_keys": ["job_matches"]}
    ],
    "fallback_events": [],
    "limitations": [
      "Recommendations are based on the parsed resume text and a fixed job dataset."
    ]
  },
  "full_state": {}
}
```

### 9.6 任务拆分（建议顺序）

| 任务 | 内容 |
|------|------|
| T1 | `api.py`：`_run_pipeline` / `_run_pipeline_until_gap` 内 `pipeline_trace` 与时间戳；响应挂载 `explainability`；**将各步返回的 `rationale` 写入 `pipeline_trace[].rationale`** |
| T2 | `resume_analysis`（可选）/`job_matching` / `study_planning` / `skill_gap`：返回 **`explainability_meta`**、**用户可读 `rationale`（为何如此分析）**，以及必要时写入 **`fallback_events`**；与 9.3「用户可读原因」一致 |
| T3 | `semantic_match` / `learning_rag` 或 agent 层：记录检索路径（qdrant vs keyword）；**与 T2 的 `rationale` 合并时注意不重复啰嗦** |
| T4 | 测试更新 + `CHANGELOG_DEV` + README 中 API 说明一行 |

### 9.7 验收标准
- [ ] `POST /api/careerpilot/run` 返回体含 `explainability.pipeline_trace`，且顺序与真实阶段一致。
- [ ] **`pipeline_trace` 中关键阶段含 `rationale`**，用户能读懂「为何这样分析 / 为何推荐」，且**不依赖额外仅用于解释的 LLM 调用**（符合 9.3 实现策略）。
- [ ] 在模拟 Qdrant 不可用时，`fallback_events` 非空且 `reason` 可读。
- [ ] 现有集成测试通过或已按新契约更新断言。
- [ ] 答辩可指着 JSON 说明「每一步对应哪个 agent、输出哪些键」，并展示 **`rationale` 的用户价值**。

---

## AI 执行规则（每次改代码前必须遵守）
1. 先确认范围：仅实现本文件中已勾选或明确批准的任务。
2. 开始编辑前，重新核对验收标准。
3. 一次只做一个小且可验证的改动。
4. 每次改动后，都要执行或说明对应行为的验证结果。
5. 每次改动完成后，立即在 `CHANGELOG_DEV.md` 记录变更。
6. 不允许静默扩展范围；先新增任务再实施。
7. 只要存在不确定性，先暂停并提问确认。
8. Explainability 相关实现按 **第 9 节** T1→T4 顺序；遵守 **9.0 非回归约束**；不删除现有业务字段。
