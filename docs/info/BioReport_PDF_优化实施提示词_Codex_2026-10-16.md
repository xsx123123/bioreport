# BioReport PDF 产品级优化 · Codex 实施提示词

> **用途**：将本提示词直接交给 Codex，用于对 BioReport 仓库进行“调查 → 设计 → 实施 → 渲染 → 回归验证”的完整优化。
>
> **重要原则**：先调查源码，再实施；不要凭猜测改模板。不要通过大量局部 margin/padding 调参掩盖 Layout Engine 问题。不得修改上游分析结果和原始统计值。

---

# 角色

你是一名资深科研软件架构师、Bioinformatics Reporting Engineer、Quarto/Typst 文档工程师。

你正在维护：

> **BioReport — configuration-driven, provenance-aware scientific reporting engine**

BioReport 是 CygnusX BioOps 的科研报告生成组件，当前支持 RNA-seq 报告，并计划继续支持多组学模块。

你的任务不是简单“把 PDF 调漂亮”，而是：

> 将 BioReport 从“内容自动排版器”升级为“产品级科研报告编排与渲染系统”。

---

# 当前问题证据

当前生成的 RNA-seq PDF：

```text
report(1).pdf
```

共 23 页。

已经确认的主要问题：

1. 第 1 页只有孤立标题“样本信息”；
2. 真正 Cover 在第 2 页；
3. 第 4–5 页样本表被拆成 1 行 + 5 行；
4. 第 8–12 页 QC 图表分页不合理；
5. 第 9、11 页存在 section 与 figure 断裂；
6. 第 10 页基本只有一张 FastQ Screen 图；
7. 第 14–15 页 4.2 标题与 Figure 9 存在分页关系问题；
8. 第 19–20 页 enrichment table 被拆成 6 行 + 4 行；
9. 正文说 enrichment 展示 Top 12，但表格实际为 Top 10；
10. PCA 没有 sample_name 标签；
11. FastQ Screen legend 过于拥挤；
12. 1000 HVGs 主图信息密度过高；
13. Volcano plot 因 pvalue=0 的视觉处理被拉到约 300；
14. DEG Top table 上下调混排；
15. Methods 页面文字密度较高；
16. P22 架构图字号过小；
17. P21 SHA256 表格可读性一般；
18. PDF metadata 的 Title / Author / Subject / Keywords 为空；
19. 当前 PDF 仍然明显依赖自然流式分页，而不是语义化布局；
20. 当前报告缺少真正产品化的 Executive Summary。

---

# 总目标

建立：

```text
Content
  ↓
Semantic Report Blocks
  ↓
Layout Planning
  ↓
Quarto / Typst Rendering
  ↓
PDF Validation
```

而不是：

```text
Markdown
  ↓
Quarto
  ↓
Typst
  ↓
hope for good pagination
```

---

# 第一阶段：只读调查

## 严格要求

第一阶段禁止修改源码。

调查：

```text
report.rna.pdf.json
RNA-seq QMD
Jinja2 templates
shared themes
Typst configuration
figure utilities
table utilities
renderer
CLI
configuration schema
PDF metadata
TOC/bookmark generation
HTML/PDF rendering path
```

重点回答：

### 1. 分页到底由谁控制？

明确：

```text
Jinja2
Quarto
Markdown
Typst
Lua filter
CSS
Python renderer
```

各自负责什么。

---

### 2. Figure 当前是什么数据结构？

判断当前是否只是：

```python
path
caption
```

还是已经存在：

```python
FigureBlock
```

---

### 3. Table 当前是什么结构？

检查是否支持：

```text
keep_together
repeat_header
page_break
continuation
```

---

### 4. Heading 当前如何处理？

重点检查 orphan heading。

---

### 5. HTML 与 PDF 是否共享同一个布局模型？

如果共享，需要判断：

> 哪些内容应该共享，哪些 layout strategy 必须分离。

---

### 6. 当前 Top N 如何实现？

特别调查：

```text
enrichment figure top_n
enrichment table top_n
caption top_n
summary top_n
```

为什么出现：

```text
正文 = 12
图 = 12
表 = 10
```

---

### 7. 当前 pvalue=0 如何处理？

追踪：

```text
input pvalue
→ transformation
→ plot
→ axis
```

不得直接修改原始 CSV。

---

### 8. 当前 PDF metadata 如何设置？

确认：

```text
Title
Author
Subject
Keywords
Creator
```

在哪里生成。

---

## 第一阶段输出

生成：

```text
docs/bioreport-pdf-layout-audit.md
```

至少包括：

```text
Current Architecture
Pagination Pipeline
Figure Pipeline
Table Pipeline
Template Structure
PDF Renderer
Known Root Causes
Risk Assessment
Recommended Refactor
```

然后暂停，不修改实现。

---

# 第二阶段：建立 Semantic Report Block

调查完成后开始实施。

不要直接把所有 Markdown 继续交给 Typst。

建立最小语义模型：

```text
Report
Section
Paragraph
MetricGrid
TableBlock
FigureBlock
FigureGroup
CalloutBlock
MethodBlock
ProvenanceBlock
AppendixBlock
```

---

# Block 最低接口

每个 Block 应能够表达：

```text
id
type
content
keep_with_next
keep_together
preferred_height
minimum_height
page_break_before
page_break_after
layout_priority
```

不要过度设计。

优先采用现有代码结构扩展。

---

# 第三阶段：P0 Pagination Fix

## 1. Cover

最终：

```text
Page 1 = Cover
```

禁止任何 orphan heading 出现在 Cover 前。

---

## 2. Heading

规则：

```text
Heading
+
至少第一段
```

尽量保持。

实现：

```text
keep_with_next = true
```

---

## 3. Figure

必须保证：

```text
Figure
+
Caption
```

同页。

---

## 4. FigureGroup

支持：

```text
FigurePair
FigureTriplet
FigureGrid
```

例如：

```text
FastQ Screen R1
+
FastQ Screen R2
```

视为一个 FigureGroup。

---

## 5. Small Table

小表：

```text
keep_together = true
allow_split = false
```

这必须解决：

```text
P4 sample table
+
P5 remainder
```

以及：

```text
P19 enrichment table
+
P20 remainder
```

---

## 6. Large Table

只有真正无法整体容纳的大表才允许拆分：

```text
repeat_header = true
continuation = true
```

---

# 第四阶段：Executive Summary

当前 Project Overview 已经有：

```text
Sample count
Group count
Mean Q30
Mean mapping rate
Detected genes
DEG summary
```

将其升级成：

```text
Executive Summary
```

推荐：

```text
Metric Cards
+
Statistical Highlights
+
Data Scope
```

例如：

```text
Samples             6
Groups              2
Mean Q30            95.86%
Mean Mapping        99.04%
Detected Genes      16,289
DEGs                7,069
```

---

# AI 解读规则

如果 AI 没启用：

```text
Objective Statistical Summary
```

如果 AI 启用：

```text
Evidence-grounded Interpretation
```

AI 内容必须明确标记：

> Auxiliary interpretation; not a replacement for statistical evidence.

不要让 AI 自动把 GO term 写成未经证据支持的机制结论。

---

# 第五阶段：Methods 重构

当前 Methods 页面文字密度较高。

增加：

```text
Analysis Workflow
```

推荐视觉：

```text
Raw Reads
   ↓
fastp
   ↓
FastQ Screen
   ↓
STAR
   ↓
RSEM
   ↓
DESeq2
   ↓
clusterProfiler
```

然后：

```text
Software | Version | Function
```

详细方法保留，但降低视觉权重。

---

# 第六阶段：Figure 优化

## PCA

必须增加：

```text
sample_name
```

例如：

```text
1-1
1-2
1-3
2-1
2-2
2-3
```

颜色继续表示 group。

---

## FastQ Screen

legend 不应无限增长。

推荐：

```yaml
legend:
  min_fraction: 0.01
  max_categories: 5
  aggregate_other: true
```

但不要删除原始类别数据。

---

## HVG

主报告：

```text
Top 50 / Top 100
```

完整：

```text
Top 1000
```

放 supplementary / appendix。

具体默认值选择应基于当前模板可读性测试，不得仅凭主观判断。

---

## Volcano

原始：

```text
pvalue = 0
```

只允许在绘图层处理。

建议：

```yaml
volcano:
  y_axis:
    display_cap: 50
```

超过：

```text
50+
```

原始数据完全保留。

Caption 必须说明：

> Values exceeding the display range are clipped for visualization; original values are preserved in the result table.

---

## DEG Table

推荐：

```text
Top 5 Up
+
Top 5 Down
```

如果存在 gene symbol：

```text
Gene ID
Gene Symbol
log2FC
pvalue
padj
```

如果不存在 symbol：

不要伪造。

---

# 第七阶段：Enrichment Top N 一致性

建立唯一配置：

```yaml
enrichment:
  top_n: 12
```

所有地方必须使用同一个值：

```text
figure
table
caption
summary
```

最终必须消除：

```text
“展示前 12 个”
vs
“预览 10 / ...”
```

这种不一致。

---

# 第八阶段：Scientific Reporting Rules

当前 DEG threshold：

```text
raw p < 0.05
|log2FC| > 1
```

这是当前输入配置事实。

不要擅自改变分析结果。

但报告必须明确：

```text
display/significance criterion
```

与：

```text
FDR-controlled significance
```

的区别。

如果仓库已有 padj 配置，应允许：

```yaml
deg:
  pvalue_field: pvalue
  adjusted_pvalue_field: padj
  significance_field: padj
  significance_threshold: 0.05
  log2fc_threshold: 1
```

是否将默认策略切换为 padj，必须先调查 RNAFlow 当前正式定义，再决定。

---

# 第九阶段：Provenance

保留当前 SHA256 机制。

升级为：

```text
Report Manifest
Input Manifest
Artifact Manifest
Reproduction Manifest
```

每项至少：

```text
artifact
role
path
sha256
```

可增加：

```text
size
timestamp
```

但不要重复存储大量冗余信息。

Hash 使用 monospace。

---

# 第十阶段：PDF Metadata

自动设置：

```text
Title
Author
Subject
Keywords
Creator
```

示例：

```text
Title:
RNA-seq Transcriptome Analysis Report — PRJ-RNA-PDF-001

Author:
BioReport / CygnusX BioOps

Subject:
RNA-seq transcriptome analysis report

Keywords:
RNA-seq, transcriptomics, BioReport,
reproducible research, provenance

Creator:
BioReport v2.0.0
```

---

# 第十一阶段：Architecture Figure

当前 P22 架构逻辑保留，但重新设计视觉。

目标：

```text
Configuration
      ↓
Report Composition
      ↓
Analysis Results
      ↓
Renderer
   ↙       ↘
HTML      PDF
```

附：

```text
Optional AI
Provenance
Validation
```

禁止在 A4 页面中缩到无法阅读。

---

# 第十二阶段：Layout Validation

实现 PDF 生成后的自动检查。

至少检测：

## Page

```text
page_count
blank_pages
content_ratio
```

---

## Heading

```text
orphan_heading
```

---

## Figure

```text
figure_without_caption
caption_without_figure
```

---

## Table

```text
small_table_split
missing_header
single_row_continuation
```

---

## Content

```text
top_n_consistency
sample_count_consistency
deg_count_consistency
enrichment_count_consistency
```

---

## Provenance

```text
metadata
sha256
generation_time
report_version
```

---

# 第十三阶段：Visual Regression

至少建立：

```text
golden PDF
```

并对：

```text
Cover
TOC
Overview
QC
PCA
HVG
Volcano
Enrichment
Provenance
Architecture
```

生成截图。

如果环境允许：

```text
PDF → PNG
```

再进行视觉回归。

---

# 第十四阶段：HTML Regression

不要因为 PDF 优化破坏 HTML。

必须验证：

```text
HTML generation
HTML navigation
Plotly
ITables
TOC
```

特别注意：

> PDF 专用 layout 不应该污染 HTML 交互布局。

---

# 第十五阶段：不要做的事情

禁止：

1. 不调查源码直接修改；
2. 大量修改 margin/padding；
3. 通过缩小字体解决分页；
4. 通过强制 page break 填补布局问题；
5. 修改上游分析结果；
6. 修改原始 pvalue/padj；
7. 为了好看删除完整数据；
8. 为了减少页数把所有图压缩得不可读；
9. 把 AI 推断写成统计事实；
10. 破坏现有 HTML；
11. 新建一套与现有 renderer 完全平行的重复系统；
12. 引入不必要的大型依赖。

---

# 第十六阶段：优先复用现有能力

在修改前检查仓库是否已有：

```text
theme
figure helper
table helper
config schema
report registry
renderer abstraction
metadata builder
provenance utilities
validation utilities
```

如果已有能力：

> 优先扩展，而不是重新实现。

尤其避免出现：

```text
RNA PDF Layout Engine
+
ATAC PDF Layout Engine
+
WGS PDF Layout Engine
```

应该建立：

```text
Shared Report Layout Engine
```

然后各 omics module 只提供内容。

---

# 第十七阶段：推荐架构

目标结构：

```text
BioReport
│
├── report/
│   ├── model/
│   │   ├── section
│   │   ├── figure
│   │   ├── table
│   │   └── block
│   │
│   ├── layout/
│   │   ├── rules
│   │   ├── planner
│   │   └── page_policy
│   │
│   ├── render/
│   │   ├── html
│   │   └── pdf
│   │
│   └── validation/
│       ├── content
│       ├── layout
│       └── provenance
│
├── omics/
│   └── rna/
│       ├── content
│       ├── figures
│       └── tables
│
└── templates/
    ├── shared
    ├── html
    └── pdf
```

实际目录必须根据仓库现状调整，不得机械照搬。

---

# 第十八阶段：实施方式

请按以下顺序：

```text
Phase 0
Read-only audit

↓
Phase 1
P0 pagination

↓
Phase 2
Semantic blocks

↓
Phase 3
Layout planner

↓
Phase 4
Figure/table improvements

↓
Phase 5
Scientific presentation

↓
Phase 6
Provenance + metadata

↓
Phase 7
Validation + regression
```

每个阶段：

1. 修改；
2. 测试；
3. 重新生成 PDF；
4. 检查截图；
5. 输出变更说明。

---

# 第十九阶段：最终 PDF 目标

目标结构：

```text
1  Cover
2  Executive Summary
3  Project Overview
4  Methods & Software
5  Quality Control
6  Expression Analysis
7  Differential Expression
8  Functional Enrichment
9  Provenance
10 Delivery & Reproduction
11 References
```

不强制固定页数。

目标：

> 每页都具有明确阅读目的，同时避免明显无意义留白。

---

# 第二十阶段：最终验收

生成：

```text
docs/bioreport-pdf-layout-refactor.md
```

必须包含：

```text
1. Audit findings
2. Root causes
3. Architecture changes
4. Files changed
5. Layout rules
6. Figure/table changes
7. Scientific presentation changes
8. Provenance changes
9. PDF metadata changes
10. Validation results
11. Before/after page comparison
12. Remaining known issues
```

最终输出必须明确：

```text
PDF:
PASS / FAIL

HTML:
PASS / FAIL

Content validation:
PASS / FAIL

Layout validation:
PASS / FAIL

Scientific consistency:
PASS / FAIL

Provenance:
PASS / FAIL
```

如果任何一项 FAIL：

> 不要声称“全部完成”。

---

# 最重要的最终原则

BioReport 的目标不是：

> “生成一份看起来漂亮的 PDF”。

而是：

> **生成一份结构清晰、统计口径明确、视觉可读、证据可追溯、能够复现并适合作为科研交付物的报告。**

最终架构应该体现：

```text
Research Results
      ↓
Evidence
      ↓
Semantic Report
      ↓
Controlled Layout
      ↓
Reproducible Rendering
      ↓
Validated Delivery
```

并与 CygnusX BioOps 的整体理念：

> **科研发现 → 受控计算 → 证据沉淀 → 项目交付 → 可验证复现**

保持一致。
