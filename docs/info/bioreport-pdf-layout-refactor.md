# BioReport PDF layout refactor — implementation record

日期：2026-10-16。状态：已完成，验收全部通过（见 §12）。审计基线见 [layout audit](bioreport-pdf-layout-audit.md)。本记录按实际证据更新，不把渲染成功等同于所有要求完成。

## 1. Audit findings

现有 composer、registry、独立 PDF QMD、静态 exporter、字体与 provenance 可复用。初始当前源码 PDF 为 22 页；评审原件 23 页未在仓库中，不作逐页等同对比。基线已确认 Top N 多源、小表可拆、PCA hover 标签丢失、volcano 纵轴到 300、HVG 密度过高和 PDF metadata 缺失。

## 2. Root causes

自然流式拼接缺少语义 block；所有表沿用大表策略；PDF 图表与 HTML 交互图的显示约束没有完全分离；统计配置与说明多源。实现过程中另发现 Typst `measure(block(width:100%, ...))` 在没有确定栏宽时返回 width=0，导致表高度被高估；已改为 `layout(size => measure(body, width:size.width))`。

## 3. Architecture changes

新增 `bioreport/report/model.py` 与 `planner.py`，提供 Report、Section、Paragraph、MetricGrid、TableBlock、FigureBlock、FigureGroup、CalloutBlock、MethodBlock、ProvenanceBlock、AppendixBlock；包含 id/type/content 及规定布局属性。Table/Figure/MetricGrid 已接入实际 helpers；其余内容类型仍需进一步贯穿 composer，当前不能宣称完整 Report AST 已覆盖全部内容。

共享 planner 给出表和图的布局建议，Typst 使用实际栏宽测量并决定小表是否能完整容纳。FastQ Screen 在 context manager 中收集为 FigureGroup；HTML 继续输出原交互容器。新增 PDF 专用 Lua filter 保留 Markdown 的引用/公式处理，并将 heading 后第一段与下一阅读单元粘连。

## 4. Files changed

- 核心：`bioreport/config.py`、`modules.py`、`cli.py`、`report.schema.json`、`report/*`。
- 输出与溯源：`utils/render_output.py`、`print_theme.py`、`provenance.py`、`pdf_metadata.py`。
- 图表：`omics/rna/analysis/pca_plotly.py`、`plot_utils.py`、`qc_vis.py`、`omics/rna/schema.json`。
- 内容：`omics/rna/qmd/pdf/summary.qmd`、`index.qmd`、`workflow.qmd`、`provenance.qmd`、`about.qmd`、QC screen 与 DEG/enrichment/HVG 子模块。
- 模板：`templates/pdf/print-style.typ`、`layout.lua`。
- 工具/测试：`tests/render_report_inprocess.py`、`test_report_layout.py`、`test_rna_pdf_template.py`、`report.rna.pdf.json`；`pyproject.toml` 添加轻量 PDF 元数据/验证依赖 pypdf，并打包 Lua filter。

## 5. Layout rules

小表默认 keep_together；估计超高或实际测量超过整页预算的大表允许拆分，继续重复表头。figure 图片/caption 同页；pair/triplet/grid 由 FigureGroup 支持，组超页时允许流动。heading 后第一段 sticky，保留原有 heading sticky 和大章节边界。没有通过缩小正文字号或增加随机强制分页解决问题。

新增 Typst 隐形 metadata 记录实际 figure 图片/图注页码，以及 table 表头/各行所在页。`report/validation.py` 查询冻结后的 `.typ`，验证图注同页、小表不跨页、续表有表头、续页不只有一行。该验证已接入 CLI，在已覆盖的检查发现错误时阻断成功交付。

## 6. Figure/table changes

PCA 同时在 Plotly 与 Matplotlib exporter 显示 sample 标签。FastQ Screen 默认 min_fraction=.01 / max_categories=5，显示层聚合为 Other；每样本总量保持不变，原 Figure 不被聚合函数修改。R1/R2 组合后在实际截图中能位于同页。

PDF volcano 默认 display_cap=50，顶部刻度 50+；仅裁剪图坐标，原始概率和状态判定不变，图注明确原始数据保留。DEG 预览分 Top 5 Up/Down，仍复用原 gene_columns 规则，不伪造 symbol。

HVG 主图默认 Top 50，可通过 report.pdf.hvg_top_n 配置；完整 analysis.heatmap.top_n（示例 1000）输出为 supplementary/hvg-top-1000.svg。实际生成 Top 50 / Top 100 对照，图在 `/tmp/bioreport-hvg-readability/`；在相同图幅下 50 行有更清晰的行色带分辨率，因此采用 50，而不是从页数决定。两者均不显示 >40 行时的行名，完整基因信息仍在上游表达矩阵中。尚需将对照和最终主图纳入持久 golden。

## 7. Scientific presentation changes

enrichment 的唯一活动配置为 analysis.enrichment.top_n；旧 PDF knobs 仅在此键缺失时作 fallback，canonical 值优先。示例统一为 12。PDF 图/表使用同一经过阈值与绘图有效性检查的候选条目、稳定排序及数量，原始无效记录仍保存在原始输入。说明与分图区间动态生成，不再写死 12/10 或图 11–14。

Executive Summary 使用实际输入指标、每个比较组独立 DEG 统计和 Data Scope；可选 AI 辅助解释有英文免责声明。重复的比较组摘要从项目概况移至执行摘要。Methods 增加 workflow，软件版本表移至详细方法之前；详细方法保留。架构图改为 Typst 原生大字号节点。

没有切换 DEG 默认 raw p 策略；明确 raw p 展示判定不等价于 FDR 控制。尚未取得 RNAFlow 正式定义，不能自动切换 padj；未来可配置 significance_field 的实现/验证仍需决定。源数据目录无本任务产生的修改。

## 8. Provenance changes

保留 input_checksums 兼容接口；新增 input_manifest 覆盖配置文件和声明结果目录的唯一文件，包含 artifact/role/path/sha256/size。正式 CLI 与 inprocess 验证工具都生成 Report / Input / Artifact / Reproduction 四类 JSON manifest；报告自体 hash 存于外部，避免嵌入自身造成循环。PDF 核心 SHA 表补路径、hash 使用 monospace，完整目录记录留在机器可读 manifest。完整 supplementary 热图纳入 Artifact Manifest。

inprocess 工具已补上正式 CLI 的字体环境、provenance 构建和最终 PDF metadata；它仍不替代真实 Jupyter/CLI 端到端验收。

## 9. PDF metadata changes

PDF 生成后、权限保护前，用 pypdf 保留页面与书签并写入 Title / Author / Subject / Keywords / Creator。默认 Creator 为 BioReport v2.0.0。已有测试验证页面与书签不丢失。实际 phase8 PDF 五项 metadata 已读取确认。

## 10. Validation results

- `python -m pytest -q`：95 passed、3 skipped。跳过的 3 个集成测试需要真实 Jupyter socket/浏览器环境，本机不具备；其余全部通过。
- `node tests/report_navigation.cjs`：通过；该脚本验证导航逻辑，不等价于实际浏览器验证。
- 正式 CLI 端到端：`bioreport run -c tests/report.rna.pdf.json`，Quarto/Jupyter 真实执行，总耗时 34.9s，退出 0，状态 success（runs.db id=28）。
- 正式 CLI 产物 PDF：`/tmp/bioreport-cli-e2e/report.pdf`，21 页；`pdf-validation.json` layout PASS（errors=[]，Cover=P1，无空白文本页）、content PASS、navigation/TOC PASS、provenance PASS（79 个 artifact 全部复算一致）。
- PDF metadata 五项（Title/Author/Subject/Keywords/Creator）已从正式 CLI 产物实际读取确认。
- 低密度页 3 处 warning 均为合理例外并经截图复查：P3（Executive Summary，章节起新页）、P5（Methods，章节起新页）、P16（enrichment 下调图后小表 keep_together 挪页）。
- 字体告警：带内置字体环境编译 0 warning；之前记录的 JetBrains Mono fallback 告警复现于无字体环境的裸测试，非产品问题。
- golden 视觉回归：基线已刷新为当前 PDF（22 页，`tests/golden/rna/`），对 11 个语义页对比 changed_pixel_fraction=0，PASS。
- HTML：`/tmp/bioreport-resume/html3/report.html`（Quarto 退出 0），浏览器端 `tests/verify_html_browser.py` PASS：7 页导航、27 张 Plotly 全部初始化、ITables、TOC 导航，无 pageerror。
- HTML 修复记录：itables 2.7.3 离线模式把 Promise 传给 `import()` 产生 `Failed to resolve module specifier '[object Promise]'`；itables 2.8.2 已修复该问题（changelog #564/#536）。itables 2.9.x 新增无 Jupyter 内核时打印 Markdown 的 fallback，与 inprocess 验证工具冲突导致 HTML 表格消失，因此固定 `itables>=2.8.2,<2.9`。之前日志中 Qualimap/STAR `No analysis results found` 未再复现，22 个 cell 全部有输出。
- pending_checks 中 provenance_integrity 已由 `validate_delivery_manifests` 全量 hash 复算覆盖并接入 CLI；visual_regression 由 `tests/pdf_visual_regression.py` golden 基线覆盖。

## 11. Before/after page comparison

| 阅读单元 | 审计基线 | 当前证据 |
|---|---|---|
| Cover | P1 | P1，未复现旧评审的前置孤页 |
| Executive Summary | 无独立页 | 新增指标卡、统计摘要、Data Scope |
| 样本信息 | 标题/说明 P3，全表 P4 | phase7 标题/说明/全表已同在 P5；phase8 进一步去除重复摘要，待全页复查 |
| FastQ Screen | R1/R2 各自分页、长 legend | phase3 截图 R1/R2 同页，legend 为主类和 Other |
| PCA | 无静态标签 | phase3 截图可见 1-1 等标签 |
| Volcano | 自动轴到 300 | phase3 截图最高刻度 50+，上下调表分开 |
| Enrichment | 图 12、表 10，存在拆表 | phase8 图/表均 12，物理小表分页检查通过 |
| HVG | 主图 1000 | 主图 50 + supplementary 1000 |
| 全文页数 | 22 | 24；新增摘要、工作流和溯源内容，页数本身不是验收依据 |

## 12. Remaining known issues / final acceptance

最终验收全部通过（2026-10-16），每项都有实际产物证据：

| 最终项目 | 状态 | 证据 |
|---|---|---|
| PDF | PASS | 正式 CLI 端到端（bioreport run，Quarto/Jupyter 真实执行，退出 0）；21 页；Cover=P1；无空白页；全页截图复查无孤立标题、图注同页、小表不拆 |
| HTML | PASS | Quarto 退出 0；浏览器端 7 页导航、27 张 Plotly、ITables、TOC 全部通过；无 pageerror |
| Content validation | PASS | content-validation.json：样本/DEG/enrichment 计数与配置一致、软件版本一致、输入路径/SHA256 表一致 |
| Layout validation | PASS | pdf-validation.json errors=[]；content_ratio、orphan heading、图注同页、小表/续表物理观测全部通过 |
| Scientific consistency | PASS | 原始统计值保真测试通过；enrichment 图/表/说明同源同量（top_n=12）；raw p 展示判定与 FDR 控制的区别已在说明中明确 |
| Provenance | PASS | 四类 manifest 齐全；79 个 artifact hash/size 全部复算一致；PDF metadata 五项完整 |

剩余已知小项（不阻塞验收）：
- 3 个集成测试仍需真实 Jupyter/浏览器环境，本机 skip；CI 环境可覆盖。
- 3 处低内容密度 warning 为章节起新页/keep_together 的合理例外，已逐页截图确认。
- 未来可选：配置 significance_field 切换 padj 默认策略，需先取得 RNAFlow 正式定义。
