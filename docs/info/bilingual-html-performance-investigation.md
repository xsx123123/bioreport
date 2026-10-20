# 双语 HTML 报告性能排查与架构评估

日期：2026-10-20  
状态：Stage 0 调查与 Stage 1 方案建议；未修改报告生成逻辑。

## 结论

当前 RNA-seq `single` HTML 的实现是“先生成两份完整的 Quarto 单文件报告，再把两份 HTML 分别 gzip + Base64 后装入第三个 HTML”。打开后，浏览器解码并解压中文版到 iframe；切换英文时再对英文版重复处理并重建 iframe。它实现了单文件交付和离线交互，但启动和切换成本都随整份报告增长，切换并非只替换少量翻译文本。

当前样例的合并 HTML 为 **60,286,093 bytes（约 57.5 MiB）**。在本机 Playwright Chromium 的 `file://` 复测中，中文 iframe 约 **10.57 秒**显示；切换到英文约 **8.93 秒**显示。等到所有 Plotly 图表有 `_fullLayout` 且出现 Itables 容器后，中文约 **10.58 秒**、英文约 **8.94 秒**达到本次交互检查条件。上一轮观测到的英文切换约 23 秒没有在本次重测中复现，故不作为稳定基线。实际耗时会受浏览器、磁盘、CPU 和报告数据规模影响；若持续停留，应另查浏览器错误或资源限制。

## 可直接用于搜索的问题描述

我们用 Quarto 分别渲染中英文两份完整的自包含 HTML，再将它们 gzip + Base64 放进同一个外层 HTML；浏览器用 JavaScript 解码、`DecompressionStream` 解压，并通过 iframe `srcdoc` 显示当前语言。最终 HTML 约 60 MB，首次显示约 10 秒，语言切换在本机复测约 9 秒（另一次观测约 23 秒，尚未稳定复现）；其中包含 Plotly 图表、约 2.3 万行的 Itables 差异表达表和内嵌字体。希望保留完整数据、图表/表格交互与离线使用，比较共享资源的双语 Quarto website、按页面/语言延迟加载，以及静态离线大表的客户端处理方案。

可用检索词：`Quarto bilingual report slow self-contained HTML iframe srcdoc gzip Base64`、`Quarto website multilingual shared assets offline`、`large offline HTML table lazy loading client-side pagination DataTables`。若考虑 DataTables server-side processing，应同时检索其 Ajax 后端要求，因为该模式不适用于纯静态离线 HTML。

## 现状实现

`render_report` 对 RNA-seq 且 `report.layout: single` 设置 `paired_html`。CLI 分别以中文和英文配置运行 Quarto，得到两份 HTML；英文渲染结束后调用合并函数，写入最终 `<project_id>_report.html` 并删除中间两份文件。见 `bioreport/cli.py` 的 `paired_html`、render job 和 merge 分支。

单文件模板使用 `embed-resources: true`，将 Quarto 的本地资源并入每个语言版本。合并逻辑位于 `bioreport/i18n.py::combine_language_editions`：两份 HTML 各自 gzip 后再 Base64 编码，放进外层 HTML 的两个 `application/octet-stream` script 节点。浏览器端对当前版本调用 `atob`、逐字节拷贝、`DecompressionStream('gzip')`，再把解压后的完整 HTML 赋给 `iframe.srcdoc`。语言切换会重新跑这条路径，没有缓存已解压版本。

调用链可以概括为：

```text
RNA-seq single HTML
  -> Quarto render zh (embed-resources=true)
  -> Quarto render en (embed-resources=true)
  -> gzip + Base64 两份完整 HTML
  -> 一个外层 HTML
  -> 浏览器解码/解压当前语言
  -> iframe.srcdoc
```

## 体积来源与性能基线

对现有输出 HTML 的检查得到以下数据（这是当前样例，不是所有项目的固定值）：

| 项目 | 当前观测 |
| --- | ---: |
| 最终双语 HTML | 60.29 MB |
| 每个语言版本未压缩 HTML | 中文 67.71 MB；英文 67.66 MB |
| 每个版本 gzip 后 | 中文 22.32 MB；英文 22.30 MB |
| gzip 后再 Base64 | 中文 30.16 MB；英文 30.12 MB |
| HTML 内脚本总量 | 约 39.78 MB/语言 |
| 内联样式内容 | 约 23.58 MB/语言，其中一段字体样式约 23.23 MB |
| CJK 字体原始数据 | 约 16.42 MB/语言（HarmonyOS Sans regular + bold） |
| Plotly 初始化脚本（含图表配置与数据） | 19 个调用，约 12.05 MB/语言；最大单图约 5.22 MB；Plotly runtime 约 4.85 MB |
| Mermaid runtime | 约 2.67 MB/语言 |
| 差异表达表 | 23,076 行；itables 序列化内容约 20.94 MB/语言 |
| 内嵌 data URI 图片 | 2 张，合计约 1.89 MB/语言；其余图片引用均为内嵌资源 |

以上分项之间有包含关系，不应直接相加：Plotly 初始化和 Itables 数据都计入 script 总量；字体计入 inline style。除双语重复外，差异表达页 `omics/rna/qmd/modules/results/deg.qmd` 将完整 DEG DataFrame 直接交给 `display_gene_expression_table(df_deg)`；该展示路径没有行数限制，当前样例的 23,076 行表数据因此在首次载入时进入 HTML。它是值得优先处理的单语言大块数据。其他表格、Plotly 图、字体和 Mermaid runtime 也有可测的体积，但需要在改造中区分“每个语言重复”“每个页面重复”和“单份数据本身很大”。

基线测试记录：

- 当前 `file://` 单文件复测（Playwright Chromium；从导航开始计时，内容时间以 loading overlay 隐藏为准，交互条件为全部 Plotly 图表有 `_fullLayout` 且存在 Itables 容器）：中文可见 10.57 秒、交互条件 10.58 秒；点击切换后英文可见 8.93 秒、交互条件 8.94 秒。先前一次约 23 秒的切换观测未重复出来，应视为波动/未复现数据。浏览器验证曾受 90 秒总超时限制，完整遍历所有页面和图表未完成；这不等同于报告本身加载失败。
- 当前代码生成的双语 website 实验（轻量测试数据）：两次独立语言渲染约 130.9 秒；目录约 155 MiB、98 个文件；压缩 ZIP 为 45,816,843 bytes（约 43.7 MiB）。当前方式将两个语言版本分别构建，发现 35 组同内容重复文件，字体、Quarto 资源、图标和主题资源均有重复。
- 单项目共享资源 PoC（Quarto 1.8.26，隔离在 `/tmp/bioreport-quarto-shared-poc`）：一次构建 `index.html`、`zh/report.html`、`en/report.html`；产物只有一个 `site_libs`（18 个文件），两种语言页面均引用同一份 CSS/JS 和字体，字体及脚本在 `file://` 下可读。Quarto 的 3 个 ES module 请求仍被 Chromium CORS 拦截；通过临时 HTTP 服务访问时模块及资源均返回 200，控制台无错误。PoC 使用 `zh-Hans` 后 Quarto 构建无语言包警告。它证明项目级 Quarto 资源可以共享，不代表 BioReport 模板已经完成兼容。
- 网站以 `file://` 打开时，Quarto ES module 受浏览器 CORS 限制，无法正常运行。改用临时本地 HTTP 服务后，英文 Results 页可以加载，Playwright 看到 Plotly runtime、12 个表格和 4 个 Itables 容器；不过字体 CSS 路径错误，仍产生 404（`/en/tmp/bioreport-website-investigation/site/en/fonts.css`）。这说明“把现有 website 目录压成 ZIP，再双击 index.html”目前不可用。若采用网站包，需要共享资源构建、修正相对资源路径，并提供本地 HTTP 打开方式或另行实现可 `file://` 的交付。

共享 Quarto 项目不会自动共享 BioReport 手动内联的 Plotly runtime。`bioreport/utils/render_output.py::show_figure` 每个独立页面都会输出一次约 4.85 MB 的 Plotly JS；现有 website 样例的 zh/en QC、Results 四个页面中实际各有一份，总计约 19.4 MB。目标方案要将此 runtime 写成单份包内静态 JS 并由含图表页面引用，继续保持完全离线；不能把它留在每个页面内，也不能改用 CDN。

## 产品约束

仓库 README 当前承诺 RNA-seq `single` 交付一个同时含中英文的 HTML；Plotly 和可搜索 Itables 表格离线可用。`report.layout: website` 是多页 HTML，两个语言版本分开，且不能和 PDF 输出组合。新方案要保留报告章节、图表和表格交互、主题与导航、可复现构建以及离线使用能力；如果交付从单个 HTML 改为 ZIP/目录，需明确用户如何打开、是否需要安装 Python、命令行消费者如何迁移，以及旧单 HTML 是否保留过渡期。

## 目标方案建议（待确认）

1. 将双语报告组织为一个 Quarto website 构建，中文和英文页面输出到同一个资源根目录（例如 `/zh/`、`/en/`），让两种语言共同引用一份 `site_libs`、字体、图标、主题资源和 Plotly runtime。PoC 已验证 Quarto 项目级资源可共享；不要继续运行两套互不相关的 website project 后直接拼目录，因为当前实验显示会重复资源。
2. 使用轻量语言入口页，不在入口载入两个完整报告。用户进入某一语言后才获取该语言页面；大章节保持独立页面。保留明确的中英文切换链接，并在切换时定位到对应章节。
3. 保留完整 DEG 数据与表格交互，但把 23,076 行数据移出首屏 HTML，考虑按需加载本地 CSV/JSON 数据并由表格组件分页、搜索和导出。需要实测 Quarto/Itables 的支持边界，再选实现方式，不能以截断数据换取速度。
4. 对字体和 Plotly/Mermaid 等资源做页面及语言维度的共享/按需策略。先用构建产物统计确认哪些资源能跨页面共用，再做优化；字体可进一步评估子集化，但要确认中文字符覆盖和 PDF/HTML 字体一致性。
5. 离线交付倾向于一个 ZIP 包，内容是本地 website + 启动脚本/清晰的本地服务命令。由于 Chromium 的 `file://` module 限制，不能把“ZIP 解压后双击首页”作为已满足的离线体验。若必须双击打开，则需要保留独立单 HTML 交付或设计非 ES module 的备选路径。
6. 迁移时显式定义配置与产物兼容策略：短期保留 `single-file` 交付选项并输出弃用提示，待消费者切换后再移除；或在主版本升级中直接切到 ZIP，并同步更新 CLI 产物命名、README、验证脚本和下游调用。默认策略需要产品侧确认。

官方资料核对后的实现取舍：Quarto website 项目可以统一渲染多份页面，并把页面引用的静态资源复制到站点输出；这为语言页面共享同一资源目录提供了基础，但不会自动把两个分别构建的站点去重。Quarto 的 `embed-resources` 用于自包含 HTML，适合单文件交付，却会把页面资源再放回每份 HTML。DataTables 服务端处理可避免一次把全部表格行交给浏览器，但必须有持续可访问的 Ajax 后端，因此不符合纯静态离线包；对离线方案应先测试“进入 Results 页时才读本地完整数据文件”的客户端处理路径。

代码可行性补充：`bioreport/modules.py::compose_report(..., website=True)` 已为每个生成页面写入语言初始化代码，页面由 Quarto 分别执行；因此可把两种语言的页面作为一个项目的不同源文件渲染。当前实现仍将两种语言生成到同名 `qmd/site-*.qmd`，由 `bioreport/cli.py` 两次渲染并分别输出到根目录和 `en/`，所以不能只把两个现有目录合并来获得共享依赖。实现前需要先让源文件拥有互不冲突的语言路径，统一一次 Quarto 项目的 render 清单、输出根目录和页面级切换链接；将 `show_figure` 的 Plotly runtime 改为包内共享静态文件；字体 CSS 改用项目内相对路径（PoC 已验证字体和 CSS 能跨两种语言引用）；并通过实际产物校验 `site_libs`/字体/Plotly 仅有一份且所有相对链接正确。

参考官方文档：

- Quarto website 项目与多页面输出：[Creating a Website](https://quarto.org/docs/websites/)、[Website Tools: Site Resources](https://quarto.org/docs/websites/website-tools.html)
- 单 HTML 资源内嵌行为：[HTML Basics: Self-contained](https://quarto.org/docs/output-formats/html-basics.html)
- 大表 Ajax/服务端处理前提：[DataTables: Server-side processing](https://datatables.net/manual/server-side)

建议的验收基线：报告生成时间、ZIP 未压缩/压缩大小、入口首屏时间、语言切换时间、Results 页打开时间、表格首次可搜索时间；用两种语言实测页面内容、导航和锚点、Plotly 交互、完整 DEG 行数/搜索/分页/导出；用断网浏览器和本地服务验证全部资源来自包内，且无关键控制台错误。记录与当前 60.29 MB 单文件及本次网站实验的指标对比。

## 参考实现位置

- `bioreport/cli.py`：双语报告渲染循环与单文件合并流程。
- `bioreport/i18n.py`：语言版本包装和 gzip/Base64 iframe 合并。
- `templates/_quarto-single.yml.j2`：单文件资源内嵌配置。
- `templates/_quarto.yml.j2`：多页 website 的非内嵌配置。
- `bioreport/renderer.py`、`bioreport/utils/font_stage.py`：将字体 CSS 写入输出目录并传给 Quarto；website 实验发现 CSS 使用绝对路径的问题。
- `omics/rna/qmd/modules/results/deg.qmd`、`bioreport/utils/visualize_utils.py`：DEG 表生成和表格展示。
- `README.md`、`docs/README.zh-CN.md`：现有单文件、双语、离线和 website 交付承诺。

## 调查边界

本次只检查了源码、现有生成产物，并在 `/tmp/bioreport-website-investigation` 生成了隔离的 website 对照样本和 ZIP；没有编辑应用代码，也没有改变现有输出。单文件计时来自本机 Playwright Chromium，网站包计时来自轻量测试数据。它们适合定位成本和比较架构方向，不构成不同硬件或真实大项目的性能保证。
