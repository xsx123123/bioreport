[English](../README.md) | **中文**

<p align="center">
  <img src="蓝色生物信息报告图标.png" alt="BioReport Logo" width="250">
</p>

# BioReport (多组学 Quarto 报告生成系统)

## 📖 项目简介

作为 [**CygnusX BioOps**](https://github.com/xsx123123/omichub) 体系下的核心可视化与交付组件，**BioReport** 是一款基于 Python 与 Quarto 构建的模块化组学报告生成工具。目前内置的 RNA-seq 模块支持一站式整合质控（`fastp`）、序列比对、差异表达及富集分析结果，并可通过配置文件灵活编排报告模块，按需接入 AI 模型实现自动化结果解读。在输出格式上，默认 RNA-seq 流程生成的交互式单文件 HTML 包含六个可切换的章节视图；仓库内置的完整 RNA-seq 示例与通用分析示例均支持同时导出单文件 HTML 与 PDF，而本地轻量级 RNA 示例则仅输出 HTML。

pdf 示例报告
![RNA-seq pdf 示例报告](./rna-seq-pdf-report.png)
html 示例报告
![RNA-seq html 示例报告](./rna-seq-html-report.png)


## ✨ 核心功能

- **统一配置**：JSON 或 YAML 驱动报告类型、标题、导航、章节、AI、分析参数和交付格式；`configs/report.example.json` 展示配置结构，`bioreport/report.schema.json` 定义字段类型与参数范围，`input_files` 中的相对路径以 `data_dir` 为根。
- **模块组合**：通用引擎通过 `report.modules` 按顺序组合 `index`、`workflow`、`provenance`、`ai`、`about` 等共享模块；当前内置的 `qc.*`、`results.*` 细分模块（如 `qc.fastp`、`results.deg`、`results.enrichment`）属于 RNA-seq 模板。其他组学或自定义流程可通过 `report.module_definitions` 引用外部 QMD，后续将逐步补充各组学的原生模块、数据契约和分析组件。
- **双格式输出**：通用引擎支持 `report.output_format: [html, pdf]` 生成 HTML 和 PDF；HTML 保留 Plotly/Itables 交互能力，PDF 使用静态图和 Typst 排版，并支持 PDF 语义与版式校验。当前 RNA-seq 单页模板提供六个导航页面，其他组学将沿用同一交付接口并使用各自的章节模板。
- **多报告变体**：同一套数据和代码可输出完整版、精简版、无 AI 版等报告，并可通过模块列表和 PDF 参数控制内容密度。
- **可追溯交付**：每次运行记录输入文件 SHA-256、配置副本、引擎版本、模块清单、运行日志和交付 manifest，并对最终产物执行重哈希校验；`provenance` 页面展示可复现所需的元数据。
- **运行历史与证据**：Workspace/API 可读取历史运行、报告产物、输入文件、证据包、溯源信息和模块级 AI 解读，并对不可用路径或完整性状态给出明确结果。
- **自动化流程**：按配置执行输入完整性检查、模块组合、数据展示、可选 AI 解读、Quarto 渲染、PDF 校验和交付清单生成。
- **逐结果 AI 解读**：LLM 针对 fastp、FastQ Screen、QualiMap、STAR、PCA、表达分布、矩阵、热图、DEG 及每个富集结果分别生成 Markdown 解读卡片，并放置在对应表格或图形下方；结构化证据与来源结果绑定。
- **PDF 视觉解读**：PDF 的 `ai.scope: results` 使用两阶段流程，先渲染图表，再将已渲染图像与结构化证据提交给视觉模型，最后二次渲染回填解读卡片；图像不可用时自动回退到结构化证据。
- **AI 可审计性**：统一使用 OpenAI Python SDK 接入兼容服务，支持超时、重试、输入截断、服务商降级、视觉降级和空响应回退；结果槽位可记录证据哈希、提示词版本、模型参数和响应状态。
- **交互式报告**：基于 Quarto 生成，包含 Plotly 交互图表、Itables 数据表格。
- **Docker 支持规划**：仓库已保留 Dockerfile 和部署草案，正式容器化交付方式将在后续版本完善。
- **向后兼容**：旧版 `project_summary.json` 仍可运行。

## 下一阶段重点

下一阶段将集中优化三条方向：完善 Docker 镜像、挂载约定和正式容器化交付；将现有逐结果 AI 框架升级为分模块 Prompt、证据校验、可审计 Agent 和 Workspace 异步解读；在通用引擎契约基础上补充其他组学的原生模块、数据读取、分析函数和报告模板。详细计划见 [`todo.md`](../todo.md) 和 [`AI.md`](AI.md)。

## 🛠️ 环境依赖

- [Python 3.10+](https://www.python.org/)；本地运行需安装 [Quarto](https://quarto.org/)
- 默认安装包含 RNA 报告和 AI 的 Python 依赖：`python -m pip install -e ./`，旧版 `rna` / `ai` extra 写法继续兼容
- PDF 只读锁与版式校验为可选依赖：`pip install -e '.[rna,security,validation]'`
- PDF 图表通过 Kaleido 导出为图片；所用 Kaleido 版本若依赖 Chrome / Chromium，需在运行环境提供浏览器
- Docker 镜像固定使用 Quarto 1.8.26；构建和容器测试命令见下方 Docker 说明及 `deploy/README.zh-CN.md`

## 🚀 快速上手

### 本地生成 RNA 示例报告

```bash
python -m pip install -e ./
python -m bioreport validate -c tests/report.rna.local.json
# 生成 HTML 报告
python -m bioreport run -c tests/report.rna.html.json -o output/rna-report
# 生成 pdf 报告
python -m bioreport run -c tests/report.rna.pdf.json -o output/rna-report-pdf
# 生成 pdf 报告 (ai解读)
python -m bioreport run -c tests/report.rna.pdf.ai.json -o output/rna-pdf-report-ai 
```

### Workspace 与运行记录

报告运行记录默认保存在 `~/.bioreport/runs.db`。当前 Workspace v1 提供运行历史、项目筛选、报告产物、证据、溯源信息和模块级 AI 解读的查询能力；命令行可按项目、状态和日期筛选，并以 Rich 终端表格查看：

```bash
bioreport runs
bioreport runs --project PRJ-RNA --status success --since 2026-01-01 --limit 20
bioreport runs --json
bioreport runs --tui
```

![查询运行记录](tui.png)

Workspace v2 的数据库迁移必须显式执行。迁移前默认创建相邻的 `.bak` 备份；恢复也必须由操作人员明确调用：

```bash
bioreport workspace-migrate --db /path/to/runs.db
bioreport workspace-restore --db /path/to/runs.db
```

历史报告查询和 API 启动不会自动迁移数据库。使用 `--db /path/to/runs.db` 或环境变量 `BIOREPORT_DB` 指定数据库。

`--tui` 启动后默认显示运行仪表盘，包括总运行数、成功/失败数、成功率、项目数和最近运行；按 `s` 搜索、`r` 刷新、`c` 清除筛选、`q` 退出。

### RNA-seq 示例与输出

示例数据位于 `examples/rna-seq/data/`，本地配置为 `tests/report.rna.local.json`。默认使用 `single` 模式，生成以 `project.project_id` 为前缀的 `<project_id>_report.html`；启用 PDF 时还会生成 `<project_id>_report.pdf`。HTML 将 Quarto、Plotly、Itables、样式、脚本和图片资源内嵌为单文件，报告章节通过顶部导航切换。示例配置包含项目概况、分析流程、质量控制、分析结果、溯源信息和关于页面，`ai` 等模块按需启用。

如需多页 HTML，将 `report.layout` 改为 `website`，并从输出目录的 `index.html` 打开。`website` 不能与 PDF 同时使用；`--dry-run` 可检查配置、模板组合和输入文件，但不会调用 AI 或执行 Quarto。`configs/report.example.json` 使用容器内 `/data` 作为数据根目录，本地运行前需要按实际挂载路径修改。

### 模板与样式扩展

需要单文件 HTML/PDF 时，将 `report.layout` 设为 `single`，并按需设置 `report.output_format`。RNA-seq 章节位于 `omics/rna/qmd/`；所有组学共用的关于、常见问题、许可、商标和 AI 页面位于 `templates/shared/`；共享样式位于 `templates/theme/`。报告标题、模块顺序、分析阈值和 PDF 预览参数均由配置文件控制，修改模板或 Logo 后重新生成报告即可生效。

### Web 端 AI 现状与规划

当前 Web 端已经具备 Workspace v1 的运行历史、证据、产物、溯源和模块级 AI 解读浏览能力，但完整的 AI 工作台尚未作为最终产品形态完成；静态 HTML/PDF 仍是当前主要交付方式。下一大版本计划建设 Workspace v2，将项目、运行、分析模块、结果证据、逐结果 AI 解读和交付版本串成统一工作流，支持异步解读、证据定位、重新解读、版本保留以及 HTML/PDF 原位回填。详细规划见 [`todo.md`](../todo.md) 的“Web 工作台大版本升级：BioReport Workspace v2”。

### Docker 与 PDF 部署说明

Docker 镜像固定 Quarto 1.8.26，构建时会执行 RNA HTML/PDF smoke test。构建镜像并测试：

```bash
docker build --platform linux/amd64 -f deploy/Dockerfile -t bioreport:latest .
docker run --rm --entrypoint python bioreport:latest /opt/bioreport-smoke-test.py
```

配置挂载、报告运行和 RNA-seq PDF 模板的详细说明见 [`deploy/README.zh-CN.md`](../deploy/README.zh-CN.md)。

## 🏗️ 技术架构

BioReport 采用配置驱动的模块化报告架构，将报告组织、领域内容、数据展示与文档渲染分别管理。系统读取已有分析结果，根据 JSON / YAML 配置选择报告章节、绑定输入文件与展示参数，再组合 Quarto 文档，生成交互式 HTML 或适合打印归档的 PDF，并支持按需加入 AI 辅助解读。

> 本节是面向使用者的概览；实现细节（流水线步骤、模块注册机制、PDF 语义校验、扩展指南）见 **[Architecture.md](Architecture.md)**。

下图表达组件依赖与产物流向（非逐行执行时序）：实线为主构建链路或数据输入，虚线为可选 AI 分支及解读内容回填。HTML 或非视觉路径会在 Quarto 渲染前生成解读；PDF `scope: results` 会先渲染图表，再基于已渲染图像和结构化证据生成解读，最后二次渲染回填卡片。Docker 属于生成阶段的运行环境。

```mermaid
flowchart LR
    subgraph INPUT["01 · 数据输入"]
        direction TB
        A["RNAFlow / FlowFrame"]
        B["DEG / QC / Enrichment"]
        C["项目配置与元数据"]
    end

    subgraph CORE["02 · BioReport Core"]
        direction TB
        D["CLI / Pipeline"]
        E["Module Registry"]
        F["Analysis Functions"]
        D --> E --> F
    end

    subgraph EVIDENCE["03 · Evidence & Visual Capture"]
        direction TB
        G["Result evidence"]
        H["Statistics + tables"]
        I["Rendered figures + block manifest"]
        G --> H
        G --> I
    end

    subgraph AI["04 · Interpretation Agent"]
        direction TB
        J["Module Orchestrator"]
        K["AIInterpreter"]
        L["Scientific Validator"]
        M["Per-result Markdown cards"]
        J --> K --> L --> M
    end

    subgraph REPORT["05 · Report Generation"]
        direction TB
        N["QMD Interpretation Slots"]
        O["Quarto / Jupyter"]
        P["HTML / final PDF"]
        P0["PDF first render"]
        T["PDF second render"]
        N --> O
    end

    subgraph AUDIT["06 · Provenance"]
        direction TB
        Q["Evidence Hash"]
        R["AI Trace / Manifest"]
        Q --> R
    end

    A --> B
    B --> F
    C --> D

    F --> G
    H --> J
    I --> J

    E --> N
    M -.-> T -.-> P
    O --> P
    O --> P0
    P0 --> I

    G -.-> Q
    L -.-> R
    P -.-> R

    classDef blue fill:#eff6ff,stroke:#3b82f6,color:#173258
    classDef cyan fill:#ecfeff,stroke:#0891b2,color:#164e63
    classDef purple fill:#faf5ff,stroke:#a78bfa,color:#553285
    classDef green fill:#f0fdf4,stroke:#22a06b,color:#14532d

    class A,B,C,D,E,F blue
    class G,H,I cyan
    class J,K,L,M purple
    class N,O,P,Q,R green
```




BioReport 根据配置组合领域模块与共享模板，在 Quarto 执行阶段读取分析结果并生成图表，分别适配交互式 HTML 与打印 PDF。AI 解读作为可选分支，在渲染前生成辅助解释内容。

技术栈按职责划分如下（设计原则：**配置决定结构，模块承载内容；分析函数复用，交付形式适配**）：

| 职责 | 技术组成 | 说明 |
| :--- | :--- | :--- |
| 配置与运行编排 | Python · JSON / YAML · JSON Schema | 配置加载、字段校验、路径解析、模块选择、输入检查及生成流程编排 |
| 模块与内容组合 | Registry · QMD · 模块组合器 · Jinja2 | 注册领域模块及输入要求，按配置组合章节、传入模块参数，生成 Quarto 配置与部分模板内容 |
| 数据处理与交互展示 | pandas / NumPy · Plotly · ITables | 读取已有质控、表达、差异及富集等分析结果，进行整理、统计汇总、绘图与可检索表格展示 |
| 多格式渲染与交付 | Quarto · Jupyter · 静态图形 · Typst | HTML 提供交互式浏览；PDF 使用 PDF 专用章节、适合分页的静态图表与 Typst 排版；两种输出共享分析函数 |
| 可选 AI 辅助解读 | OpenAI SDK · 结构化证据 · Markdown | 默认按结果生成独立解读卡片；HTML/非视觉路径在渲染前生成，PDF 视觉路径在第一次渲染后读取图像与证据，再二次回填；模型生成内容需研究人员审阅 |
| 运行环境 | 本地 Python / Quarto · Docker | 本地或容器内完成模板渲染、代码执行与文档构建；报告阅读使用浏览器或 PDF 阅读器 |

> 架构图的权威源文件是 [`templates/shared/assets/architecture.mmd`](templates/shared/assets/architecture.mmd)：报告「关于」页通过 include 机制内嵌该 Mermaid 源码。README 和 `docs/Architecture.md` 使用同一架构语义的说明性副本；PDF 中的静态 SVG（`templates/shared/assets/architecture.svg`）需要在架构图变更后重新离线导出。当前内置 RNA-seq 模块；新增组学类型需要提供对应的数据读取、图表和解释模块。

## 📂 目录结构说明

```text
.
├── bioreport/                   # 组学无关核心引擎与 CLI
│   ├── __init__.py
│   ├── __main__.py              # 支持 python -m bioreport
│   ├── cli.py                   # CLI 解析与主流程编排
│   ├── config.py                # YAML/JSON 统一配置加载 + 项目元数据
│   ├── report.schema.json       # 报告配置字段与取值约束
│   ├── registry.py              # 组学模块注册表与模块契约
│   ├── modules.py               # 通用模块组合与兼容别名
│   ├── renderer.py              # Jinja2 模板渲染与字体 staging
│   ├── pipeline.py              # AI 分析流程封装
│   ├── assets/                  # 内置字体（PDF / 离线 HTML 使用）
│   ├── ai/                      # AI 调用引擎
│   │   ├── engine.py
│   │   └── schemas.py
│   ├── report/                  # PDF 语义文档模型与渲染后校验
│   │   ├── model.py             #   语义块词汇表
│   │   ├── planner.py           #   布局高度估算
│   │   ├── composition.py       #   章节组合（report-plan.json）
│   │   ├── recording.py         #   执行期语义块记录
│   │   ├── validation.py        #   PDF 版式/内容校验
│   │   └── content_validation.py#   渲染结果与原始输入比对
│   └── utils/                   # 工具脚本
│       ├── consolidate_rna_seq_data.py
│       ├── render_output.py / print_theme.py / pdf_results.py  # 格式感知展示与静态图导出
│       ├── fonts.py / font_stage.py     # 字体发现与 staging
│       ├── pdf_metadata.py / pdf_security.py  # PDF 元数据与只读锁
│       ├── provenance.py        # 溯源与交付 manifests
│       ├── run_db.py            # SQLite 运行记录
│       ├── report_utils.py / visualize_utils.py / setup_report.py
│       └── prompt.txt
├── omics/                       # 组学插件包（自动发现）
│   ├── __init__.py              # load_all：遍历子包调用 register(registry)
│   ├── base.py                  # OmicsPackage Protocol
│   └── rna/                     # RNA-seq 模块、QMD 与分析脚本
│       ├── modules.py           # RNA 模块声明、输入契约与导航图标
│       ├── schema.json          # RNA 分析参数 schema
│       ├── qmd/                 # RNA 专属页面（index/workflow/qc/results 及 pdf/、modules/）
│       └── analysis/            # HTML 与 PDF 共用的绘图函数
├── templates/                   # 通用 Quarto 壳、主题与资源
│   ├── _quarto.yml.j2           # Quarto 网站配置 Jinja2 模板
│   ├── _quarto-single.yml.j2    # 单页 HTML/PDF 配置模板
│   ├── shared/                  # 全类型共用内置页面（about/faq/license/trademark/AI）及其资产
│   ├── theme/                   # HTML 主题与样式
│   ├── pdf/                     # PDF Typst 样式（layout.lua、print-*.typ、封面模板）
│   ├── reference/               # bibliography / csl 引用资源
│   └── logo/
├── configs/                     # 报告配置文件
│   ├── report.example.json
│   └── report.generic.json
├── examples/                    # RNA 与通用 assay 示例数据
├── tests/                       # 单元、交付布局与可选集成测试
├── archive/                     # 旧版演示与运行产物归档，不参与运行
├── pyproject.toml               # Python 包配置
├── deploy/Dockerfile             # 唯一 Docker 交付定义
├── docs/Architecture.md          # 架构详解
└── README.md                    # 项目说明文档
```

### 共用内置页面（所有报告类型通用）

`templates/shared/` 中的 `about.qmd`、`faq.qmd`、`license.qmd`、`trademark.qmd`、`AI.qmd` 是**所有报告模版共用**的内置页面：它们由 `bioreport/modules.py` 的 `MODULES` 注册为组学无关的内置模块，随核心模板一起分发。`bioreport/cli.py` 在渲染任何 assay 类型（RNA-seq 或通用 assay）时都会先把 `templates/shared/` stage 为临时 Quarto 项目的 `qmd/` 根目录，再让各组学包（如 `omics/rna/qmd/`）覆盖叠加自己的页面——因此核心引擎不依赖任何具体组学，修改这些共享文件会影响全部报告类型，只有 `rna.*` 注册模块及 `pdf/` 子目录下的内容才是 RNA-seq 专属。

## 📝 配置文件 (`configs/report.example.json`) 关键字段

### `report` — 报告级设置

| 字段 | 说明 |
| :--- | :--- |
| `type` | 报告类型标识，例如 `rna-seq`；实际内容由 `modules` 控制 |
| `title` | 报告主标题 |
| `language` | 报告语言，例如 `zh` / `en` |
| `output_format` | `html`、`pdf` 或 `[html, pdf]` |
| `layout` | `single`（默认）或 `website`（多页 HTML） |
| `modules` | 内容模块 ID 列表，决定单页中的内容与顺序；`qc`、`results` 可分别替换为对应的子模块；旧 `sections` 字段仍可使用 |
| `module_definitions` | 自定义模块 ID 到 QMD 路径、标题、`params` 和必需输入的映射；路径相对配置文件所在目录 |
| `theme` | HTML 报告主题，形如 `{"light": "...", "dark": "..."}`；省略时使用 `templates/theme/` 中的默认主题，路径相对临时 Quarto 项目根目录 |
| `css` | HTML 报告的 CSS 文件列表；省略时使用 `templates/theme/styles.css` 和 `itables_saas.css`，路径相对临时 Quarto 项目根目录 |
| `logo` | 网站模式中的 Logo 图片路径 |
| `logo_href` | 网站模式中的 Logo 点击链接 |
| `announcement` | 网站模式中的顶部公告，设为 `null` 可关闭 |
| `pdf` | PDF 预览行数、富集 Top N、`qc_detail: key / all`、字体等打印参数，见下文「RNA-seq PDF 专用模板」 |
| `security` | PDF 只读锁（`enable_read_only_lock`、`allow_copy_text`、`allow_print`、`owner_password(_env)`）；需安装 `'.[security]'` |
| `navbar_right` | 单文件 HTML 顶部导航栏右侧内容 |

单文件 HTML 的两个 Logo 在组合模板中定义，分别链接到 [BioReport 仓库](https://github.com/xsx123123/bioreport) 和 [华中农业大学官网](https://www.hzau.edu.cn/)。

自定义模块示例：

```json
{
  "report": {
    "layout": "single",
    "modules": ["custom.finding"],
    "module_definitions": {
      "custom.finding": {
        "path": "modules/finding.qmd",
        "title": "发现",
        "params": {"input_key": "measurements"},
        "required_inputs": ["measurements"]
      }
    }
  },
  "input_files": {"data_dir": "/data", "measurements": "measurements.csv"}
}
```

外部 QMD 可在代码块中通过 `REPORT_CONFIG` 读取输入数据；静态图片路径应为绝对路径，Quarto 才能在临时组合目录中找到并内嵌它们。
配置 `params` 时，组合器在模块内容前设置 `report_module = {"id": 模块ID, "params": 配置参数}`；同一 QMD 可用不同模块 ID 和参数引用多次。自定义模块中的 `#| label:` 及对应 `@标签` 引用会按模块区分，避免重复引用时发生标签冲突。模块内的相对 `include` 会按原 QMD 所在目录递归展开，循环引用会报错。
使用 Docker 时，应把包含 JSON 和 `modules/` 的目录整体挂载进容器，使相对模块路径在容器内仍然存在。

`examples/generic-assay/` 提供非 RNA 示例：同一份 QMD 在 JSON 中被引用两次，每次通过 `params.input_key` 绑定不同的 CSV。QMD 用 `report_module["params"]` 读取当前引用的参数、通过 `load_config()` 读取输入路径，再用 `show_table()` / `show_figure()` 在 HTML 与 PDF 中分别输出交互或静态结果。本地可运行 `bioreport run -c configs/report.generic.json -o output/generic-report`；Docker 部署草案见 [`deploy/README.zh-CN.md`](../deploy/README.zh-CN.md)。这个例子的数据列契约是 `sample`、`group`、`value`；其他分析可定义自己的模块和列契约。

### `project` — 项目元数据

| 字段 | 说明 |
| :--- | :--- |
| `client` | 客户/课题组名称 |
| `species` | 物种 |
| `genome_version` | 参考基因组版本 |
| `pipeline_version` | 分析流程版本 |
| `analysis_date` | 分析日期 |

### `input_files` — 输入数据路径

| 字段 | 说明 |
| :--- | :--- |
| `data_dir` | 数据根目录；相对路径以配置文件所在目录为起点，省略时也使用配置文件所在目录 |
| `qc_file` / `mapping_file` / `tpm_file` / `sample_file` | 核心统计与表达文件 |
| `fastp_report_dir` / `fastp_stats_file` | fastp 质控报告 |
| `fastq_screen_r1_dir` / `fastq_screen_r2_dir` | 污染检测报告 |
| `qualimap_dir` | QualiMap / STAR 比对质控 |
| `contrasts_file` / `deg_dir` / `enrichment_dir` | 差异分析与富集结果 |
| `software_versions_file` | 流程页的软件版本表；选择 `rna.workflow` 时必填，`validate` 和 `run` 会检查文件存在且可读 |

其他输入字段的相对路径基于 `data_dir` 解析，绝对路径直接使用。修改输入或参数后，需要重新运行生成命令才能更新 HTML / PDF。

可选 `files` 对象按结果文件名指定每个比较组的 DEG 或富集文件路径；相对路径同样基于 `data_dir` 解析。

### `analysis` — 分析参数

| 字段 | 说明 |
| :--- | :--- |
| `deg.log2fc_threshold` | 差异基因 log2FC 阈值 |
| `deg.pvalue_threshold` | 差异基因 P 值阈值 |
| `enrichment.p_cutoff` | 富集显著性阈值 |
| `enrichment.top_n` | 富集图展示条目数 |
| `heatmap.top_n` | 热图展示基因数 |
| `pca.height` / `pca.width` | PCA 图尺寸 |
| `distribution.threshold` / `distribution.width` / `distribution.height` | 表达分布图参数 |
| `expression.preview_rows` | 表达矩阵 HTML 预览行数；RNA PDF 默认预览 8 行 |

### AI 配置与后续计划

统一 JSON/YAML 配置已经为 AI 兼容性预留 `enabled`、`provider`、`model`、`base_url`、`api_key_env`、`scope`、`vision`、输入限制和回退策略等字段，可兼容 OpenAI SDK 及 OpenAI-compatible 服务商。详细字段、当前逐结果流程和 PDF 视觉流程见 [`AI.md`](AI.md)。

当前主线已经具备逐结果 AI 解读框架；下一版本将重点优化分模块 Prompt、证据约束、输出验证、审计字段和 Web Workspace v2 的异步解读能力，详见 [`AI.md`](AI.md) 与 [`../todo.md`](../todo.md)。

## 🔄 向后兼容

- 推荐显式指定 `configs/report.example.json`；旧 YAML 和 `project_summary.json` 仅由加载器兼容，不再作为仓库示例。
- `bioreport.config.load_config()` 会自动识别 `.yaml` / `.yml` / `.json` 文件，并把旧的 `project_meta` 结构映射到新的 `project` 结构。
- `setup_report.py` 新建配置时以容器内 `/data` 为数据根目录；更新已有配置时保留已填写的输入路径。

## 模块与输出边界

- 当前生成入口使用根目录的 `bioreport/`、`omics/rna/` 和 `templates/`。归档内容位于 `archive/`，不参与当前生成流程。
- 旧 HTML 是一组文件，因为 `report.layout: website` 将各个 QMD 渲染为独立网页，而且 `_quarto.yml.j2` 设置了 `embed-resources: false`。`report.layout: single` 会先按 `report.modules` 组合章节，再用 `embed-resources: true` 输出 HTML；RNA-seq 在单个 `<project_id>_report.html` 内提供六个可切换页面。RNA PDF 使用独立章节模板与 Typst 打印样式。
- 内置 `qc.*` 和 `results.*` 模块使用 RNA-seq 数据列契约。其他分析流程可以通过 `module_definitions` 引用自己的 QMD；同一份 QMD 可传入不同 `params` 重复使用。新数据类型仍需提供对应的读取与解读模块。
- HTML 中的 Plotly 和 ITables 资源由展示函数以内联或离线方式提供；普通文献超链接仍可能指向外部网站。RNA PDF 图表使用 Matplotlib 导出 SVG。

## 验证与测试

## BioReport Workspace v1

Workspace 提供历史报告、证据和模块级解读的本地工作台。先复制 `.env.example` 并设置数据库和可信报告根目录，然后启动仅监听 loopback 的 API：

```bash
pip install -e '.[web]'
BIOREPORT_DB=/path/to/runs.db \
BIOREPORT_TRUSTED_ROOT=/approved/report/root \
python -m bioreport.api_server --host 127.0.0.1 --port 8000
```

另一个终端启动 React 工作台：

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

默认 API 不接受公网绑定；绑定非 loopback 地址前必须设置 `BIOREPORT_API_TOKEN`，并在反向代理中配置项目授权。Workspace 只通过逻辑 artifact ID 读取可信根目录下由 Manifest 登记的文件，不直接向浏览器暴露 SQLite 或本地路径。详细 API、迁移、安全和验收记录见 [`architecture`](architecture)。

团队部署可额外设置 `BIOREPORT_ALLOWED_PROJECTS`（精确项目 ID 白名单）、`BIOREPORT_RATE_LIMIT_PER_MINUTE`（每客户端限流）和 `BIOREPORT_CORS_ORIGINS`（明确的浏览器来源白名单）；请求中的 `project` 参数只用于筛选，不能授予项目权限。

- `bioreport validate -c <配置文件>`：检查 JSON/YAML 配置结构、字段取值、模块选择及必需输入路径（存在性、可读性、`_file` / `_dir` 路径类型）；所选模块已配置的可选输入也会检查，其他无关输入缺失仅告警。相对路径基于 `input_files.data_dir`，未配置该目录时基于配置文件目录。不检查文件内容或执行 Quarto / AI；模板组装请使用 `run --dry-run`。
- `bioreport run -c <配置文件> -o <输出目录> --dry-run`：进一步检查模块选择、模板组合与输入文件，不调用 AI 或执行 Quarto。
- `bioreport init`：显示初始配置位置，不会自动创建配置文件。

在仓库根目录安装测试依赖并运行常规测试：

```bash
pip install -e '.[rna,dev]'
python -m pytest -q tests -k "not integration"
```

完整渲染测试需要允许 Jupyter 内核启动，并支持 Kaleido 图像导出：

```bash
RUN_REPORT_INTEGRATION=1 python -m pytest -q tests/test_integration_render.py
```

完整测试用通用分析及 RNA 示例生成 HTML 和 PDF，检查内嵌资源、章节结构与文件输出；导航脚本另由常规测试验证。详细日志保存在输出目录的 `<project_id>_<time>_bioreport.log`（以配置中的项目标识和运行时间为前缀），成功生成后会保存 `run_config_backup.json` 或对应 YAML 扩展名的配置备份。

## ❓ 常见问题

- **AI 报告没有生成？** 确认 `report.modules` 包含 `ai`、`ai.enabled` 为 `true`，并检查 AI 依赖、服务商 API Key、模型标识及网络连接。Docker 中需将对应 API Key 环境变量传入容器。
- **路径报错？** 检查解析后的路径是否存在。本地相对路径基于配置目录和 `data_dir`；Docker 配置需使用容器内的路径，并挂载实际数据。
- **报告章节未按配置隐藏？** 请确认 `report.modules` 中已移除该章节，并重新运行 `python -m bioreport run`。

---
 
## 版本信息

**版本**: v2.0.0 
**作者**: Zhang Jian 
**最后更新**: 2026-10-17 

## 🤝 开源协作与致谢

<p align="center">
  <img src="愿景.png" alt="愿景 FROM STARDUST, TO DISCOVERY：让每一次计算留下证据，让每一份报告承载发现。本项目欢迎通过 GitHub 提交问题反馈与模块贡献；感谢华中农业大学相关科研团队在研究场景、分析需求与工具测试方面提供的宝贵支持。开发与维护：BioReport / CygnusX BioOps 研发团队。" width="880">
</p>
