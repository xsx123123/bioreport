# BioReport PDF 产品级优化评审报告

**评审对象**：`report(1).pdf`  
**报告类型**：RNA-seq 转录组分析报告  
**报告规模**：23 页  
**生成引擎**：BioReport v2.0.0 / Typst 0.13.0  
**评审日期**：2026-10-16  
**评审性质**：PDF 成品审查 + 信息架构/科研表达/渲染系统优化建议

---

## 0. 评审结论

这份 PDF 已经具备比较完整的科研报告骨架：

> 项目概况 → 方法与软件 → 质量控制 → 表达分析 → 差异表达 → 富集分析 → 溯源 → 交付说明 → 参考文献

并且已经具备 BioReport/CygnusX 很有价值的几个特征：

- 配置驱动报告；
- 上游分析与报告渲染解耦；
- 软件版本记录；
- 输入文件路径映射；
- SHA-256 数据完整性指纹；
- HTML/PDF 双输出思路；
- 可选 AI 解读；
- 报告模块化组织。

因此，**当前主要问题不是“缺少分析内容”，而是“报告编排系统还没有产品化”**。

当前可以概括为：

> **数据/结果层：8–9/10**  
> **科研内容组织：7.5–8/10**  
> **视觉设计：6.5–7/10**  
> **PDF Layout / Pagination：5/10**  
> **交付产品感：6–6.5/10**

最终建议不是继续局部调 CSS，而是建立：

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

也就是把 **Report Layout System** 作为 BioReport 的正式能力。

---

# 1. 审查范围与证据边界

本次结论直接基于已生成的 23 页 PDF，包括：

- 页面正文；
- 表格；
- Figure；
- Figure caption；
- TOC；
- 页眉/页脚；
- 报告架构图；
- 溯源页；
- PDF metadata。

PDF 实际信息包括：

- 6 个样本；
- 2 个实验分组；
- 平均 Q30 95.86%；
- 平均比对率 99.04%；
- TPM > 1 检出基因 16,289；
- 2_vs_1：上调 4,364，下调 2,705；
- 23 页输出；
- PDF metadata 中 Title / Author / Subject / Keywords 为空；
- PDF creator 为 Typst 0.13.0；
- PDF 书签/outline 共 22 个条目。

**注意：**

本报告可以确定“成品表现出了什么问题”，但不能仅凭 PDF 断言具体源码位置。以下内容分为：

- **已验证事实**：PDF 中直接观察到；
- **根因假设**：需要进入仓库调查确认；
- **实现建议**：建议的架构方向，不代表当前仓库一定采用了该方式。

---

# 2. P0 核心问题总表

| ID | 问题 | PDF 证据 | 优先级 | 处理 |
|---|---|---|---|---|
| L01 | 首页出现孤立“样本信息” | P1 | P0 | 必须修 |
| L02 | Cover 被推迟到 P2 | P2 | P0 | 必须修 |
| L03 | 样本表跨页，仅 P5 剩余 5 行 | P4–P5 | P0 | 必须修 |
| L04 | 图表与章节出现明显断裂 | P9–P12 | P0 | 必须修 |
| L05 | 小表格被无意义拆页 | P19–P20 | P0 | 必须修 |
| L06 | 富集分析声明 Top 12，但表格实际 Top 10 | P17–P20 | P0 | 必须修 |
| L07 | 页面存在大面积无效留白 | 多页 | P0/P1 | 必须修 |
| L08 | Section heading 可能与核心 figure 分离 | P14–P15 | P1 | 必须修 |
| L09 | PCA 没有 sample_name 标签 | P13 | P1 | 建议修 |
| L10 | FastQ Screen legend 过长 | P10–P11 | P1 | 建议修 |
| L11 | HVG 1000 基因主图信息密度过高 | P15 | P1 | 建议修 |
| L12 | Volcano plot y 轴最高达到约 300 | P16 | P1 | 必须优化 |
| L13 | DEG Top 表上下调混排 | P16 | P1 | 建议修 |
| L14 | Methods 文字密度偏高 | P6 | P1 | 建议重构 |
| L15 | 架构图字号过小 | P22 | P1 | 必须优化 |
| L16 | SHA256 表格不够适合阅读/复制 | P21 | P2 | 优化 |
| L17 | PDF metadata 不完整 | PDF metadata | P2 | 修复 |
| L18 | Executive Summary 不够产品化 | P4 | P1 | 升级 |

---

# 3. 逐页问题审查

## 3.1 Page 1：孤立标题页

### 已验证事实

P1 几乎只有：

> 样本信息

随后是大量空白。

P2 才是真正 Cover：

> CygnusX BioOps  
> RNA-seq 转录组分析报告

### 判断

这是典型的 orphan heading / page-break 问题。

### 目标

最终 PDF 应：

```text
P1 Cover
P2 Contents / Executive Summary
P3 Project Overview
```

不能再出现孤立章节标题。

---

# 4. Page 4–5：样本表分页问题

P4 已经包含：

- 项目概况；
- 核心指标；
- DEG 摘要；
- 样本表第一行。

P5 又只剩：

- 其余 5 个样本；
- 样本预览说明。

### 判断

这是最典型的 Table Block 没有整体布局能力。

### 推荐规则

对于小表：

```text
keep_together = true
```

如果整张表无法放入剩余空间：

```text
move entire table to next page
```

而不是：

```text
first row → current page
remaining rows → next page
```

---

# 5. Page 6：Methods 信息密度过高

当前页面是连续长段落：

- QC 方法；
- Fastp；
- FastQ Screen；
- STAR；
- Qualimap；
- RSEM；
- DESeq2；
- clusterProfiler；
- 软件版本。

### 当前问题

内容本身完整，但阅读模式接近技术说明书。

### 推荐改为

```text
Analysis Workflow
      ↓
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

再放：

```text
Software / Version / Function
```

详细方法进入：

```text
Methods
```

或 Appendix。

---

# 6. Page 7–12：QC 分页系统需要重构

当前：

- P7：Fastp 文字 + 表格；
- P8：Figure 1 + Figure 2；
- P9：Figure 3 + 3.2 开头；
- P10：Figure 4；
- P11：Figure 5 + 3.3 开头；
- P12：Figure 6 + STAR table。

### 核心问题

很多页面只有一张图，下面有大量空白。

尤其：

- P10 基本是 Figure 4；
- P11 基本是 Figure 5；
- P9 Figure 3 后只剩少量章节文字。

### 推荐布局

#### Fastp

```text
3.1 Fastp QC

Metric Summary Table

Figure 1
Figure 2
Figure 3
```

按照图形实际高度自动：

```text
FigureGroup
```

组合。

#### FastQ Screen

```text
3.2 External Contamination

R1 + R2
```

两个方向应该视为一个：

```text
FigurePair
```

而不是两个独立 Figure。

#### Alignment QC

```text
3.3 Qualimap
Figure 6

3.4 STAR
STAR summary table
```

---

# 7. Page 13–15：表达分析

## 7.1 PCA

P13 的 PCA 图使用 group 颜色，但没有直接显示：

```text
1-1
1-2
1-3
2-1
2-2
2-3
```

### 推荐

每个点：

```text
● 1-1
● 1-2
● 1-3
```

颜色继续表示 group。

这样能够直接发现：

- 离群样本；
- 组内重复一致性；
- 组间分离。

---

## 7.2 HVG

P15 的 Figure 9 为：

> Top 1000 HVGs

对于 6 个样本来说，1000 行主图视觉密度非常高。

### 推荐

主报告：

```text
Top 50 / Top 100 HVGs
```

补充材料：

```text
Top 1000 HVGs
```

不要删除完整结果，只降低主报告的信息密度。

---

# 8. Page 15–16：DEG 分析

## 8.1 Volcano Plot

当前原始 p-value 存在：

```text
pvalue = 0
```

报告通过：

```text
p + 1e-300
```

避免数学无穷大。

这在计算上可以稳定绘图，但造成：

```text
-log10(p) ≈ 300
```

因此纵轴被拉到 300。

### 视觉问题

大量点集中在顶部区域。

### 推荐

使用：

```text
display_cap = 50
```

或配置化：

```text
volcano.y_axis.max = 50
```

超过范围的点：

```text
50+
```

或使用顶部箭头/裁剪标记。

**不得修改原始 p-value。**

caption 明确：

> Values exceeding the display range are clipped for visualization; original values are preserved in the result table.

---

## 8.2 DEG Preview

当前 Top 10 完全按 pvalue 排序。

推荐：

```text
Top 5 Up-regulated
+
Top 5 Down-regulated
```

如果存在 gene symbol：

```text
Gene ID
Gene Symbol
log2FC
pvalue
padj
```

---

# 9. Page 17–20：Functional Enrichment

这是当前最明显的内部一致性 bug。

正文写：

> 优先展示前 12 个功能条目。

但：

P18：

> 预览 10 / 3788 行

P20：

> 预览 10 / 4323 行

### 必须统一

建立单一配置：

```yaml
enrichment:
  top_n: 12
```

然后所有地方从该配置读取：

```text
Figure = top_n
Table = top_n
Caption = top_n
Summary = top_n
```

禁止：

```text
figure_top_n = 12
table_top_n = 10
caption_top_n = 12
```

---

## P19–P20 表格拆页

P19 只有部分 10 行表格，P20 剩余 4 行。

必须禁止这种情况。

---

# 10. 图表系统优化规范

## 10.1 Figure Block

每个 figure 应被视为：

```text
Figure
├── Title
├── Image
├── Caption
└── Data source
```

整体不可随意拆开。

---

## 10.2 Figure Group

支持：

```text
FigurePair
FigureTriplet
FigureGrid
Figure + Table
```

例如：

```text
FastQ Screen
├── R1
└── R2
```

---

## 10.3 Caption

统一结构：

```text
Figure N. Title.

Description.
Axes.
Color encoding.
Filtering / statistical settings.
Data source.
```

不要把所有解释塞入正文。

---

# 11. FastQ Screen Legend 优化

当前图例列出了大量物种。

如果实际占比很小：

```text
Mouse
Multiple Genomes
```

已经足够。

推荐配置：

```yaml
legend:
  min_fraction: 0.01
  max_categories: 5
  aggregate_other: true
```

完整数据仍保留在原始交付文件。

---

# 12. Table System

建立：

```text
TableBlock
```

属性：

```yaml
keep_together: true
repeat_header: true
allow_split: false
max_rows_on_page: ...
compact: true
```

大表才允许：

```yaml
allow_split: true
repeat_header: true
continuation_label: true
```

小表禁止拆分。

---

# 13. 信息架构升级

推荐最终 PDF：

```text
01 Cover

02 Executive Summary

03 Project Overview
   ├── Project Information
   ├── Core Metrics
   ├── DEG Summary
   └── Sample Information

04 Methods & Software
   ├── Analysis Workflow
   └── Software Versions

05 Quality Control
   ├── Fastp
   ├── FastQ Screen
   ├── Qualimap
   └── STAR

06 Expression Analysis
   ├── PCA
   ├── Expression Distribution
   ├── HVGs
   └── Expression Matrix Preview

07 Differential Expression
   ├── Volcano Plot
   └── DEG Summary

08 Functional Enrichment
   ├── Up-regulated
   └── Down-regulated

09 Provenance

10 Delivery & Reproduction

11 References
```

目标不是机械压缩页数，而是：

> **每一页都有明确的阅读任务。**

---

# 14. Executive Summary 升级

当前 P4 已经有核心指标，但仍属于普通项目概况。

建议增加：

```text
EXECUTIVE SUMMARY

Samples                6
Experimental groups    2
Mean Q30               95.86%
Mean mapping rate      99.04%
Detected genes         16,289
DEGs                    7,069
```

然后：

### Statistical Highlights

- 4,364 up-regulated genes；
- 2,705 down-regulated genes；
- 上调富集条目主要来自当前输入结果中的相关功能类别；
- 下调富集结果显示多个 extracellular matrix / migration / angiogenesis 相关条目。

注意：

如果没有 AI 解读，不要自动写成机制结论。

可以使用：

```text
Objective Statistical Summary
```

启用 AI 后才增加：

```text
Evidence-grounded Interpretation
```

并明确 AI 是辅助内容。

---

# 15. 科研统计与科学表达审查

## 15.1 DEG 阈值

当前报告使用：

```text
raw p < 0.05
|log2FC| > 1
```

这是当前配置事实。

但正文将其表述为：

> “显著性判定阈值”

建议报告 UI 明确区分：

```text
Differential expression display threshold
```

与：

```text
FDR-controlled significance threshold
```

如果项目没有配置 padj 阈值，不要在报告中暗示这是 FDR 控制后的“显著 DEG”。

建议将统计策略完全配置化：

```yaml
deg:
  pvalue_field: pvalue
  significance_field: padj
  significance_threshold: 0.05
  log2fc_threshold: 1
```

默认策略是否切换到 padj，需要结合 RNAFlow 的正式分析定义决定，不能由报告引擎擅自改变。

---

## 15.2 Enrichment

当前：

```text
p.adjust < 0.1
```

应明确这是：

```text
enrichment filtering threshold
```

不要与 DEG 阈值混为一谈。

---

## 15.3 客观结果与自动解释分离

推荐三层：

```text
Observed
↓
Statistical Summary
↓
Optional Interpretation
```

而不是：

```text
Observed
↓
BioReport automatically concludes mechanism
```

这一点与 BioReport 的 provenance-aware 定位一致。

---

# 16. Provenance 页面升级

当前 P21 是整个报告非常有价值的一页。

已有：

- Project ID；
- Report Engine；
- Generation Time；
- Report Modules；
- Pipeline Version；
- SHA-256。

建议升级为：

| Artifact | Role | Path | SHA256 | Size |
|---|---|---|---|---|
| sample.csv | Sample metadata | ... | ... | ... |
| TPM matrix | Expression | ... | ... | ... |
| DEG result | Differential expression | ... | ... | ... |

Hash 使用：

```text
monospace
```

并允许复制。

---

# 17. Delivery Manifest

P22–P23 当前已经开始建立：

> 数据目录 → 报告模块 → 输入文件

建议进一步统一为：

```text
Report
│
├── Report Manifest
├── Input Manifest
├── Analysis Manifest
├── Artifact Manifest
└── Reproduction Manifest
```

这样可以直接与 CygnusX 的：

```text
Case
Artifact
Evidence
Manifest
```

体系对接。

---

# 18. Architecture Figure

P22 的架构图逻辑是正确的：

```text
JSON/YAML
    ↓
Module Registration
    ↓
Temporary Quarto Project
    ↓
Quarto/Jupyter
    ↓
Result Reading
   ↙     ↘
HTML    PDF
```

但当前在 A4 页面中字号过小。

### 建议

减少节点数量，突出：

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

然后补：

```text
Optional AI Interpretation
Provenance
Validation
```

如果图需要展示完整工程架构，应独立占较大面积。

---

# 19. PDF Metadata

当前 PDF metadata：

```text
Title: empty
Author: empty
Subject: empty
Keywords: empty
Creator: Typst 0.13.0
```

建议自动生成：

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

# 20. Layout Engine 设计

建议不要继续依赖：

```text
Markdown → Typst 自动流式分页
```

而建立：

```text
Report AST
```

例如：

```python
Report(
    sections=[
        Section(
            id="overview",
            blocks=[
                MetricGrid(...),
                TableBlock(...),
            ]
        ),
        Section(
            id="qc",
            blocks=[
                FigureGroup(...),
            ]
        )
    ]
)
```

Block 类型：

```text
SectionBlock
ParagraphBlock
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

# 21. Layout Rules

建议建立统一规则：

## Heading

```text
keep_with_next = true
```

## Heading + Intro

尽量保持。

## Figure

```text
keep_with_caption = true
```

## FigureGroup

整体布局。

## Small Table

```text
keep_together = true
```

## Large Table

```text
repeat_header = true
```

## Page Break

只允许：

```text
Section start
Major report front matter
Appendix
Explicit user request
```

禁止：

```text
random page break
```

---

# 22. 页面利用率

建立 PDF post-render validation。

建议：

```text
min_content_ratio = 0.55
```

如果某页内容面积明显低于阈值：

```text
warning
```

如果：

```text
orphan heading
single-row continuation
empty page
```

则：

```text
ERROR
```

注意：

不能机械要求所有页面填满。

Cover、TOC、References、Architecture 等页面可以例外。

---

# 23. 最终推荐的实施顺序

## Phase 0 — Audit

只读：

- 模板；
- QMD；
- Jinja2；
- Typst；
- renderer；
- config；
- figure/table utilities。

输出：

```text
docs/bioreport-pdf-layout-audit.md
```

---

## Phase 1 — P0 Pagination Fix

解决：

- P1 orphan；
- Cover 顺序；
- sample table；
- figure/caption；
- enrichment table；
- empty page；
- section/figure separation。

---

## Phase 2 — Semantic Block

建立：

```text
FigureBlock
FigureGroup
TableBlock
SectionBlock
CalloutBlock
```

---

## Phase 3 — Visual System

统一：

- typography；
- spacing；
- figure width；
- caption；
- table；
- legend；
- page header；
- footer；
- color semantics。

---

## Phase 4 — Scientific Presentation

优化：

- PCA labels；
- volcano cap；
- DEG preview；
- HVG top N；
- enrichment top N；
- FastQ Screen legend。

---

## Phase 5 — Provenance & Delivery

建立：

- Input Manifest；
- Artifact Manifest；
- Report Manifest；
- PDF metadata；
- reproduction information。

---

## Phase 6 — Regression

每次生成：

```text
HTML
PDF
```

都运行：

```text
content validation
layout validation
visual validation
provenance validation
```

---

# 24. 验收标准

最终至少通过：

### Structural

- [ ] 无空白 orphan page
- [ ] Cover 为第一页
- [ ] TOC 页码正确
- [ ] PDF bookmarks 正常
- [ ] heading 无孤立
- [ ] figure/caption 不分离
- [ ] small table 不拆页
- [ ] table continuation 合法

### Content

- [ ] Top N 全部来自单一配置
- [ ] figure/table/caption 数量一致
- [ ] 样本数量一致
- [ ] DEG 数量一致
- [ ] enrichment 数量一致
- [ ] 软件版本一致
- [ ] 数据路径一致

### Scientific

- [ ] 原始统计值不改变
- [ ] pvalue=0 只做视觉处理
- [ ] DEG threshold 明确
- [ ] enrichment threshold 明确
- [ ] AI interpretation 与 objective results 分离

### Visual

- [ ] PCA 有 sample labels
- [ ] Volcano 不被极端 p-value 拉伸
- [ ] legend 不拥挤
- [ ] HVG 主图可读
- [ ] 架构图字号可读
- [ ] 页面无明显异常留白

### Provenance

- [ ] SHA256 完整
- [ ] input path 完整
- [ ] report version 完整
- [ ] generation timestamp 完整
- [ ] PDF metadata 完整

---

# 25. 最终产品定位

BioReport 不应该成为：

> “把 QMD 自动转成 PDF 的工具”。

应该成为：

> **A provenance-aware, configuration-driven scientific reporting engine for reproducible omics analysis.**

最终架构建议：

```text
Upstream Analysis
       │
       ▼
Normalized Results
       │
       ▼
Report Configuration
       │
       ▼
Semantic Report Model
       │
       ▼
Layout Planner
       │
       ├──────────────┐
       ▼              ▼
HTML Renderer      PDF Renderer
       │              │
       ▼              ▼
Interactive       Print-ready
Report            Scientific Report
       │              │
       └──────┬───────┘
              ▼
       Provenance Layer
              │
              ▼
       Reproduction Manifest
```

这会使 BioReport 真正成为 CygnusX BioOps 的“科研交付层”，而不仅是一个 PDF 模板。

---

# 26. 一句话总结

当前 PDF 最大的问题不是“内容不够”，而是：

> **内容已经达到科研报告级别，但 Layout Engine 仍停留在自动排版级别。**

下一轮工作的核心不是继续微调字体，而是建立：

> **Semantic Blocks → Layout Planner → Renderer → PDF Validation**

这将同时解决当前 PDF 的分页问题、空白问题、图表问题、表格问题，并为后续 RNA / ATAC / WGS / scRNA / 多组学报告复用提供统一基础。
