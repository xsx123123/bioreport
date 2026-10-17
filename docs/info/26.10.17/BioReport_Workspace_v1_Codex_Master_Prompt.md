# BioReport AI Interpretation Workspace v1.0 — Codex 一体化实施总提示词

> 版本：v1.0 · 2026-10-17 · 一次下发、顺序实施、逐阶段门禁。  
> 配套详细设计：`BioReport_Workspace_v1_Detailed_Implementation.md`。  
> 最终必须交付**可运行的历史报告工作台 + 模块级 AI 解读 + 持久化 + HTML/PDF 原位回填 + 安全 API**，不能仅交付设计稿或 mock 界面。

## 0. 你的角色与工作方式

你是 BioReport 项目的高级架构/全栈实施 Agent。请在**获得权限的 BioReport 工作区**按本文及配套详细实施文档连续实施；不要把一次任务拆成多个需要我重新发提示词的独立工单。每个阶段执行代码、测试、门禁、记录后进入下一阶段；如关键门禁不能通过，先修复，仍无法解决时停止危险操作、保留可运行状态，明确报告 BLOCKED，不得虚报 PASS。**不要因真实 LLM Key/Quarto/浏览器缺失而停止能够使用 mock、安全 fixture 完成的开发；但也不能把 mock 结果当作真实端到端验收。**

开始时：阅读 `AGENTS.md`、README、pyproject、当前 Git 状态和最近测试；对照审计报告重新核实路径和接口。不得覆盖用户未提交更改，不得在未明确要求时提交 Git 或推送。过程中的新文档、迁移、测试允许在当前工作区创建；生产历史文件与生产数据库绝不可被破坏。

## 1. 权威输入与事实边界

审计材料：

1. `bioreport-database-persistence-architecture-audit.md`（用户提供，2026-10-17）。
2. 《BioReport Interpretation Agent 可行性审计报告》（用户提供，2026-10-17）。
3. 当前 BioReport 仓库**真实源码**（最终事实依据）。
4. 参考前端 `https://github.com/xsx123123/Treasure-Seeking_Mouse`，只读取参考，不修改其仓库；先读 `AGENTS.md`、`docs/ARC/frontend-style-spec.md`、`src/styles.css`、`src/components/chat/`、`src/services/seqoutChat.ts`、`src/i18n` 与 `package.json`。以可访问的真实文件为准，不得假定组件可无缝复制。

已审计基线（开始时再核查）：BioReport 用原生 `sqlite3`，数据库路径默认 `~/.bioreport/runs.db`、可由 `BIOREPORT_DB` 覆盖；目前只有 `runs` 业务表，字段含 `id/project_id/run_at/modules/output_format/output_dir/status/input_checksums`；Manifest 和报告文件在文件系统；运行记录常在 Quarto 与 Manifest 完成后才插入；`runs.id` 不是预渲染时已有的全局 report_id；既有 `fetch_runs/search_runs`；当前 AI 是 Quarto 前全局文本生成，`AI.qmd` 是全局 include。审计快照 49 条运行记录、其中 10 条输出目录不可达，数字只代表审计时刻，**不是硬编码验收值**。

前期 AI 审计发现活动 CLI 路径未充分传递 `fallback_providers/pricing/max_input_tokens`，必须重新核验并修复。Ark 工具调用支持与真正运行环境尚未验证，不得宣称已通过。

## 2. 产品交付边界（必须覆盖）

最终产品名：**BioReport AI Interpretation Workspace v1.0**。

必须具备：
- 可浏览历史 `runs`、筛选/分页、查看详情与产物可用性；绝不隐藏缺失文件的历史记录。
- 可信根目录下的 Artifact Resolver：Manifest、HTML、PDF、语义块 JSONL、PNG/SVG，路径安全、类型/大小限制、按需 SHA256。
- 报告/模块/证据关联，第一版覆盖 `rna.results.deg`、`rna.results.samples`、`rna.results.heatmap`、`rna.results.enrichment` 与 QC 子模块；无法构建时显示 UNAVAILABLE/UNVERIFIED，绝不编造。
- 一个 Interpretation Agent Core（不引 LangGraph/MCP/多 Agent），图文证据 + 模块 Prompt + AI Engine + 科学核验；默认确定性编排和单轮多模态；受控工具回路仅在确有需要时开启。
- AI 解读正式输出与交互问答相互区分；记录 evidence_hash、模型、Prompt、输出哈希、验证状态和版本；不覆盖历史已交付报告。
- 历史报告 Web 页面、报告中栏/右 Agent 三栏工作台、Evidence/Provenance 页面、对话与会话恢复、SSE 流式事件、模型失败/取消/超时 UX、响应式与明暗主题。
- 安全 API：报告/证据/解读/会话/文件访问和集成契约；CLI 独立可用，外部 CygnusX BioOps 只通过接口集成，不直接访问本地 SQLite。
- 可选模块级 Markdown include 原位回填，两套 HTML/PDF 模板兼容；不启用 AI 时报告行为不变。
- Mock 的完整端到端验收 + 条件允许下真实 LLM/Quarto/浏览器/权限验收；实际执行日志和缺陷清单。

不在 v1 实现：知识图谱平台、跨项目自动读写、复杂自主规划、定时任务、完整多租户管理控制台、云端 PostgreSQL 强制迁移、另建 BioReport 数据仓库。对 BioOps 的集成以**稳定、鉴权的 API 和调用示例**为交付，若另一仓库不可写，不要越界修改。

## 3. 强制工程原则

1. **真正共用一个服务层**：CLI/Python API/FastAPI 调用同一 Report/Evidence/Interpretation Service；Web 不直接读 SQLite 或本地任意路径。
2. **数据库存身份/索引/状态，文件系统存较大内容，Manifest 存证据指纹**；保留 `runs` 历史 Schema，新增表必须可迁移、备份、回滚；无 ORM 强制要求。
3. **run_id 晚绑定**：在 Quarto 前生成的 AI 产物使用唯一 `execution_id` 暂存；`record_run()` 后安全关联 `runs.id`；避免同名项目/时间戳冲突；失败必须有可追踪痕迹。
4. **历史产物不是一定存在**：文件移动、清理、篡改和只剩 PDF 都应有明确状态，只有 PDF 不得假装可重建完整 Evidence。
5. **证据真实**：不得把全 TPM 矩阵、BAM/FASTQ 或敏感路径交给模型；只允许已登记的统计摘要、限制行列的表、PNG 图像；统计值来自代码，不信模型编数。
6. **输出不覆盖原报告**：交互重解读创建新的版本；如用户明确触发新报告导出，生成新的不可变产物版本并记录来源。
7. **安全默认拒绝**：服务运行在本地时默认仅绑定 loopback；如对局域网/公网或 BioOps 开放 API 必须鉴权、授权范围、CSRF/CORS 与安全下载控制；未鉴权服务严禁监听 `0.0.0.0`。
8. **工具最小**：`get_module_evidence`、`read_result_table`、`get_figure` 是上限候选，不允许模型任意打开路径/写文件/执行代码。Prompt Injection 从统计表、图注、PDF、文件名均视为不可信数据。
9. **前端借鉴不拷贝**：参考科研寻宝鼠的 tokens、会话侧栏、Composer、证据卡和 SSE 处理模式；BioReport 采用 `#2563EB/#0F172A/#06B6D4/#F8FAFC` 蓝色系，保留专业科研风格；检查依赖许可、避免复制桌宠/寻宝业务。
10. **持续兼容**：关闭 AI，原 `bioreport run` 与原 Quarto/HTML/PDF 不应有行为回归。

## 4. 连续实施阶段与门禁

按以下顺序执行（允许必要的细化，不得跳过主验收）：

### Phase 0 — Baseline & Contract
- 梳理源代码、已有运行库/Manifest、AI Pipeline、Quarto HTML/PDF 分支、前端可参考资产。
- 写目标 API/DTO、错误码、存储边界、威胁模型；检查 Git 和测试基线；确定部署模式（默认本地安全单用户）。
- 门禁：来源/接口清单、测试基线、依赖变化清楚，未修改真实库。

### Phase 1 — Repository & Artifact（合并 DB-P0/P1/P2 的最小必要范围）
- 封装原生 SQLite 只读查询，保留原 `run_db.py` 旧接口；Report DTO、分页/过滤、JSON 解析、未知模块兼容。
- Artifact Resolver 安全扫描 Manifest、校验允许目录、符号链接/路径穿越、字节数/哈希，JSONL 流式解析；缺失目录/坏 Manifest 降级。
- 建立 report -> module -> evidence 的索引/查询接口，不复制全部科研统计表进 DB。
- 门禁：临时 SQLite + 多种恶意路径 fixture + 报告历史只读检查通过。

### Phase 2 — Evidence & Scientific Agent（Agent P0/P1/P2/P3 可按难度递进）
- 先实现 `rna.results.deg` 证据包，含真实阈值、raw P vs padj、上/下调、Top 表、火山图；明确图像与报告图的参数一致性。
- 接入现有 AI Engine 的完整配置，构建图片能力检测/纯文本降级；结构化三层输出（观察/解释/假设和限制）；数值引用校验，不合格拒绝正式回填。
- 扩展 `samples/PCA`、`heatmap/HVG`、`enrichment`、`fastp/screen/qualimap/star`，一个科学模块/比较组为调用单元，控制成本与缓存。
- 仅在证据不足并且真实需求需要时支持最多 2~3 轮受控工具；Ark tools 若不可验证则保持关闭并留 BLOCKED。
- 门禁：DEG + 至少多模块 mock 图文解释测试、隐私与统计一致性通过。

### Phase 3 — Persistence & Lifecycle（DB-P3/P4）
- 先完成 Schema 版本、备份、迁移演练、失败恢复，再新增 `interpretations`、按需 `conversation_sessions/messages` 等表；SQLite FK/索引/事务有效。
- 支持正式 interpretation 与 chat draft 分离；同一 run/module/comparison/evidence 支持多个版本；去重缓存并避免并发重复调用。
- 处理预渲染 `execution_id` 迟绑定 `run_id`；历史报告使用已有 run_id。
- 门禁：迁移备份+旧记录完整性+多版本+崩溃/重试+关联正确性测试通过。

### Phase 4 — FastAPI & SSE（DB-P5）
- 独立可复用 API 层，Pydantic DTO，报告、模块、文件、Manifest、解读、会话等端点（URL 详见配套实施文档）。
- SSE 事件按协议发送 `started/evidence_ready/token/tool_status/validated/completed/error/cancelled`；断线清理、超时取消、幂等键与限流。
- 默认 loopback only；外部访问走受控鉴权，明确当前用户项目授权。严格禁止路径输入和任意文件代理。
- 门禁：API 合同、鉴权拒绝、越权、路径穿越、SSE 异常恢复全通过。

### Phase 5 — React Workspace（完整 v1 页面）
- 使用 React/TypeScript/Vite/Tailwind 和最小必要依赖；参考科研寻宝鼠 `frontend-style-spec.md` 的 tokens、focus、i18n、dark mode 规则与聊天模式。
- 页面：报告库、报告详情、三栏解读工作台、Evidence/Provenance；三栏左模块树/中图表或 PDF/右 Agent 可折叠、可拖动、响应式。
- 具备 loading/empty/failed/missing/no-evidence/no-key 等真实状态；不是假数据界面；可访问性与暗色模式。
- 门禁：TS typecheck、前端 build、后端实数数据 E2E、流式对话与版本切换、截图检查桌面/移动端通过。

### Phase 6 — Quarto & Full E2E（Agent P1-C/P4）
- HTML 与 PDF 对应 QMD 模板中可选地插入模块级解读，必要时提取共享 include；旧 AI.qmd 不重复正文。
- 关闭 AI、不提供 Key、某模块失败、图片失败、部分产物缺失均不阻断原报告；正式结果仍可审计。
- 检验图表参数一致性、原始报告不可变、Manifest hash、report/AI evidence 关联。
- 门禁：真实 Quarto/模型/浏览器可用时实际端到端；不可用时 Mock + BLOCKED 明示，不能判定真实 E2E PASS。

## 5. 推荐 API 契约（以实际架构和文档为准）

- `GET /api/v1/reports?project_id=&status=&limit=&cursor=`
- `GET /api/v1/reports/{run_id}`
- `GET /api/v1/reports/{run_id}/modules`
- `GET /api/v1/reports/{run_id}/artifacts`
- `GET /api/v1/reports/{run_id}/artifacts/{artifact_id}/content`
- `GET /api/v1/reports/{run_id}/modules/{module_id}/evidence`
- `GET /api/v1/reports/{run_id}/interpretations`
- `POST /api/v1/reports/{run_id}/interpretations`
- `GET /api/v1/interpretations/{interpretation_id}`
- `POST /api/v1/conversations`
- `GET /api/v1/conversations/{session_id}`
- `POST /api/v1/conversations/{session_id}/messages`
- `GET /api/v1/operations/{operation_id}/events`（SSE）

设计 OpenAPI、稳定错误码、任务终态、重试行为、操作取消、run/module/project 授权边界；不要求路径/源文件通过 HTTP 入参。

## 6. 严格验收目标

必须证明：

1. 既有 `runs.db` 不被破坏，旧记录照常查询；临时数据库迁移能备份恢复。
2. 审计快照所见失效历史目录被准确标记，不影响历史列表；不要求旧目录“自动修复”。
3. 真实统计与模型解释分层、证据引用可回溯、模型不能伪造已验证数值。
4. PNG/SVG/HTML/PDF 真实产物由安全 Resolver 提供；恶意 artifact/路径/伪造 Manifest 拒绝。
5. 真实报告列表→模块→证据→Mock 解读→入库→重新打开工作台→会话追问闭环贯通。
6. Quarto HTML/PDF 在 AI on/off 都可生成；旧 CLI 回归通过。
7. SSE 流式正常、取消/超时/断线有终态；模型 Key 不泄漏到浏览器。
8. `npx tsc --noEmit` / 前端 build / Python tests / API tests / 浏览器 E2E 按环境真实运行并记录命令与结果。
9. 真正 CygnusX BioOps 集成在缺少其仓库权限时只能提供鉴权 API 合同、示例客户端和 contract tests，不得宣称生产集成成功。

每阶段输出 PASS/FAIL/BLOCKED/UNVERIFIED 及证据。安全/数据准确性相关 FAIL 属于停止门禁，不能绕过。环境 BLOCKED 允许继续开发与 mock 测试，但最终 `CONDITIONAL GO`，不能升级为完整 PASS。

## 7. 最终交付文件（必须）

在仓库内生成：

- `docs/architecture/bioreport-workspace-v1-architecture.md`（Mermaid LR 总体图、ER 图、sequenceDiagram）。
- `docs/architecture/bioreport-workspace-v1-api-contract.md`（OpenAPI、DTO、SSE、错误/鉴权/数据流）。
- `docs/architecture/bioreport-workspace-v1-database-migrations.md`（备份、Schema 版本、向后兼容、回滚）。
- `docs/architecture/bioreport-workspace-v1-security.md`（可信根、跨项目权限、模型隐私、Prompt 注入）。
- `docs/architecture/bioreport-workspace-v1-ui-spec.md`（参考仓库映射、Design Tokens、响应式、交互态）。
- `docs/architecture/bioreport-workspace-v1-runtime-acceptance.md`（每阶段真实命令、日志摘要、截图/产物、PASS/FAIL/BLOCKED）。
- `docs/architecture/bioreport-workspace-v1-implementation.md`（最终文件清单、偏差、遗留问题、GO 判定）。
- Python/TS 单元与集成测试，浏览器自动化用例及 fixture；示例运行方法、环境变量模板（不含真实 Key）。

最终回答：已实现/未实现矩阵、所有阶段门禁、实际改动文件、迁移是否执行、真实测试命令与统计、外部依赖/环境阻塞、接口使用示例、后续建议。**在未具备生产级鉴权前，不许暴露公网端口**。不要因为任务要求“一步到位”而伪造不存在的集成或跳过核验。

## 8. 具体执行指令

现在开始实施。首先核查代码与附件差异，随后按 Phase 0→6 连续执行、完成所有可以在当前环境运行的测试。对未安装依赖/不可用的外部服务，先用本地 fixture 和 mock 前进，再单独报告真实验收缺口。不要只回复方案，不要仅搭前端静态页，不要只在文档中声称完成。全部完成后按交付清单总结并停止，不自动提交/推送，也不修改参考仓库。
