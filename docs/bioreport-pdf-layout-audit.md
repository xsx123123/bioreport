# BioReport PDF Layout Audit

审计日期：2026-10-16。源码基线：`6bd05f9`。范围：两份 2026-10-16 PDF 评审/实施文档中的 Phase 0；本阶段不修改实现和上游输入。

## Current Architecture

当前已有可复用的模块注册、配置校验、HTML/PDF 内容分流、静态图导出、字体和溯源工具，不需要另建 RNA 专用渲染器。

```text
CLI / config.load_config + JSON Schema
  → registry / modules.selected_modules
  → renderer.render_templates
  → modules.compose_report(pdf=True / False)
  → QMD Python cells → render_output helpers
  → Quarto / Pandoc → Typst PDF 或 HTML
  → CLI 检查文件存在 → 可选 PDF 权限保护
```

`bioreport/pipeline.py` 负责可选 AI 数据整合与解释，并非页面布局引擎。`bioreport/cli.py` 负责工作目录、输入校验、溯源、环境变量、执行 Quarto、移动产物和配置备份。`bioreport/renderer.py` 渲染 Jinja2 项目配置并调用 composer。

## Pagination Pipeline

| 层 | 当前职责与边界 |
|---|---|
| Jinja2 | `_quarto*.yml.j2` 配置项目；`rna-cover.typ.j2` 生成封面和目录；不测量正文 |
| Python composer | `modules.py:compose_report` 展开 includes、处理模块元数据、拼接章节；RNA 大章节前插入 weak pagebreak |
| Markdown/QMD | 标题、正文、Python 执行结果混合；没有统一 block ID 或布局清单 |
| Quarto/Pandoc | 执行 cells、解析 Markdown、生成 Typst 标题/引用/书签结构 |
| Typst | 最终测量与分页；`print-style.typ` 控制 sticky heading、图片高度、table.header 和页眉页脚 |
| Lua filter | 未发现仓库自定义分页 Lua filter；Quarto 自身过滤器属于工具链 |
| CSS | HTML 样式和交互布局；不参与 Typst PDF 分页 |

`print-style.typ` 已将三级 heading 设为 `block(sticky: true)`，但只能保护相邻内容起点，不能表达“标题 + 首段 + 首图”的阅读单元。`report-intro` 也使用 sticky，只有部分模板使用。长说明段落及后续图仍可跨页，不能将现状描述为完全没有 heading 保护。

封面通过 include-before-body 放在正文前，封面后强制换页、输出 outline、再换页。这是合理的 front matter 边界。当前源码基线封面确实在 P1，没有复现评审原件的孤立“样本信息”页，不能凭旧 PDF 断言现有 cover 根因。

## Figure Pipeline

`omics/rna/analysis/*` 创建 Plotly Figure → `render_output.show_figure` 按格式分流。

- HTML：嵌入 Plotly JS，输出可响应尺寸的交互图。
- PDF：`print_theme.print_panels` 拆分密集图 → `export_vector` 用 Matplotlib 输出 SVG，特殊 trace 回退 Kaleido → 读取 viewBox 高宽比 → 输出 `#report-figure(path, caption, ratio)`。
- Typst `report-figure` 将图片和 caption 放入同一 figure，placement 为 none，统一编号；图片按 `min(170mm * ratio, 190mm)` 定高。没有针对 caption、说明、可用页高的语义规划。

当前数据结构是 Plotly Figure 加 path/caption/ratio，没有 FigureBlock、FigureGroup、preferred/minimum height 或 layout_priority。`print_panels` 是图内拆分工具，不是跨图组合器。FastQ Screen R1/R2 在两个 cell 中独立显示，不构成 FigurePair。

PCA 的 `pca_plotly.py` 使用 `mode='markers'`，text 仅用于 hover；静态 exporter 的 scatter 分支也未绘制 trace.text。只改 Plotly mode 不能证明 PDF 标签已修好，必须同时覆盖静态导出路径。

FastQ Screen 从 `qc_vis.visualize_multiqc_logs` 经 MultiQC 转为 traces；静态 exporter 对多类别 bar 使用底部两列换行图例，没有 min_fraction、max_categories 或 Other 聚合策略。

HVG PDF 使用 `analysis.heatmap.top_n`，示例为 1000；大于 40 行时静态图隐藏行名。现有拆分主要按样本列，不解决 1000 基因的主图密度。没有完整热图 supplementary 的专门交付流程。

## Table Pipeline

`pdf_results.preview` 排序/裁行 → `render_output.show_print_table` 格式化字符串 → Typst `report-table(headers, rows, numeric)`。

| 能力 | 当前状态 |
|---|---|
| keep_together / allow_split | 没有接口，所有表外层均 `block(breakable: true)` |
| repeat_header | 已有 `table.header(repeat: true)` |
| page_break | 表接口无专用策略；章节有 pagebreak |
| continuation | 无续表标记、尾页最少行或单行续页约束 |
| 原始概率保真 | `raw_probability_columns` 用字符串保留低于浮点范围的值，Decimal 格式化，输入 0 明确标注 |

样本表、富集表与大表使用同一策略，这是小表跨页的直接原因。不可简单将所有表改为不分页，必须对高度超页的大表保留合法拆分与重复表头。

## Template Structure

`omics/rna/qmd/pdf/` 已包含 index、workflow、qc、results、provenance、about 以及 QC/results 子模块，HTML 使用同目录下的非 pdf 模板。两者共享配置、分析函数、display helper、registry 和 composer，但并未共享一个语义布局模型。

共享内容应包括输入数据、统计阈值、筛选排序、指标、路径和 provenance；PDF 页高规划、图组合、续表策略应独立于 HTML 的 tabset、导航和交互容器。

index 当前是项目说明、元数据表、核心指标表、比较组统计表、样本表；没有独立 Executive Summary、MetricGrid 或 Data Scope block。workflow 已有按模块筛选的软件版本/功能表，但主要仍是长方法文字。PDF about 引用 `assets/architecture.svg`，整图按页宽缩放，缺少最小字号保障。

## Top N 与科学口径

当前配置存在三个独立源：

| 输出 | 来源 | 示例值 |
|---|---|---|
| HTML 富集图 | `analysis.enrichment.top_n` | 20 |
| PDF 富集图 | `report.pdf.enrichment_top_n` | 12 |
| PDF 富集表 | `report.pdf.enrichment_rows` | 10 |
| PDF 正文 | `pdf/modules/results/enrichment.qmd` 写死 | 12、1–8、9–12、图 11–14 |

差异不仅是 12/10：图先按 `p.adjust < cutoff` 过滤，再剔除无效 GeneRatio/Count；表却对全部原始 frame 排序。必须统一候选结果、排序和 Top N，另外明确保留无效绘图记录的位置。图号和区间同样不能写死。

`plot_utils.plot_volcano_pvalue` 在 frame.copy 上分类，以 raw p 和 log2FC 判定；绘图 y 为 `-log10(p + 1e-300)`，零值显示在 300，坐标轴自动扩展。未发现写回输入 CSV。阈值计数 `pdf_results.deg_counts` 同样使用 pvalue，padj 当前仅展示而非判定字段。已有测试还明确断言零值图高为 300，后续需更新测试契约。

`omics/rna/schema.json` 目前仅声明 log2fc_threshold、pvalue_threshold，未实现 significance_field 等参数；不能把 additionalProperties 容许未知键视为已支持。未在本仓库获得 RNAFlow 正式显著性定义的充分证据，暂不改变默认 raw p 策略，应标为 display/significance criterion 并明确不等价于 FDR 控制。富集 cutoff 为独立 p.adjust 阈值。

DEG preview 当前按 pvalue 总排序取 10，无上下调均衡抽样。`gene_columns` 已防止把 Ensembl ID 冒充 symbol，应复用。客观统计与可选 AI 分支已有分离基础，但 Executive Summary 的辅助解释标签仍待实现。

## PDF Renderer 与 Metadata

`modules.compose_report` 在 RNA PDF 分支移除 title/date，避免默认标题块；没有另行构建 PDF document metadata。author、subject、keywords、BioReport creator 也未设置。最终基线实测仅有 Typst Creator 和创建/修改时间。

正确方向是分离“可见 title block”与“PDF document metadata”，保留自定义封面，同时显式设置 Title / Author / Subject / Keywords / Creator。元数据不能仅在封面画文字代替。

TOC 使用封面的 `#outline(title: "目录", depth: 2)`；正文标题参与 Typst 编号、outline/bookmarks。基线能提取书签和目录页码，但尚无自动逐项页码验证。

## Provenance

`utils/provenance.py` 已提供分块 SHA256、引擎版本、生成时间、模块、layout、formats、pipeline_version；CLI 在正式运行时生成 `qmd/provenance.json` 并备份配置。直接 input_files 文件有 hash，目录键被跳过，因此 DEG/enrichment 目录中的实际文件不在 input_checksums 覆盖内。

PDF 表只显示逻辑键/hash，about 另列路径；没有包含 artifact/role/path/sha256 的统一 manifest，也没有 Report/Input/Artifact/Reproduction 四类记录。`#show raw` 使用 monospace，但哈希在普通表 cell 中由 `report-cell` 输出普通 text；换行支持不等于 monospace。

## Baseline Evidence

原评审 `report(1).pdf` 未包含在仓库内，本审计不把它当作已重新检查的成品。当前示例的有效字体基线为 **22 页、23 个书签条目，Cover=P1、TOC=P2**，与评审原件的 23 页/22 条书签不同。

复现使用现有验证工具：

```bash
python tests/render_report_inprocess.py \
  -c tests/report.rna.pdf.json \
  -o /tmp/bioreport-pdf-layout-audit-20261016 --pages
```

该脚本未注入 CLI 的 TYPST_FONT_PATHS，初次渲染有字体缺失警告；审计随后用 `bioreport.utils.fonts.typst_font_paths()` 设置此环境变量，重跑同一 staged QMD 的 `quarto render qmd/report_pdf.qmd --to typst --no-execute -M keep-typ:true`，退出码 0，并重新生成所有截图与 review.json。最终 `render-fonts.log` 仍有 `JetBrains Mono` 不存在的 fallback 警告；先前正文 Source Sans 3 / CJK 字体缺失警告已消除，后续需验证 monospace fallback 并固定可用字体。

产物位于 `/tmp/bioreport-pdf-layout-audit-20261016/`：`report.pdf`、`review.json`、`pages/page-*.png`、`pages/contact-*.png`、`execution.json`、`render-fonts.log`、staged 原始 QMD/执行后 QMD/保留 Typst。它们是本机临时审计证据，不是已入库的 golden 或最终交付物。

已查看 P1–6、P13–18 联系表；全部页面已提取文本。实测：

- P3 样本标题/说明与 P4 全表分离；与原评审的 1+5 行切分不同，但仍有明显阅读断裂和留白。
- P9 单张 FastQ Screen 图；R1/R2 不成组。
- P13 HVG 标题/说明与 P14 热图分离。
- P15 volcano 纵轴达到 300，上下调在预览表混排。
- P17 上调图展示 12、表预览 10；P18–19 下调表跨页。
- PDF Title / Author / Subject / Keywords 缺失，Creator=Typst 0.13.0。
- 指标为 6 样本、2 组、Q30 95.86%、mapping 99.04%、检出 16289、DEG up 4364/down 2705，与评审口径相符。

重要证据限制：inprocess 工具执行真实科学 cells，再由 Quarto --no-execute 渲染，没有模拟统计函数，但它不经过 CLI provenance 生成流程。因此本基线的 P20 缺失 fingerprints 不能证明正式 CLI 不生成 hash；正式 provenance 应另做 CLI 端到端验收。本阶段没有运行 HTML 浏览器回归，也没有声明最终 PDF 通过。

## Known Root Causes

1. 没有语义 block 和共享 layout planner，文字、图片、表、说明分别进入自然流式分页。
2. 小表沿用大表可拆策略；sticky heading 保护范围不足以覆盖首图或表。
3. 图片固定全宽、高度仅按比例和硬上限，没有 FigureGroup 或页预算。
4. Top N 多源且候选集合不一致，正文写死图号与数量。
5. Plotly hover text 在静态导出时丢失；图例和 HVG 没有主报告密度策略。
6. 概率稳定变换未与显示范围分离；科学判定字段未配置化。
7. 可见封面与 document metadata 混为一处；输入指纹未覆盖目录内实际读取 artifact。
8. 当前 CLI 只验证渲染成功/文件存在，没有布局、内容、manifest 的生成后 gate。

## Risk Assessment

| 风险 | 后续约束 |
|---|---|
| 改变统计结果 | 不改输入文件；计数、分类、阈值、原始概率与 visual cap 分离验证 |
| 不可拆表超页 | 先估计/测量高度，再选择整体移动或合法拆分；检查长路径/长条目 |
| 影响 HTML | 共用内容语义，按 renderer 输出策略；验证 Plotly/ITables/导航/TOC |
| 伪造已支持的配置 | Schema、运行逻辑、图表、caption、summary 同步接入与测试 |
| 只修 Plotly 不修 PDF | 同时验证 SVG exporter 和最终 PDF 截图 |
| 误用基线证据 | 使用正式 CLI 补 provenance 和 Jupyter 路径；inprocess 不替代端到端验收 |
| 分页不稳定 | 固定字体和工具链；golden 记录版本，覆盖长表、多比较组、缺失/极小值 |

## Recommended Refactor

复用 `modules.py`、`render_output.py`、`print_theme.py`、Typst helpers，不建立平行 renderer。

1. 在共享 report 层增加轻量 Block/Report/Section 模型，覆盖 Paragraph、MetricGrid、TableBlock、FigureBlock、FigureGroup、CalloutBlock、MethodBlock、ProvenanceBlock、AppendixBlock；统一 id/type/content 与要求的七项布局属性。
2. planner 负责 heading 后首个阅读单元、小表整体、超页大表、figure/caption 和 pair/triplet/grid 策略；Typst 负责最终精确测量。分页只用于大章节/front matter/appendix。
3. 先接入现有 helpers 与 PDF QMD，输出可检查的 block/layout manifest，避免只建未使用的 AST。
4. 单一 enrichment.top_n，明确兼容旧配置的迁移/冲突规则；图表使用同一候选集，动态说明数量。
5. 增加 Executive Summary、工作流、PCA 静态标签、legend 聚合、主图/附录 HVG、volcano cap、上下调表；主图 50/100 通过实际可读性对比决定。
6. 扩展现有 provenance 为统一 manifest，覆盖目录内实际 artifact；单独注入 PDF metadata。
7. 扩展现有 tests 和 `render_report_inprocess.py`，新增正式 CLI 双输出、PDF 结构/布局/内容/溯源验证与十类页面 golden 截图。

后续最终验收文档为 `docs/bioreport-pdf-layout-refactor.md`，需按需求逐项记录 PDF、HTML、Content、Layout、Scientific consistency、Provenance 的 PASS/FAIL、前后页面对照和未解决项；当前尚不满足最终验收。

## Phase 0 Boundary

已完成只读源码调查、基线渲染与审计文档。按照实施提示词“然后暂停，不修改实现”，停在此阶段；本次仓库仅新增本审计文档，不修改源码、模板、测试、配置和原始数据。全目标仍未完成，后续实施和最终验证待继续。
