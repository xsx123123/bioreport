# BioReport RNA-seq 报告样式优化实现计划

> 版本：v1（2026-10-21）
> 范围：Quarto 生成的 BioReport RNA-seq HTML 报告——比较组 tab 切换样式 + 富集表通路名称列宽。
> 性质：**对已有报告的样式优化，不是重新设计**。改动集中在 1 个自定义 CSS 文件 + 富集表 R 代码块的 options。

---

## 1. 背景与目标

BioReport 报告由 Quarto 渲染（Bootstrap 5 主题），顶部为页面导航（项目概述 / 样本信息 / 分析概述 / 质量控制 / 分析结果 / 溯源信息 / 关于），支持深色模式切换。「分析结果」页内：

- 差异表达分析（Volcano）与富集分析结果使用 Quarto `.panel-tabset` 做比较组切换（6 个比较组：Salt_A_vs_WTSalt / Salt_B_vs_WTSalt / Salt_C_vs_WTSalt / Salt_A_vs_WT1Salt / Salt_B_vs_WT1Salt / Salt_C_vs_WT1Salt）；
- 富集结果表为 DT::datatable（带 复制 / CSV 按钮、分页、搜索），内层还有「上调(UP) / 下调(DOWN)」二级 tab。

目标：tab 切换有容器感与选中态、两级 tab 层级可区分；富集表 Description（通路名称）列加宽、长通路名不再折成 4 行。

## 2. 问题清单

| # | 位置 | 现状问题 | 严重度 |
|---|------|----------|--------|
| 1 | 分析结果页 比较组 tab（6 个） | Bootstrap 默认 nav 样式：未选中=蓝色下划线文字链接，选中=浅灰描边盒子；换行散落两行，无容器感 | 中 |
| 2 | 富集分析 二级 tab（UP/DOWN） | 与一级 tab 样式完全相同，层级看不出 | 中 |
| 3 | 富集结果表 Description 列 | 未设列宽，"negative regulation of endopeptidase activity" 折 4 行，行高被撑大，右侧数字列留白 | 高 |
| 4 | 深色模式兼容 | 新增样式若硬编码浅色，深色模式下会刺眼 | 需防回归 |

## 3. 技术路径

| 问题 | 修改点 | 机制 |
|------|--------|------|
| tab 样式 | 新增 `assets/report-style.css`，挂载到 `_quarto.yml` 或 YAML header `format: html: css:` | 覆写 `.panel-tabset` 的 Bootstrap nav 样式 |
| 表格列宽 | 生成富集表的 R 代码块中 `DT::datatable(options = list(autoWidth = TRUE, columnDefs = ...))` | DT 原生列宽控制；无法改 R 时用 CSS `nth-child` 兜底 |
| 深色模式 | CSS 变量或 `[data-bs-theme="dark"]` 选择器 | Quarto/Bootstrap 5.2+ 内置暗色主题钩子 |

## 4. 分阶段实现

### 阶段 1：tab 切换样式（轨道式 pill）

1. 定位渲染 tabset 的 DOM 结构与 class（`.panel-tabset > ul.nav > .nav-item > .nav-link`）。
2. 新建/追加自定义 CSS 并挂载：
   - 一级容器：`background: #f1f3f5; border-radius: 10px; padding: 4px; gap: 4px; display: flex; flex-wrap: wrap;`
   - tab 项：去下划线去边框，`border-radius: 8px; padding: 6px 14px; font-size: 14px; color: #495057;`
   - 选中态：白底 + 主色文字（`#1e6fff`）+ `font-weight: 600` + `box-shadow: 0 1px 3px rgba(0,0,0,0.12)`
   - hover：`rgba(255,255,255,0.6)` 过渡 `all .2s ease`
3. 二级 tab（UP/DOWN）降一级：容器透明、tab 更小（13px / 4px 12px），选中态用主色下划线或浅填充；DOM 无法区分两级时给二级 tabset 容器加自定义 class（如 `.tabset-sub`）。
4. 窄屏 <768px：容器 `overflow-x: auto; flex-wrap: nowrap`，禁止孤行贴边。

### 阶段 2：富集表列宽

1. 首选改 R：`DT::datatable(options = list(autoWidth = TRUE, columnDefs = list(list(width = '380px', targets = <Description 列索引>))))`；Description 单元格 `white-space: normal; line-height: 1.5`。
2. 数字列（GeneRatio / BgRatio / RichFactor / FoldEnrichment / p.adjust 等）固定 90~120px 并右对齐，让出宽度；ID 列 `nowrap`。
3. 兜底（表为流水线产物改不了 R 时）：表容器加 class + `td:nth-child(2) { min-width: 360px; }`（注明脆弱性）。
4. 统一表格字号 13~14px，行 hover 浅底色 `rgba(0,0,0,0.03)`。

### 阶段 3：深色模式与回归检查

1. 所有新增颜色走 CSS 变量，`[data-bs-theme="dark"]` 下 tab 轨道用 `#212529` 系、选中态用 `#2b3035`。
2. 全页面（项目概述/样本信息/分析概述/质量控制/分析结果/溯源信息/关于）回归检查。

## 5. 给编码 Agent 的提示词

```text
你是一名资深前端工程师，熟悉 Quarto HTML 报告（Bootstrap 5 主题）与 R DT::datatable。

任务：在现有 BioReport RNA-seq Quarto 报告模板基础上做样式优化。先阅读现有代码
（.qmd 报告模板、_quarto.yml 或 YAML header、已有 CSS 主题文件、生成富集表格的
R 代码块），理解当前实现后再修改。禁止推倒重写，禁止改动报告结构、分析逻辑和无关
页面。这是对已有报告的优化，不是重新设计。

## 问题 1：比较组切换 tab 样式太素、层级不清

现状：分析结果页「差异表达分析 / 富集分析」的比较组切换（Salt_A_vs_WTSalt 等
6 个）使用 Quarto .panel-tabset 默认样式：未选中是蓝色带下划线的文字链接，选中
只有一个浅灰描边盒子，换行后散落两行，无容器感；富集表内层「上调(UP)/下调(DOWN)」
二级 tab 与一级样式完全相同，层级看不出。

修改 spec（写入自定义 CSS，如 assets/report-style.css，并在 _quarto.yml 或 YAML
header 的 format: html: css: 中挂载）：
1. 一级 tab 容器改「轨道式 pill」：.panel-tabset > ul.nav 加
   background: #f1f3f5; border-radius: 10px; padding: 4px; gap: 4px;
   display: flex; flex-wrap: wrap;
2. tab 项 .nav-link：text-decoration: none; border: none; border-radius: 8px;
   padding: 6px 14px; font-size: 14px; color: #495057;
3. 选中态 .nav-link.active：background: #ffffff; color: #1e6fff;
   font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,0.12);
4. hover 态：background: rgba(255,255,255,0.6); transition: all .2s ease;
5. 二级 tab（UP/DOWN）视觉降一级：容器背景透明，tab 更小（font-size: 13px;
   padding: 4px 12px），选中态用主色下划线或浅填充，与一级区分；若两级 tab 的
   DOM 无法区分，在 R/Quarto 输出处给二级 tabset 容器加自定义 class
   （如 .tabset-sub）再写 CSS。
6. 窄屏（<768px）tab 容器允许横向滚动（overflow-x: auto; flex-wrap: nowrap），
   不允许出现孤行单 tab 贴边。

## 问题 2：富集表 Description（通路名称）列太窄

现状：GO/KEGG 富集结果表（DT::datatable，带 复制/CSV 按钮与搜索）中 Description
列过窄，"negative regulation of endopeptidase activity" 折成 4 行，行高被撑大，
右侧数字列大量留白。

修改 spec（首选改 R 代码，CSS 仅作兜底）：
1. 在生成富集表的 DT::datatable 调用中加 options：autoWidth = TRUE，
   columnDefs = list(list(width = '380px', targets = <Description 列索引>))；
   Description 单元格 white-space: normal; line-height: 1.5;
2. 数字列（GeneRatio/BgRatio/RichFactor/FoldEnrichment/p.adjust 等）设较窄固定
   宽度（90~120px）并右对齐，把省下的宽度让给 Description；
3. ID 列（GO:0010951 这类）white-space: nowrap;
4. 若表格是流水线产物无法改 R 代码，CSS 兜底：给该表容器加 class，
   table td:nth-child(2) { min-width: 360px; }（注明 nth-child 脆弱，仅兜底）；
5. 顺手统一：表格字号 13~14px，行 hover 加浅底色 rgba(0,0,0,0.03)。

## 全局约束

- 深色模式（页面右上角有切换）下两套样式都要正常：用 CSS 变量或
  [data-bs-theme="dark"] 覆盖，tab 轨道深色下用 #212529 系，不能出现刺眼白块；
- 不动火山图 plotly、不动侧边导航、不动其他页面；
- 改动集中在 1 个 CSS 文件 + 富集表 R 代码块的 options，最小化改动面。

## 验收标准

- [ ] 6 个比较组 tab 呈轨道式 pill 容器，选中/hover 态明确，换行整齐
- [ ] UP/DOWN 二级 tab 与一级有明显层级差
- [ ] Description 列至少 350px，长通路名不超过 2 行折行
- [ ] 深色模式下 tab 与表格可读、无刺眼白块
- [ ] 其余页面（项目概述/质量控制/样本信息等）无样式回归

完成后简述：每个问题对应的修改文件与关键属性改动。
```

## 6. 人工验收对照表（用户手测）

| 操作 | 期望现象 | 不通过时的处理 |
|------|----------|----------------|
| 打开报告 → 分析结果 → 差异表达分析 | 6 个比较组 tab 在灰色轨道容器内，选中项白底蓝字有阴影 | 检查 CSS 是否挂载（YAML `css:` 路径）、选择器是否命中实际 DOM class |
| 切换任意比较组 tab | 选中态平滑过渡，无下划线 | 检查 `.nav-link` 的 `text-decoration` 与 `transition` 是否生效 |
| 富集分析结果 → 切换 UP/DOWN | 二级 tab 明显比一级小/淡，层级可辨 | 检查 `.tabset-sub` 自定义 class 是否加到二级 tabset 容器 |
| 富集表查看 Description 列 | 宽度 ≥350px，长通路名 ≤2 行 | 改 R 的查 columnDefs targets 索引是否正确（DT 索引从 0 开始，含 rownames 需 +1）；兜底 CSS 的 nth-child 是否指对列 |
| 右上角切深色模式 | tab 轨道、选中态、表格均不刺眼 | 检查 `[data-bs-theme="dark"]` 覆写是否完整 |
| 浏览其余 6 个页面 | 无样式变化 | 检查 CSS 选择器作用域是否过宽（应限定在分析结果页或 tabset 相关 class） |

## 7. 风险与注意

- **DT columnDefs 的 targets 索引**：DT 从 0 开始计列，且若 datatable 输出了行名（rownames），行名占第 0 列，Description 的实际索引要相应 +1——这是最常见的"设了列宽没生效"原因。
- **Quarto 版本差异**：旧版 Quarto 深色模式钩子可能是 `body.quarto-dark` 而非 `[data-bs-theme="dark"]`，施工时先确认实际渲染出的 class。
- **选择器命中**：Quarto tabset 依配置可能渲染成 `nav-tabs` 或 `nav-pills`，CSS 两类都要覆盖，或统一指定。
