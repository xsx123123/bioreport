# BioReport 数据库、报告持久化与 AI Interpretation Workspace 架构审计

> 审计日期：2026-10-17  
> 审计方式：源码静态审计 + SQLite mode=ro 只读检查  
> 本轮未修改源码、配置、数据库、报告文件或 Git 状态。

状态标记：

- VERIFIED：源码或实际运行数据已确认
- INFERRED：由已验证事实推导
- UNVERIFIED：当前环境无法确认
- BLOCKED：需要外部系统或用户提供信息

## 1. Executive Summary

BioReport 当前使用一个本地 SQLite 运行记录库，但它不是完整的报告数据库，也不是 Report Repository。

数据库只保存每次 CLI 运行的摘要：自增运行 ID、project_id、时间、BioReport / pipeline 版本、布局和输出格式、模块列表、配置路径、输出目录、状态以及输入文件 checksum JSON。

报告正文、HTML、PDF、图表、模块证据、Manifest 和 AI Markdown 均保存在文件系统中，由 JSON Manifest 和 JSONL 语义块记录间接关联。

实际数据库检查结果：

- 文件：/home/zj/.bioreport/runs.db
- 类型：SQLite
- 业务表：runs
- 业务记录：49 条
- success：48 条
- failed：1 条
- 项目：3 个
- 输出格式：HTML 16 条、PDF 33 条
- 外键：无
- 业务索引：无
- PRAGMA user_version：0
- 数据库迁移机制：未发现

结论：**CONDITIONAL GO**。

可以在当前数据库和 Manifest 之上建设 Workspace，但不能直接把当前 runs 表当作完整报告数据源。最小可行路径是：

1. 复用 runs 作为历史运行索引；
2. 通过 output_dir 读取报告 Manifest；
3. 增加只读 Report Service / Artifact Resolver；
4. 再增加独立的 Interpretation 表；
5. 暂不迁移 PostgreSQL；
6. 暂不引入 FastAPI、Agent 或聊天系统，直到查询服务契约稳定。

## 2. Database Technology Stack

### 2.1 数据库类型

VERIFIED。源码证据：

- bioreport/utils/run_db.py:12 导入 sqlite3；
- bioreport/utils/run_db.py:17-33 使用 SQLite CREATE TABLE IF NOT EXISTS；
- bioreport/utils/run_db.py:56 使用 sqlite3.connect()。

数据库默认路径由 bioreport/utils/run_db.py:36-41 决定：

~~~text
BIOREPORT_DB
  └─ 已设置：使用环境变量指定路径
  └─ 未设置：Path.home() / ".bioreport" / "runs.db"
~~~

因此：

- 支持自定义数据库路径：VERIFIED
- 默认位于用户目录：VERIFIED
- 不使用 SQLAlchemy、DuckDB 或 Peewee：VERIFIED
- 使用原生 SQL：VERIFIED

### 2.2 初始化与连接管理

record_run() 每次写入时依次创建父目录、建立连接、执行 CREATE TABLE IF NOT EXISTS、插入记录、提交并关闭连接。

证据：bioreport/utils/run_db.py:44-85。

查询函数：

- fetch_runs()：bioreport/utils/run_db.py:88-104
- search_runs()：bioreport/utils/run_db.py:107-151

连接关闭使用 finally，但没有发现显式的 busy timeout、WAL 配置、写入重试、连接池、线程隔离或备份恢复 API。

### 2.3 数据库架构图

~~~mermaid
flowchart LR
    CLI[bioreport CLI] --> RunDB[run_db.py]
    RunDB --> SQLite[(~/.bioreport/runs.db)]
    CLI --> FS[报告输出目录]
    FS --> Manifests[Report/Input/Artifact/Reproduction Manifest]
    FS --> Reports[HTML/PDF/日志/配置备份]
    SQLite -.摘要索引.-> FS
~~~

## 3. Schema & Entity Relationships

### 3.1 真实业务表

当前只有一张业务表：

~~~sql
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    run_at TEXT NOT NULL,
    engine_version TEXT,
    pipeline_version TEXT,
    layout TEXT,
    output_format TEXT,
    modules TEXT,
    config_path TEXT,
    output_dir TEXT,
    status TEXT NOT NULL,
    input_checksums TEXT,
    created_at TEXT NOT NULL
)
~~~

证据：bioreport/utils/run_db.py:17-33。

| 字段 | 类型 | Nullable | 默认值 | 说明 |
|---|---|---:|---|---|
| id | INTEGER | 是 | 自增 | 运行记录主键 |
| project_id | TEXT | 否 | 无 | 项目 ID |
| run_at | TEXT | 否 | 无 | provenance 生成时间 |
| engine_version | TEXT | 是 | 无 | BioReport 版本 |
| pipeline_version | TEXT | 是 | 无 | 分析流程版本 |
| layout | TEXT | 是 | 无 | 当前实际为 single |
| output_format | TEXT | 是 | 无 | JSON 字符串，如 ["pdf"] |
| modules | TEXT | 是 | 无 | JSON 字符串形式的模块列表 |
| config_path | TEXT | 是 | 无 | 配置路径 |
| output_dir | TEXT | 是 | 无 | 报告输出目录 |
| status | TEXT | 否 | 无 | 当前代码写入 success / failed |
| input_checksums | TEXT | 是 | 无 | JSON 字符串 |
| created_at | TEXT | 否 | 无 | 数据库写入时间 |

实际检查：

- 外键：无；
- Unique constraint：无；
- 业务索引：无；
- updated_at：无；
- report_id：无；
- run_id：没有独立字段，id 只能作为运行记录 ID；
- Schema 版本字段：无，user_version=0。

### 3.2 ER 图

由于当前没有外键，不能虚构实体关系：

~~~mermaid
erDiagram
    RUNS {
        INTEGER id PK
        TEXT project_id
        TEXT run_at
        TEXT engine_version
        TEXT pipeline_version
        TEXT layout
        TEXT output_format
        TEXT modules
        TEXT config_path
        TEXT output_dir
        TEXT status
        TEXT input_checksums
        TEXT created_at
    }
    RUNS }o..o FILESYSTEM : "通过 output_dir 字符串间接关联"
    FILESYSTEM }o..o MANIFEST : "文件路径间接关联"
~~~

FILESYSTEM 和 MANIFEST 不是当前数据库表，只表示外部持久化对象。

### 3.3 实际数据库记录

使用 SQLite URI mode=ro 读取，没有执行 INSERT、UPDATE、DELETE 或迁移。

当前库：

- 49 条总记录；
- 48 条 success；
- 1 条 failed；
- 最早记录：2026-10-15T20:17:22+08:00；
- 最晚记录：2026-10-17T11:58:27+08:00；
- 10 条记录的当前 output_dir 不存在或不可访问；
- 39 条记录的输出目录当前存在。

这说明历史记录可能包含已移动、清理或当前环境不可访问的输出目录。

## 4. Report Lifecycle

### 4.1 实际调用顺序

~~~mermaid
flowchart TD
    A[bioreport run] --> B[load_config]
    B --> C[selected_modules]
    C --> D[创建临时模板目录]
    D --> E[build_provenance]
    E --> F[check_input_files]
    F --> G[check_quarto_env]
    G --> H[render_templates]
    H --> I{dry-run?}
    I -- yes --> Z[结束，不写运行记录]
    I -- no --> J{包含 ai 模块?}
    J -- yes --> K[run_ai_pipeline]
    J -- no --> L[跳过 AI]
    K --> M[render_report / Quarto]
    L --> M
    M --> N{Quarto 成功?}
    N -- no --> O[record_run failed]
    N -- yes --> P[backup_config]
    P --> Q[write_delivery_manifests]
    Q --> R{Manifest 校验成功?}
    R -- no --> O
    R -- yes --> S[record_run success]
~~~

证据：bioreport/cli.py:480-518、bioreport/cli.py:536-567。

### 4.2 数据库写入时机

VERIFIED：数据库不是在任务开始时写入，而是在以下时机写入：

- Quarto 失败后：failed；
- Manifest 校验失败后：failed；
- 报告和 Manifest 全部完成后：success。

没有发现 pending、running、cancelled 或中途进度更新状态。

### 4.3 AI 失败处理

存在一个一致性风险：

~~~python
if "ai" in selected:
    run_ai_pipeline(...)
try:
    render_report(...)
except ...:
    _record_run("failed")
~~~

证据：bioreport/cli.py:549-556。

如果 run_ai_pipeline() 在进入 render_report() 前抛出未处理异常，可能不会进入 Quarto 失败捕获块，因此可能出现 AI 失败但没有失败运行记录的情况。是否存在外层统一异常处理，需要完整 CLI 运行验证，当前标为 UNVERIFIED。

### 4.4 报告生命周期风险

| 风险 | 结论 |
|---|---|
| 报告生成成功但数据库写入失败 | VERIFIED，数据库失败只告警，不阻断报告 |
| 数据库记录存在但报告文件被删除 | VERIFIED，无文件外键或存在性约束 |
| AI 预渲染失败没有失败记录 | VERIFIED，当前异常边界存在缺口 |
| 重复执行覆盖历史报告 | VERIFIED，没有幂等键 |
| 同一项目多次运行 | VERIFIED，允许多条记录 |
| 自动清理 | 未发现，UNVERIFIED |
| 删除记录同步删除文件 | 未实现，VERIFIED |
| 数据库删除接口 | 未发现 |
| 数据库迁移机制 | 未发现 |

## 5. Persistence & Artifact Management

数据库不保存报告文件，只保存 config_path、output_dir 和 output_format。HTML、PDF、SVG、JSON、日志和 Markdown 都在文件系统。

bioreport/config.py:328-330 使用以下命名：

~~~text
<project_id>_report.html
<project_id>_report.pdf
~~~

Manifest 由 bioreport/utils/provenance.py:112-163 生成：

- report-manifest.json
- input-manifest.json
- artifact-manifest.json
- reproduction-manifest.json

Manifest 记录 artifact 名称、role、path、SHA-256 和 size。输入目录由 provenance.py:94-109 递归扫描。

~~~mermaid
flowchart LR
    R[runs.id] --> P[project_id]
    R --> O[output_dir]
    O --> H[project_report.html]
    O --> PDF[project_report.pdf]
    O --> RM[report-manifest.json]
    O --> IM[input-manifest.json]
    O --> AM[artifact-manifest.json]
    O --> REC[report-blocks-pdf.jsonl]
    O --> CFG[run_config_backup.json]
    RM --> H
    AM --> PDF
    AM --> SVG[supplementary SVG]
    IM --> INPUT[原始输入和结果文件]
    REC --> FB[FigureBlock/TableBlock 记录]
~~~

这是文件和 JSON 的间接关系，不是数据库外键关系。

| 能力 | 状态 |
|---|---|
| 通过 runs.id 查询运行记录 | SUPPORTED |
| 通过 output_dir 找报告目录 | SUPPORTED |
| 推导 HTML/PDF 文件名 | SUPPORTED |
| 通过数据库直接查询 artifact | MISSING |
| 通过 Manifest 查询 artifact | SUPPORTED |
| 验证文件 SHA-256 | SUPPORTED |
| 文件移动后自动修复路径 | MISSING |
| 文件恢复 | MISSING |
| 通过 report_id 查询全部产物 | MISSING |
| 通过 project_id 查询历史运行 | SUPPORTED |

## 6. Scientific Evidence Integration

### 6.1 Module Registry

Registry 定义位于 bioreport/registry.py:7-19，包含 id、qmd、title、category、required_inputs、parent、setup_qmd 等字段。

RNA 实际 module_id 位于 omics/rna/modules.py:9-23：

~~~text
rna.index
rna.workflow
rna.qc
rna.qc.fastp
rna.qc.screen
rna.qc.qualimap
rna.qc.star
rna.results
rna.results.samples
rna.results.matrix
rna.results.heatmap
rna.results.deg
rna.results.enrichment
~~~

### 6.2 数据库是否保存模块

保存，但仅作为 JSON 文本：

~~~text
runs.modules = '["rna.index", "rna.workflow", ...]'
~~~

可以读取启用模块列表和顺序，但不能支持 report_id + module_id 的关系查询、模块执行状态、模块错误信息或模块结果版本。

### 6.3 FigureBlock / TableBlock

模型定义：

- bioreport/report/model.py:42-60
- bioreport/report/model.py:62-71

记录逻辑：

- bioreport/report/recording.py:8-20
- bioreport/utils/render_output.py:26-70
- bioreport/utils/render_output.py:169-203

当前情况：

- FigureBlock.id 存在；
- TableBlock.id 存在；
- content 可携带 evidence；
- module_id 不是模型必填字段；
- 记录只在 Quarto 执行期间产生；
- 数据库没有存储这些 block；
- HTML 没有与 PDF 同等级别的最终 block manifest 交付保证。

| 目标 | 状态 |
|---|---|
| 读取模块列表 | SUPPORTED |
| 读取模块 QMD | SUPPORTED |
| 查询 FigureBlock | PARTIAL，需要读取 JSONL |
| 查询 TableBlock | PARTIAL，需要读取 JSONL |
| 通过数据库查询图表 | MISSING |
| 通过 Manifest 查询图表 | PARTIAL |
| 从历史报告重建 Evidence Package | PARTIAL，原始输入仍需存在 |
| 只有 PDF 时恢复结构化证据 | UNVERIFIED，不建议作为可靠路径 |
| 原始输入删除后重新解读 | MISSING，除非证据已缓存 |

~~~mermaid
flowchart LR
    RUN[Run Record] --> MODULES[modules JSON]
    RUN --> OUT[output_dir]
    OUT --> MAN[Manifests]
    MAN --> ART[Artifacts]
    OUT --> BLOCKS[FigureBlock/TableBlock JSONL]
    BLOCKS --> EVIDENCE[Evidence metadata]
    EVIDENCE --> SOURCE[Input SHA256 / result files]
    EVIDENCE --> AI[Interpretation record]
~~~

## 7. Historical Report Management

| 能力 | 状态 | 依据 |
|---|---|---|
| 查询全部历史运行 | SUPPORTED | fetch_runs() / search_runs() |
| 按项目筛选 | SUPPORTED | search_runs(project=...) |
| 按日期筛选 | SUPPORTED | search_runs(since/until=...) |
| 按状态筛选 | SUPPORTED | search_runs(status=...) |
| 按分析类型筛选 | PARTIAL | 需要解析 modules JSON |
| 区分 HTML/PDF | SUPPORTED | output_format |
| 按稳定 report_id 查询 | MISSING | 当前只有自增 id |
| 按运行 ID 查询详情 | PARTIAL | 没有单行 detail API |
| 分页 | PARTIAL | 只有 LIMIT，无 offset/cursor |
| 排序 | SUPPORTED | 固定按 id DESC |
| 关键词搜索 | PARTIAL | 仅 project_id LIKE |
| 项目多版本 | SUPPORTED | 多条 runs 记录 |
| 报告预览地址 | PARTIAL | 只能组合输出目录和文件名 |
| 报告重生成 | MISSING | 无 Service/API |
| 报告删除/归档 | MISSING | 未发现 |
| 报告文件一致性 | PARTIAL | Manifest 可校验，数据库不自动校验 |
| 历史记录完整性 | UNVERIFIED | 当前库只代表本机历史 |
| Schema 兼容 | MISSING | 无迁移和版本机制 |

现有 bioreport runs 和 bioreport/utils/run_browser.py 只提供终端运行记录查看，不是报告详情 API。

## 8. Interpretation Agent Persistence

当前 AI 输出文件：

~~~text
template_dir/data/ai_reports/AI_Interpretation_Report.md
template_dir/data/consolidated_rna_seq_report.md
~~~

证据：

- bioreport/pipeline.py:61-79
- bioreport/utils/consolidate_rna_seq_data.py:384-391
- templates/shared/AI.qmd:8-13

当前数据库没有保存 provider、model、prompt version、token usage、cost、evidence hash、validation status、tool calls 或 interpretation version。

AIInterpreter 内部存在 usage 和 cost 计算：

- bioreport/ai/engine.py:250-258
- bioreport/ai/engine.py:335-354

但这些信息没有写入数据库或 Manifest。

### 8.1 建议的 Interpretation 表

建议新增独立表，不修改 runs 表：

~~~sql
interpretations (
    interpretation_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    module_id TEXT NOT NULL,
    comparison TEXT,
    evidence_hash TEXT NOT NULL,
    content_path TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_version TEXT,
    validation_status TEXT NOT NULL,
    token_usage_json TEXT,
    cost REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
)
~~~

这是目标设计，不是当前真实 Schema。数据库保存索引、状态和查询字段；Markdown 保存于文件系统；Manifest 保存完整 artifact hash；旧 interpretation 不覆盖。

~~~mermaid
erDiagram
    RUNS ||--o{ INTERPRETATIONS : has
    INTERPRETATIONS {
        INTEGER interpretation_id PK
        INTEGER run_id FK
        TEXT module_id
        TEXT comparison
        TEXT evidence_hash
        TEXT content_path
        TEXT output_hash
        TEXT provider
        TEXT model
        TEXT prompt_version
        TEXT validation_status
        TEXT token_usage_json
        REAL cost
        TEXT created_at
    }
~~~

## 9. Conversation Persistence

当前未发现 Session、Conversation、Message 表，或 Chat Repository，因此交互式问答持久化能力为 MISSING。

未来建议单独设计 conversation_sessions 和 conversation_messages，保存 run_id、module_id、evidence_hash、消息角色、内容 hash、模型和 token usage。不要把长对话正文和全部科学证据重复塞进 runs 表。

报告删除策略应采用：运行记录保留，会话标记 archived，内容文件按 Artifact Policy 管理；不允许仅凭用户传入的 report_id 直接访问文件。

## 10. API & Workspace Feasibility

当前没有发现 FastAPI、Flask、Starlette、Uvicorn、API route、Report Repository、数据库 Service Layer 或文件预览/下载接口。

docs/UPDATE.md 中的 FastAPI 片段是设计示例，不是现有实现。

~~~mermaid
flowchart LR
    CLI[BioReport CLI] --> Service[Report Query Service]
    API[未来 FastAPI] --> Service
    Service --> RunRepo[Run Repository]
    Service --> Resolver[Artifact Resolver]
    Service --> Evidence[Evidence Builder]
    RunRepo --> SQLite[(Existing SQLite runs)]
    Resolver --> FS[报告输出目录]
    FS --> Manifest[JSON Manifests]
    Evidence --> Agent[Interpretation Agent]
    Agent --> IntRepo[Interpretation Repository]
    IntRepo --> IntDB[(Interpretation tables)]
    IntRepo --> Files[Interpretation Markdown]
    BioOps[CygnusX BioOps] --> API
~~~

建议先实现纯 Python 查询 Service，再由 CLI 和未来 API 共用，之后增加 FastAPI 只读接口，最后接入 Workspace。CygnusX BioOps 只通过 API/Service 集成，不直接操作 SQLite 文件。

建议的未来 API：

~~~text
GET /reports
GET /reports/{run_id}
GET /reports/{run_id}/artifacts
GET /reports/{run_id}/modules
GET /reports/{run_id}/evidence
GET /reports/{run_id}/interpretations
POST /reports/{run_id}/interpretations
GET /interpretations/{interpretation_id}
~~~

第一版本应先做只读报告列表、运行详情、文件存在性、Manifest、模块和 block evidence 查询。

## 11. Database Reliability

当前 SQLite 配置：

- journal mode：delete；
- WAL：未启用；
- busy timeout：未设置；
- 索引：无；
- 事务：单次 INSERT 后 commit；
- 连接：每次函数调用新建并关闭；
- 写入失败重试：无；
- 备份机制：未发现；
- 恢复机制：未发现；
- Schema migration：未发现。

当前低并发 CLI 使用 SQLite 足够。在多用户并发写入、FastAPI 多 worker、Celery、跨主机共享、高并发 interpretation/chat 写入或高可用备份需求出现后，才重新评估 PostgreSQL。

## 12. Security & Compatibility

当前数据库可能泄露配置路径、输出目录、project_id、输入 checksum、模块信息。Workspace 必须不直接暴露 SQLite 文件和绝对路径，使用逻辑 artifact ID，校验项目权限和 run_id 归属，防止路径穿越，并对下载文件执行 resolver 校验。

| 等级 | 风险 | 建议 |
|---|---|---|
| Critical | 通过 output_dir 访问越权文件 | 增加 Artifact Resolver 和根目录限制 |
| Critical | AI 解读与历史报告输入不一致 | 绑定 run_id/evidence_hash |
| High | AI 失败不一定生成 failed 运行记录 | 统一包裹 AI 阶段异常 |
| High | 无索引导致历史量增长后查询变慢 | 先增加查询测试，再加索引 |
| High | 文件移动导致 output_dir 失效 | 使用 artifact manifest 和可配置根目录 |
| Medium | 无 Schema 版本/迁移机制 | 新表前建立 schema_version |
| Medium | JSON 字段难以 SQL 查询 | Service 层解析，必要时增加派生索引 |
| Medium | 多进程写入锁竞争 | 先按部署负载验证 timeout/WAL |
| Low | 运行状态只有 success/failed | Workspace 首版可沿用，后续扩展状态机 |
| Low | 旧记录无 report_id | 以 runs.id 兼容，后续引入 report identity |

## 13. Recommended Architecture

~~~mermaid
flowchart LR
    Core[BioReport Core / CLI] --> RunRepo[Run Repository]
    RunRepo --> SQLite[(Existing SQLite runs)]
    Core --> Provenance[Provenance Builder]
    Provenance --> Manifests[Report/Input/Artifact Manifests]
    Manifests --> Artifacts[Artifact Resolver]
    Artifacts --> Evidence[Module Evidence Builder]
    Evidence --> Agent[Interpretation Agent]
    Agent --> IntRepo[Interpretation Repository]
    IntRepo --> IntDB[(Interpretation tables)]
    IntRepo --> IntFiles[Markdown + JSON evidence files]
    Workspace[AI Interpretation Workspace] --> API[FastAPI Read/Write API]
    API --> Service[Shared Report Service Layer]
    Service --> RunRepo
    Service --> Artifacts
    Service --> Evidence
    Service --> IntRepo
    BioOps[CygnusX BioOps] --> API
~~~

保留 runs 表、provenance、四类 Manifest、FigureBlock/TableBlock、Registry 和文件系统报告产物。新增 ReportQueryService、ArtifactResolver、EvidenceBuilder、interpretations 表、interpretation manifest、可选 Conversation 表和 API 层。

不建议新增 ORM、LangGraph、MCP、独立 Agent 进程、PostgreSQL，或重构现有报告生成流程。

## 14. Minimal Implementation Plan

### DB-P0：架构确认与只读 Repository

封装 runs 查询，解析 JSON 字段，检查输出目录，加载 Manifest，返回统一 Report DTO。建议新增：

~~~text
bioreport/report_service.py
bioreport/artifacts.py
~~~

不修改现有 runs 表。验收：支持 run_id、project_id、日期和状态查询；不暴露绝对敏感路径；覆盖缺失目录和损坏 Manifest。

### DB-P1：历史报告列表与详情

实现历史运行列表、项目筛选、HTML/PDF 定位、文件存在性和 SHA 校验、模块列表读取。复用 search_runs()、report_artifact_name() 和 validate_delivery_manifests()。

### DB-P2：模块与 Evidence 关联

从 runs.modules 获取 Registry module_id，从 report-blocks-*.jsonl 获取 FigureBlock/TableBlock，从 Manifest 解析源 artifact，生成只读 Evidence DTO。不把完整统计表复制到数据库。

### DB-P3：Interpretation 持久化

新增独立 interpretation 表，保存 run/module/evidence hash，Markdown 存文件，保存 model/provider/prompt/token/cost，保留多个 interpretation 版本。这是第一个必须新增数据库表的阶段。

### DB-P4：交互式问答

增加 Conversation Session、Message、run/module/evidence 绑定，并分离临时问答与正式 interpretation。在权限模型确定前，不实现跨项目会话。

### DB-P5：FastAPI / Workspace

复用 Shared Service，API 只做权限校验和 DTO 转换，先做只读报告浏览，再开放 AI 生成。

### DB-P6：可靠性与迁移

增加 Schema version、迁移、备份恢复、busy timeout/WAL 压测、多 worker 测试、权限和路径安全测试。

## 15. Final Recommendation

最终建议：**CONDITIONAL GO**。

当前数据库适合作为本地报告运行历史索引、project_id/date/status/output_format 查询源和 Workspace 的运行入口。

当前数据库不适合作为完整报告实体库、Artifact 数据库、模块证据库、AI interpretation 存储、会话数据库或多用户 Web 后端数据库。

最值得实施的一个最小工作包是：

> **只读 Report Query Service + Artifact Resolver**

它不需要修改数据库结构，能够先实现：

~~~text
历史运行
  ↓
选择 run_id / project_id
  ↓
定位 output_dir
  ↓
读取 Report/Input/Artifact Manifest
  ↓
解析 modules
  ↓
定位 FigureBlock/TableBlock
  ↓
返回统一报告详情
~~~

这是 Interpretation Agent 和 Workspace 共同依赖的基础，风险最低，且不会影响现有报告生成。

## 16. 十二个核心问题

1. **BioReport 当前究竟使用什么数据库？**  
   VERIFIED：本地 SQLite，默认 /home/<user>/.bioreport/runs.db，可由 BIOREPORT_DB 覆盖。

2. **数据库当前保存了哪些报告信息？**  
   VERIFIED：运行 ID、项目 ID、时间、版本、布局、输出格式、模块 JSON、配置路径、输出目录、状态、输入 checksum JSON。

3. **是否可以直接查询全部历史报告？**  
   PARTIAL：可以查询全部历史运行记录，但不是完整报告实体；报告文件和 Manifest 需要从文件系统读取。

4. **是否具有稳定的 report_id 和 project_id？**  
   project_id 有；独立 report_id 没有。runs.id 是稳定的自增运行记录 ID。

5. **是否可以定位每份报告的 HTML/PDF 文件？**  
   PARTIAL：可通过 output_dir + report_artifact_name() 推导，但路径可能失效，数据库没有 artifact 校验。

6. **是否可以通过报告记录定位具体分析模块？**  
   PARTIAL：modules JSON 保存模块列表，但没有模块表和模块状态。

7. **是否可以关联 FigureBlock、TableBlock 和 Manifest？**  
   PARTIAL：可以通过输出目录读取 JSONL 和 Manifest 间接关联；数据库没有外键。

8. **是否可以复用当前数据库保存 AI 解读记录？**  
   PARTIAL：可复用 runs.id 作为父记录，但不应把 AI 字段塞进 runs。

9. **是否需要新增 Interpretation 数据表？**  
   需要。建议独立表，支持版本、证据 hash、模型信息和校验状态。

10. **是否可以直接基于现有数据库开发 Web Workspace？**  
    不能直接开发。应先增加只读 Service 和 Artifact Resolver，再封装 API。

11. **是否有必要将当前数据库迁移到 PostgreSQL？**  
    当前没有必要。只有多用户、多 worker、跨主机、高并发写入时才重新评估。

12. **如何以最小改动实现目标路径？**

~~~text
runs.db
  ↓
Report Query Service
  ↓
Artifact Resolver
  ↓
Manifest + FigureBlock/TableBlock
  ↓
Module Evidence Builder
  ↓
Interpretation Agent
  ↓
Interpretation Repository
  ↓
Workspace/API
~~~

