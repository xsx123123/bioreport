# BioReport HTML 报告视觉风格规范

> 记录日期：2026-10-24
> 适用范围：HTML 交互报告（单文件 / 双语版）的网页视觉系统，不含 PDF 排版（PDF 静态导出规范见文末第 8 节）。

本文档描述当前 HTML 报告的完整视觉体系：设计变量、布局、组件、深色模式、图表主题。所有规则均有对应源码实现，修改样式前先定位到对应文件。

## 1. 样式文件地图

| 文件 | 职责 |
| --- | --- |
| `templates/theme/bioreport.scss` | 主主题（Quarto 编译）：语义色板、字体、卡片、导航栏、About 页组件、深色模式覆盖 |
| `templates/theme/styles.css` | 运行时纯 CSS：`--br-*` 设计变量、表格/标签页/控件细节、图表容器 |
| `templates/theme/itables_saas.css` | DataTables 交互表格样式 |
| `templates/theme/report-pages.html` | 页面行为 JS：导航栏对齐、主题切换、语言切换、单页路由 |
| `bioreport/utils/plotly_style.py` | Plotly 图表统一主题（模板 + 下载配置） |
| `bioreport/utils/print_theme.py` | 分组色板与 PDF 静态导出（SVG）样式 |
| `bioreport/utils/fonts.py` | 内置字体栈与字体暂存 |

## 2. 设计变量

### 2.1 浅色语义色板（`bioreport.scss` 顶部 `scss:defaults`）

| 变量 | 值 | 用途 |
| --- | --- | --- |
| `$body-bg` | `#ffffff` | 页面底色 |
| `$body-color` | `#26364a` | 正文文字 |
| `$primary` | `#1d5fbf` | 主色（链接、激活态、卡片顶边） |
| `$primary-dark` | `#174ea6` | 悬停加深 |
| `$secondary` | `#63748a` | 次级文字 |
| `$border-color` | `#dbe4ee` | 边框 |
| `$success` / `$warning` / `$danger` | `#2d9c78` / `#d99024` / `#c94a5b` | 语义色 |
| `$surface` | `#f3f7fb` | 浅底表面 |

约定（scss 文件头注释强制）：全局组件只允许引用这些变量，禁止散落硬编码色值。

### 2.2 运行时变量（`styles.css`）

`--br-primary`、`--br-text`、`--br-muted`、`--br-border`、`--br-surface`、`--br-surface-soft`、`--br-surface-hover`、`--br-control-*`，以及标签页变量 `--br-tab-track/-text/-active/-accent/-hover/-shadow`。

### 2.3 深色卡片变量（`bioreport.scss` 深色覆盖块）

```
--br-card: #222a35            /* 卡片表面 */
--br-card-border: #3b4654     /* 卡片边框 */
--br-card-text: #e8eef7       /* 卡片主文字 */
--br-card-muted: #aab6c5      /* 卡片次级文字 */
--br-card-accent: #86b7fe     /* 卡片强调/链接 */
--br-card-badge-bg: rgba(134,183,254,.12)
--br-card-badge-border: #3f5a86
```

后续新增深色组件统一引用这组变量，不要再造新色值。

## 3. 字体

- 字体栈（报告网页与 Plotly 图共用）：
  `BioReport-Latin, BioReport-CN, Source Sans 3, HarmonyOS Sans SC, -apple-system, Segoe UI, Arial, sans-serif`
- `BioReport-Latin` / `BioReport-CN` 为内置字体，渲染时暂存并在 HTML 里以 `@font-face` 声明；单文件报告会做子集化（`bioreport/utils/html_fonts.py`）。
- Plotly 主题中的字体栈**不带引号**：带引号的字体名（如 `"Source Sans 3"`）会让旧版 kaleido 的 plotly.js 文本测量报错（`plotly_style.py` 注释有说明）。
- 正文字号 16px 基准，行高 1.65；标题字重 650，h1 2rem / h2 1.55rem / h3 1.2rem。
- 报告正文中英文混排：宽屏（≥1400px）下 `p, li` 限宽 62rem；不用 `ch` 限宽（CJK 下换行参差）。

## 4. 布局

### 4.1 Quarto 网格

页面使用 Quarto 默认 page-columns 网格：左侧目录列（TOC，`#quarto-sidebar-toc-left`）+ 正文列（`#quarto-document-content`，宽屏下约 1110px）+ 右侧预留 margin 列（本报告不使用）。页面上端留白 `body { padding-top: var(--report-navbar-height) }`，由 JS 实测导航栏高度写入。

### 4.2 导航栏对齐（2026-10-24 修复）

导航栏 `position: fixed` 全宽，但**内部内容与正文网格左右对齐**：

- `report-pages.html` 的 `alignNavbar()` 实测目录列左缘与正文列右缘，写入 CSS 变量 `--report-page-inset-left/right`（load/resize 时同步；TOC 隐藏时回退到正文列左缘）。
- `.report-navbar` 的 padding 使用这两个变量，JS 未生效前回退为 1280px 视口居中。
- 不要改回固定像素 padding—— Quarto 网格在不同视口下是动态计算的。

### 4.3 单页路由

`report-pages.html` 实现 `#锚点` 驱动的单页多章节切换（`.report-page` 显隐）、TOC 高亮、移动端汉堡菜单（≤1279px 导航栏降为 60px 高，链接收进抽屉）。

## 5. 组件

### 5.1 卡片

- **信息卡** `.report-info-grid > .info-card`：自适应网格（minmax 190px），左上图标（Bootstrap Icons 单色）+ 标签 + 值，白底细边框。
- **KPI 卡** `.report-kpi-grid > .kpi-card`：三列网格，中性卡 + 主色顶边 3px；指标异常时 `.kpi-danger` 改 danger 顶边 + 淡红底。数值 2rem / 字重 700 / `tabular-nums`。
- **About 页系列**：manifesto 引言卡（Georgia 衬线引用 + 左侧竖线装饰）、mission / feature / tech-role / roadmap / footer-note / footer-card 卡片，徽标（badge/pill/tag）用药丸形浅蓝底。
- 架构图（mermaid SVG）保持浅色画布：图内文字是烤进 SVG 的深色系，深色模式下不压暗（按图片惯例处理）。

### 5.2 表格

- 普通表格：表头 `#f3f7fb` 底 + `#29496f` 文字，居中，行间细分隔线。
- DataTables：同色系 + `itables_saas.css` 的控件细节；导出按钮（复制/CSV/Excel）在顶部左侧，搜索在右侧。

### 5.3 Callout

只保留语义色左边框（note=primary / tip=success / warning / important=danger），无阴影。Quarto 默认风格 callout 的头部在浅色下为浅蓝底，深色下压暗为 `--br-card`。

### 5.4 控件

`.report-control`（语言切换、主题切换、校徽链接）：36px 高、8px 圆角、细边框，悬停变 `$surface`。主题切换按钮用太阳/月亮 SVG 双图标切换。

## 6. 深色模式

- 开关：`document.documentElement.dataset.reportTheme = 'dark'`（同步 `data-bs-theme`），状态存 `localStorage('bioreport.report-theme')`，初始跟随系统 `prefers-color-scheme`。
- 实现方式：浅色主题编译结果 + `:root[data-report-theme="dark"]` 覆盖层（不是 Quarto 双主题编译）。
- 深色基底：页面 `#171c24`，三级表面 `#222a35`，边框 `#3b4654`，正文 `#d5dce6`，标题 `#e8eef7`，链接 `#86b7fe`。
- 覆盖范围（`bioreport.scss` 深色块）：导航栏、菜单、控件、表格（含 DataTables）、callout、全部卡片与徽标、`code`、TOC 链接。
- **新增组件时**：浅色写完就必须在同文件深色块补覆盖规则，引用第 2.3 节变量。

## 7. Plotly 图表主题（`bioreport/utils/plotly_style.py`）

所有交互图共用一套主题，绘图函数只声明自己的尺寸/图例等定制项：

- **入口**：`style_figure(fig, **layout)` 应用模板；`export_config(filename, height=, width=, scale=4)` 统一 PNG 下载配置（scale=4、去 logo、去 lasso 按钮、responsive）。
- **模板**：白底；网格 `#e4e8ed`；轴线/刻度 `#b4bec9`；文字 `#243746` / 次级 `#64748b`；标题左对齐 17px；图例透明无边框；悬停框白底 `#cbd5e1` 边框；colorbar 细条（14px）无外框。
- **分组色板**（`print_theme.PALETTES`，HTML 与 PDF 共用）：

  | 名称 | 色值 | 说明 |
  | --- | --- | --- |
  | `seaside`（默认） | `#8ecae6 #219ebc #023047 #ffb703 #fb8500` | 全部图的分组色 |
  | `apple` | `#ff3b30 #ff9500 #ffcc00 #4cd964 #5ac8fa #007aff #5856d6` | 备选 |
  | `ibm` | `#5B8DFE #725DEE #DD227D #FE5F00 #FFB109` | 备选 |
  | `candy` | `#9b5de5 #f15bb5 #fee440 #00bbf9 #00f5d4` | 备选 |

  切换方式：`group_palette(groups, palette='apple')`，或改 `PALETTE = PALETTES['seaside']` 的默认指向。
- **交互配色切换（updatemenus）**：分组图（PCA、分布小提琴图、交互 PCA、MultiQC 质控图、FastQ Screen 双面板）右上角带 `Palette: …` 下拉，可在四套 `PALETTES` 间切换；连续色带图（聚类热图、相关性热图、富集气泡图）带 `Scale: …` 下拉，可切换 Viridis / Blues / Cividis / RdBu_r / RdYlBu / Portland（当前色带恒排第一）。实现于 `palette_updatemenu()` / `colorscale_updatemenu()`，经 `style_figure(palette_menu=True)` / `style_figure(colorscale_menu='<当前色带>')` 开启：
  - 按钮 payload 是纯静态 JSON（`restyle` / `relayout` / `update`），离线 HTML 中可用，不依赖任何后端。
  - 分组切换保持"同组同色"（按基色去重后映射新色板）；小提琴图填充保留原 alpha；无显式颜色的 trace 依次接在已有颜色后分配。
  - px 图常把色带放在 `layout.coloraxis` 上，此时按钮用 `method='relayout'` 改 `coloraxis.colorscale`；trace 级 `colorscale` / `marker.colorscale` 则用 `restyle`；两者并存时合并为 `method='update'`。
  - 图例占位哑 trace（坐标全 None）会被跳过；重复调用 `style_figure` 时同类菜单先移除再追加，不会叠加。
  - 火山图不加切换：Up/Down/NS 是语义色，轮换会破坏含义。
  - 下拉按钮的外观与交互在 `bioreport/assets/js/plotly-export.js` 注入的 CSS 中统一：圆角 chip、悬停高亮（跟随 `--br-surface-hover` / `--br-primary`，深浅色自适应）、展开淡入动画、悬停显示中文/英文 tooltip；`@media print` 下隐藏。
  - 导出不含按钮：`Plotly.toImage` 会把 updatemenus 画进 SVG，导出对话框在截图前临时 `relayout(updatemenus=[])`、完成后恢复，因此 PNG/SVG/PDF 下载件中不会出现 Palette/Scale 按钮。
- **语义色不参与轮换**：火山图固定 Up `#ef4444` / Down `#3b82f6` / NS `#cbd5e1`，阈值虚线 `#8795a5`。
- **图表文字固定英文**（两个语言版本都不出现中文）：富集图 colorbar 恒为 `Adjusted P value`，FastQ Screen 百分比轴为英文标题。正文标题/图注仍跟随报告语言。
- 火山图版式：图例底部横向居中，图高 500。
- 热图关闭网格与轴线；PCA 双面板共享顶部水平图例（`legendgroup` 联动）。

已接入的图：PCA（`pca_plotly.py`）、表达分布小提琴图（`distribution_plotly.py`）、聚类热图（`plotly_heatmap.py`）、富集气泡图（`enrichment_plotly.py`）、火山图 / 相关性热图 / 交互 PCA（`plot_utils.py`）、MultiQC 质控图（`qc_vis.py`，含 FastQ Screen 双面板）。

## 8. PDF 静态导出（对照参考）

HTML 图在 PDF 中经 `print_theme.export_vector()` 用 matplotlib 重绘为 SVG（不是截图）：字号 10/9pt、去右上脊柱、轴线 `#b4bec9`、网格 `#e4e8ed`、色板与 HTML 完全一致（同源 `PALETTES`）；>1000 点的散图层栅格化（400dpi）嵌入 SVG 以控制内存；热图按 40 列分面板且不重聚类。改 HTML 图样式时，若涉及 trace 结构（新增图形类型），需同步检查 `export_vector` 的支持列表。

## 9. 修改样式的流程约定

1. 改色值 → 优先改语义变量（第 2 节），不改组件。
2. 新增组件 → 浅色 + 深色两套规则一起写，深色引用 `--br-card-*`。
3. 新增 Plotly 图 → 走 `style_figure()` + `export_config()`，分组色走 `group_palette()`；分组图传 `palette_menu=True`、连续色带图传 `colorscale_menu='<当前色带>'` 即获得右上角交互切换（语义色图不加）。
4. 验证：`python -m pytest tests/test_modules.py tests/test_report_layout.py` + 已有渲染产物用 Playwright 截图目检（参考 `scripts/verify_report_theme.py`）。
