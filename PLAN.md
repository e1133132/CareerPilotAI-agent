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

## AI 执行规则（每次改代码前必须遵守）
1. 先确认范围：仅实现本文件中已勾选或明确批准的任务。
2. 开始编辑前，重新核对验收标准。
3. 一次只做一个小且可验证的改动。
4. 每次改动后，都要执行或说明对应行为的验证结果。
5. 每次改动完成后，立即在 `CHANGELOG_DEV.md` 记录变更。
6. 不允许静默扩展范围；先新增任务再实施。
7. 只要存在不确定性，先暂停并提问确认。
