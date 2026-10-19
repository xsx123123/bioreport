# BioReport 开发计划（TODO）

## v3 规划

### AI 逐结果解读 Agent 框架（先搭骨架）

**现状**：当前结果卡片已经按结果 ID 生成，PDF 也支持“首次渲染图表 → 视觉 AI → 二次回填”的路径，但提示词仍集中在 `pipeline.py`，不同模块共用同一套角色描述，输出主要依赖自由文本 Markdown。

**目标**：将 AI 解读拆成可版本化、可审计、可替换的 Agent 层，不改变现有报告交付接口。

**框架边界**：

1. `EvidenceAdapter`：为每个结果生成统一证据包，包含 `result_id`、模块类型、比较组、统计摘要、表格预览、图像引用、来源 artifact 和 evidence hash。
2. `PromptRegistry`：按 `assay / module / result_kind` 选择 Prompt，分离角色安全边界、模块读图规则、证据约束、输出格式和语言要求；记录 prompt version。
3. `InterpretationAgent`：负责模型调用、超时、重试、取消、fallback 和 token/cost 记录；不修改原始证据。
4. `OutputValidator`：校验结构化输出、证据引用、数值一致性、限制说明和空响应；失败时生成可见的回退卡片，禁止静默空白。
5. `RendererAdapter`：把通过校验的结果绑定到 HTML/PDF 对应结果槽位；PDF 保留两阶段视觉回填协议。

**第一阶段验收**：先落地接口和版本字段，不改变现有 Prompt 内容；每个结果都能记录 `result_id`、`evidence_hash`、`prompt_version`、模型、参数、响应状态和最终卡片内容。后续再逐模块重写 fastp/QC、样本关系、DEG、富集的专家提示词。

### Web 工作台大版本升级：BioReport Workspace v2

**现状**：仓库已有 Workspace v1（`bioreport/api.py`、`bioreport/api_server.py` 和
`frontend/` React 页面），可以浏览历史运行、模块证据、图表 artifact 和模块级 AI
解读，但主入口仍是报告列表 + 三栏详情；报告生成、证据浏览、AI 解读和交付管理之间
缺少统一的工作流上下文。当前静态 HTML/PDF 报告仍是主要交付形态，Web 页面尚未成为
项目分析的主工作台。

**目标（下一个大版本）**：将 Web 版 BioReport 设计为面向科研分析的项目工作台，
以“项目 → 运行 → 分析模块 → 结果证据 → AI 解读 → 交付版本”为主导航和数据模型。
Web 页面应能承载完整工作流，同时继续支持导出静态 HTML/PDF。

**产品形态**：

1. **项目总览**：项目元数据、最近运行、运行状态、输入完整性、报告版本、警告和待处理任务集中展示；支持按项目、 assay、日期和运行状态筛选。
2. **运行时间线**：按 QC、比对、定量、样本关系、DEG、富集和交付阶段显示任务进度、日志、失败原因和可重试操作；长任务使用 SSE/轮询统一呈现。
3. **结果工作区**：左侧模块树，中间证据画布，右侧 AI 解读面板。表格、图表、统计值、输入文件和 provenance 必须保持同一模块上下文；比较组和 UP/DOWN 方向切换不能丢失当前证据。
4. **逐结果 AI**：每一张表、每一幅图和每个比较组结果拥有独立 interpretation 记录，显示 evidence hash、模型、提示词版本、生成时间、验证状态和历史版本；支持重新解读、接受/标记需复核、导出到 HTML/PDF 原位卡片。
5. **证据联动**：从图表点击样本、基因、通路或比较组后，可跳转到对应原始表格、输入文件和统计口径；禁止把没有 provenance 的自由文本伪装成证据。
6. **交付中心**：查看 HTML/PDF、下载 supplementary artifacts、比较两个报告版本、校验 manifest 和 SHA-256；生成新交付版本时保留旧版本，不覆盖历史文件。
7. **任务与权限**：项目级访问控制、可信报告根目录、API token、审计日志和明确的错误/空状态；默认 loopback，公网部署必须经过反向代理和项目白名单。
8. **响应式与可访问性**：桌面端支持可调整面板，窄屏切换为模块抽屉 + 证据/AI 标签页；键盘导航、焦点状态、表格语义、颜色之外的状态表达和 reduced-motion 必须覆盖主要流程。

**工程拆分**：

1. 将 Workspace API 稳定为 versioned contract：projects、runs、modules、evidence、interpretations、artifacts、operations、provenance；补充 OpenAPI schema、错误码和分页约定。
2. 将前端拆成 `ProjectOverview`、`RunTimeline`、`ModuleNavigator`、`EvidenceCanvas`、`InterpretationPanel`、`DeliveryCenter`，共享查询缓存、加载/空/错误状态和权限上下文。
3. 把模块证据统一为可序列化的 `EvidenceBlock`（table、figure、metric、source、hash、comparison），RNA-seq 先迁移，其他组学沿同一契约接入。
4. AI 请求改为异步 operation，支持取消、重试、幂等键、模型/提示词配置快照和 token/cost 记录；失败只能标记当前结果，不得污染原始证据或历史报告。
5. 增加 HTML/PDF 原位回填协议：Web 中的 interpretation 必须能通过 module/comparison/evidence hash 精确定位到静态报告卡片。

**验收标准**：

- 从项目总览打开一次 RNA-seq 运行，可依次查看 fastp、污染筛查、QualiMap、STAR、PCA、矩阵、热图、DEG 和富集的证据与逐结果 AI 解读。
- 任意解读都能回溯到唯一 evidence hash、输入 artifact、模型和提示词版本；重新解读生成新版本，不覆盖旧版本。
- 失败运行、缺失 artifact、无 AI key、空表和权限拒绝均有可操作的页面状态；不存在静默空白。
- 同一运行可下载经过 manifest 校验的 HTML/PDF 和 supplementary 文件，并能在 Web 中比较两个交付版本。
- 覆盖 API contract、权限、操作流、证据完整性、AI 幂等/取消、响应式主要视图和浏览器端无障碍回归测试。

**实施顺序**：先冻结 API/EvidenceBlock 契约，再做运行与证据工作区，随后迁移逐结果 AI 和交付中心，最后补权限、响应式、可访问性和浏览器验收。每阶段保留 Workspace v1 回退路径。

### AI 管线去 RNA 化：按组学分派的数据整合契约

**现状**：`bioreport/pipeline.py` 中 AI 管线的整合步骤写死 RNA——直接 import
`bioreport.utils.consolidate_rna_seq_data`，且中间文件名硬编码为
`consolidated_rna_seq_data.txt` / `consolidated_rna_seq_report.md`。任何非 RNA
组学包无法复用 AI 解读管线，核心引擎与 RNA 实现存在隐性耦合。

**目标（v3 实现）**：

1. 在组学包契约（`OmicsPackage` / `Registry` 注册接口）上增加
   `consolidate()` 方法，由各组学包提供自己的数据整合器：
   - 输入：解析后的 `input_files`、AI 配置（限额、prompt 等）、输出目录
   - 输出：整合后的文本 + 解读 Markdown 的目标路径约定（纳入契约，不再硬编码文件名）
2. `pipeline.py` 按当前报告选择的 assay 从注册表分派到对应整合器，
   引擎本身不 import 任何组学实现（保持现有 lazy-load 风格）。
3. `templates/shared/AI.qmd` 中的 include 路径改为由组合器按契约注入，
   或约定组学包注册时声明解读产物的 staged 路径。
4. 迁移 `consolidate_rna_seq_data.py` 至 `omics/rna/` 包内，
   `bioreport/utils/` 只保留真正组学无关的工具。

**验收**：新增一个最小非 RNA 组学包即可走通「整合 → 模型解读 → 渲染前就绪」
全流程；RNA 行为与现有输出保持一致（回归 `tests/test_modules.py` 中
AI include 相关用例）。

**暂不处理的原因**：当前仅内置 RNA-seq 模块，硬编码不影响任何现有功能；
先完成共享页迁移与 CLI 身份独立（见 git 历史），契约设计留待 v3 与
多组学模块扩展一并落地。

---

_维护约定：完成事项及时打勾或移除；每项需注明现状、目标与验收方式。_
