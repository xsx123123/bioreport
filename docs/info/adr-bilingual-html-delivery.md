# ADR: RNA-seq 双语 HTML 交付改为共享资源网站包

- 状态：已采纳，分阶段实施中（决策见《BioReport双语HTML性能优化实施手册》0.2；2026-10-20）
- 日期：2026-10-20
- 范围：RNA-seq HTML 双语报告；PDF 和分析计算逻辑不在本 ADR 的修改范围内

## 背景

当前 `report.layout: single` 分别通过 Quarto 生成两份完整、自包含的语言版 HTML，再用 gzip + Base64 将两份文件装进第三个 HTML。现有样例的最终文件为 60,286,093 bytes；浏览器需要解码并解压当前版本，语言切换时再重新构建 iframe。该样例中单语言 HTML 约 67.7 MB，23,076 行差异表达表约 20.94 MB，CJK 字体约 16.42 MB，Plotly 初始化脚本约 12.05 MB。

本机 Playwright Chromium 复测 `file://` 下中文显示约 10.57 秒、英文切换后约 8.93 秒达到内容显示；此前约 23 秒的英文切换观测未能稳定复现。时间会随报告和运行环境变化。

当前 `website` 方案也不满足目标：中文和英文由两套项目分别渲染，字体、Quarto 资源与 Plotly runtime 有重复；生成的字体 CSS 含错误绝对路径。现有网站 ZIP 可以打开目录，但 Chromium 的 `file://` 会阻止 Quarto ES modules。轻量 PoC 已验证单一 Quarto website 可输出 `index.html`、`zh/report.html`、`en/report.html`，并由两种语言页面共用一个 `site_libs`、静态 CSS/JS 和字体；通过本地 HTTP 服务时，PoC 资源请求正常，直接 `file://` 也能读取普通 CSS、JS 和字体。

## 提案

将 RNA-seq 双语 HTML 改为一个 Quarto Website Project，输出一个可压缩为 ZIP 的静态网站包：

```text
<project>_report/
├── index.html
├── zh/...
├── en/...
├── site_libs/
├── assets/
└── serve-report.py   # 或等价启动入口，形式待确认
```

`index.html` 是轻量语言入口。中英文页面使用普通相对链接互相切换，并尽量保留对应章节锚点。两种语言页面在同一次 Quarto website 项目构建中输出，共享一份 `site_libs`、字体、主题、图标及本地 Plotly runtime，不再将整份 HTML 放入外层文件。生成入口不包含两份完整报告。

页面交互和数据按以下方式保留：

- Plotly runtime 作为一份本地静态资源随包交付，图表页面引用它；不依赖 CDN。
- Plotly 图表、轴标签、悬浮信息、下载能力及现有交互保持不变。测量后再判断是否延迟初始化非首屏图表，或将确定不需交互的图改为静态图。
- 完整 DEG 数据和表格功能保持不变。先评估将数据放入本地 JSON/CSV，在 Results 页面或表格区域打开时再由客户端读取；保留排序、分页、搜索、复制和导出。服务端分页不作为离线默认方案，因为它需要持续可用的后端。
- 保留现有模块内容、品牌、导航、主题、结果来源和可复现生成流程；PDF 输出保持独立路径。

ZIP 离线查看通过随包服务入口或文档化本地服务命令启动。直接 `file://` 双击入口不能作为验收方式，因为 Chromium 会阻止 Quarto 的 ES modules。最终打包需验证服务入口不访问外网、所有依赖来自 ZIP。

## 考虑过的方案

| 方案 | 优点 | 代价/限制 | 结论 |
| --- | --- | --- | --- |
| 保留一个自包含双语 HTML，只减少部分数据 | 双击打开简单，现有交付延续 | 字体、图表 runtime 和 HTML 资源仍需内嵌；语言切换仍处理完整 HTML；不实现共享依赖 | 不建议作为目标架构 |
| 保留现有两套 website 输出后拼目录 | 改动较小 | 已实测有大量重复资源、字体路径错误；不满足共享资源要求 | 拒绝 |
| 一个 Quarto website 项目输出双语页面和共享资源 | 首屏轻、页面按需进入、静态资源可共享；Quarto PoC 已验证项目依赖共享 | 需重构页面源路径、导航、资源相对路径；离线运行需要本地 HTTP 服务；Plotly/Itables 自定义载荷需单独改造 | 采用，待实施验收 |

## 兼容与迁移

`report.layout` 目前表示报告布局，不宜继续同时表达交付文件形态。实施时需定义清楚新的配置/产物命名，并更新 CLI 摘要、README、测试和调用方。建议新产物为 `<project_id>_report.zip`，解压后的入口为 `index.html`；若决定改成直接输出目录而非 ZIP，也应在日志中列出实际目录。

由于当前单文件 `_report.html` 的交付会变更，迁移说明需记录旧、新产物名称，附启动命令和程序化调用调整示例。是否在一个过渡版本保留显式 legacy 单 HTML 选项、或在主版本直接切换，需要产品决策；迁移不能静默覆盖同名产物。

## 已确认的迁移决策（2026-10-20）

1. 默认 RNA-seq HTML 交付迁移为单一 Quarto website ZIP，接收方通过本地 HTTP 启动。
2. 显式 `report.layout: single` 保留至少一个大版本，发出弃用提示，下一主版本再移除。
3. 使用 Python 标准库 `serve-report.py` 启动服务并自动开浏览器，同时提供 Windows / macOS / Linux 等价命令。不引入新服务依赖。

以上来自配套性能手册 0.2 的已确认默认策略；实现与用户最终验收分别记录。

## 验收要求

- 单次 Quarto website 构建生成入口、中英文页面及完整 ZIP；入口载入轻量，不包含两个语言版全文。
- 两种语言内容、图表、表格、导航、品牌与锚点通过浏览器回归。
- `site_libs`、字体、主题资源、图标和 Plotly runtime 的共享数量经产物清点确认；不存在意外绝对路径或外网资源请求。
- 完整 DEG 行数、搜索、排序、分页、复制、导出都通过真实浏览器操作确认。
- 通过 ZIP 解压后的本地 HTTP 入口验证断网运行、无严重控制台错误；若直接 `file://` 不支持，README 明确说明。
- 报告压缩/未压缩体积、生成耗时、中文/英文首显、Results 首次打开和表格首次可操作时间，与本 ADR 背景基线对照。
- 迁移说明和实际中英文输出一同交付。

## 验证材料

- 现状和性能剖析：[`bilingual-html-performance-investigation.md`](bilingual-html-performance-investigation.md)
- 单项目 Quarto 共享资源与字体路径 PoC：`/tmp/bioreport-quarto-shared-poc`
- 当前双独立 website 对照产物：`/tmp/bioreport-website-investigation/site`

本 ADR 已采纳；状态不代表网站包迁移已实现或已通过用户验收。以性能手册的逐阶段证据为准。
