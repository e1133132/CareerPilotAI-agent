# 开发变更日志

使用本文件记录开发过程中的关键事实与决策。

---

## 2026-03-25 12:30（本地时间） | 任务：QDRANT-QUERY-POINTS
- **类型**：fix
- **改动文件**：
  - `tools/vector_store_qdrant.py`
  - `pyproject.toml`
  - `uv.lock`
- **改动内容**：
  - 将 `QdrantClient.search()` 替换为 `query_points()`（兼容 qdrant-client 2.x，该类已无 `search` 方法）。
  - 在 `pyproject.toml` 中补齐 `fastapi`、`uvicorn`、`python-multipart`、`pypdf`，并执行 `uv lock`，修复 `uv run uvicorn` 找不到可执行文件的问题。
- **改动原因**：
  - 运行时出现 `'QdrantClient' object has no attribute 'search'`，导致回退到 `embedding_cosine`。
- **验证方式**：
  - `uv lock` 成功；本地可再跑接口确认 `score_method` 为 `qdrant_cosine`。
- **影响范围**：
  - 仅向量检索调用方式与 uv 依赖声明；行为上恢复使用 Qdrant。

---

## 2026-03-25 12:00（本地时间） | 任务：UV-QDRANT-DEP
- **类型**：update
- **改动文件**：
  - `pyproject.toml`
  - `tools/vector_store_qdrant.py`
  - `tools/semantic_match.py`
  - `tools/learning_rag.py`
- **改动内容**：
  - 将 `qdrant-client` 写入 `pyproject.toml`，使 `uv sync` / `uv run` 与 `requirements.txt` 一致。
  - Qdrant 检索失败时发出 `warnings.warn`，避免静默回退到 `embedding_cosine` 却无从排查。
  - 在 `DEBUG=true` 时通过现有 `debug()` 输出索引/客户端不可用提示。
- **改动原因**：
  - 仅用 `uv run` 而未安装 `qdrant-client` 时，Qdrant 分支会返回空列表，响应里仍显示 `embedding_cosine`，易误判为「向量库未生效」。
- **验证方式**：
  - 尚未运行 `uv sync`（需在本地执行）。
- **影响范围**：
  - 依赖声明与可观测性；业务逻辑不变。
- **后续事项**：
  - 执行 `uv sync` 后重试接口，确认 `recommended_jobs` 与 RAG 条目的 `score_method` / `match_method` 为 `qdrant_cosine`。

---

## 2026-03-25 11:05（本地时间） | 任务：DEV-DB-ONLY-COMPOSE
- **类型**：update
- **改动文件**：
  - `docker-compose.yml`
- **改动内容**：
  - 移除 `careerpilot-ai` 服务定义，`docker compose` 仅保留 `qdrant` 数据库服务。
  - 保留 `qdrant_storage` volume 与网络配置，便于本地 app 连接容器数据库调试。
- **改动原因**：
  - 开发阶段希望本地运行应用、仅用 Docker 托管数据库，避免端口冲突并提高调试效率。
- **验证方式**：
  - 配置结构检查通过（仅保留 qdrant service）。
  - 运行验证待执行：`docker compose up -d` 后用 `docker ps` 确认仅 qdrant 在运行。
- **影响范围**：
  - Compose 启动行为变更为“仅数据库”，不再启动应用容器。
- **后续事项**：
  - 本地启动应用时需设置 `QDRANT_URL=http://localhost:6333`。

---

## 2026-03-25 10:45（本地时间） | 任务：T1-T4
- **类型**：add | update
- **改动文件**：
  - `tools/vector_store_qdrant.py`
  - `tools/semantic_match.py`
  - `tools/learning_rag.py`
  - `agents/study_planning.py`
  - `api.py`
  - `config.py`
  - `docker-compose.yml`
  - `requirements.txt`
  - `README.md`
  - `PLAN.md`
- **改动内容**：
  - 新增 Qdrant 向量存储与检索模块：健康检查、可选自动启动、按数据 hash 自动索引、query 检索。
  - Job matching 与 learning RAG 改为优先走 Qdrant；不可用时自动回退到原有检索逻辑。
  - API 启动加入 Qdrant 索引预热；Compose 新增 qdrant 服务与持久化 volume；补充部署说明。
- **改动原因**：
  - 降低每次请求重复向量化开销，减少超时并提升本地/组员一键运行体验。
- **验证方式**：
  - `python3 -m compileall api.py config.py tools agents`：通过。
  - `python3 -m pytest -q`：环境缺少 `pytest`，未执行测试用例（非代码错误）。
- **影响范围**：
  - 影响检索路径与部署方式；业务输出字段保持兼容。
- **后续事项**：
  - 安装测试依赖后执行完整接口回归与性能对比，补齐 PLAN 的量化验收项。

---

## 2026-03-25 | 任务：PLAN-QDRANT
- **类型**：update
- **改动文件**：
  - `PLAN.md`
- **改动内容**：
  - 将通用计划模板替换为 Qdrant 向量检索专项计划（目标、非目标、需求、验收、风险、任务拆分）。
  - 明确“自动部署 Qdrant + 自动向量化初始化 + fallback 可用性”的实施边界与验收口径。
- **改动原因**：
  - 在动代码前先完成可审核的实施计划，确保范围可控、便于团队协作与本地部署。
- **验证方式**：
  - 人工核对计划结构完整性（目标/需求/验收/风险/任务拆分均已落地）。
  - 代码尚未修改，暂无运行验证。
- **影响范围**：
  - 仅影响规划文档，不影响当前程序行为。
- **后续事项**：
  - 待你审核计划后，再按 T1->T4 分批实施并逐步记录变更。

---

## 记录模板
### YYYY-MM-DD HH:MM（本地时间） | 任务：T#
- **类型**：add | update | remove | refactor | fix
- **改动文件**：
  - `path/to/fileA`
  - `path/to/fileB`
- **改动内容**：
  - 简洁事实描述 1
  - 简洁事实描述 2
- **改动原因**：
  - 该改动对应的问题/风险/需求
- **验证方式**：
  - 执行的命令/测试/检查
  - 结果摘要
- **影响范围**：
  - 对 API/UI/DB/行为的影响
- **后续事项**：
  - 下一步任务或已知限制

---

## 记录规则（开发过程中必须遵守）
1. 每个有意义的改动批次写一条记录（不是每一行改动都记）。
2. 记录要客观、简洁，避免模糊描述。
3. 必须写验证证据，或明确标注“尚未验证”。
4. 若影响功能行为，需说明受影响流程。
5. 若存在回滚风险，记录中需附回滚提示。
6. 最新记录放在最上方，便于快速审阅。
