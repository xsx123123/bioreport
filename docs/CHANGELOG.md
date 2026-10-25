# Changelog

本项目的重要变更记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- 比较组标签页改为可横向滑动的胶囊样式标签条（桌面与移动端一致）：当比较组数量超过阈值（默认 10，`report.comparison_search_threshold` 可调，设 0 关闭，兼容旧的 `comparison_fold_threshold`）时，标签条右侧出现带组数的搜索按钮，点击展开下拉面板按名称过滤，回车选中第一个匹配，选中后自动切换标签并滚动到可见位置；DEG 表格/火山图与 GO/KEGG 富集的比较组统一使用此样式，PDF 版式不受影响。
- HTML 页脚使用提供的 BioReport 与 Quarto 图标，保留版本和生成时间，支持离线图片资源、窄屏换行和深色主题。
- HTML 差异基因表与火山图支持离线联动：搜索后点击基因旁的“定位”，自动切换到对应比较组并高亮目标，支持返回表格和清除标记；按基因 ID 匹配，保留表格搜索、排序、分页与原始值导出，中英文模板同步接入。
- 交互图表支持配色切换：分组图（PCA、表达分布、MultiQC 质控等）右上角 Palette 下拉可在 seaside/apple/IBM/candy 四套色板间切换；连续色带图（聚类热图、相关性热图、富集气泡图）Scale 下拉可切换 Viridis/Blues/Cividis/RdBu_r/RdYlBu/Portland；按钮为静态 JSON payload，离线 HTML 可用，导出图片中自动隐藏。
- 图表下载的 PNG 按 1000 DPI 高清渲染并写入 pHYs 元数据，输出宽高为布局尺寸的 1000/96 倍，下载框显示实际输出尺寸（输出单边上限 16000 px、总像素上限 1.28 亿）；导出图片中自动隐藏 Palette/Scale 切换按钮；切换按钮带主题化悬停动画与中英文 tooltip。
- 终端在 PDF DEG/富集模块下显示实时子进度：并行绘图完成数、按原顺序写入报告的结果数、当前比较组及 GO/KEGG 上下调标识；独立进度文件避免等待 Jupyter 输出刷新，富集无结果/缺失/未启用项也计入写入进度。
- PDF DEG、GO/KEGG 富集结果使用独立工作进程读取、筛选、绘图并导出 SVG，默认 8 个工作进程；主进程按原顺序输出图表、预览表、AI 解读和证据清单。
- 新增 `report.pdf.workers` 配置及 `--workers`、`-t`、`--threads` 命令行参数；设为 1 可串行处理，命令行设置覆盖配置文件。
- 限制预取任务数量和工作进程内的 BLAS/OpenMP 线程数，任务失败时回收工作进程与临时文件；补充串行/并行图像和证据一致性测试。

### 修复

- 修复离线 HTML 报告图表与表格永久停留在“将在进入视野时加载”：Quarto `embed-resources` 序列化会丢弃空 `<script>` 的闭合标签，把随后的图表注册脚本/表格初始化模块吞成不可执行的文本；暂存载荷脚本内写入占位符保持非空，1132 个图表与 1128 张表格恢复进入视野即加载。
- 修复单语 HTML 交付时共享载荷块插错位置：`str.lower()` 会把 İ (U+0130) 展开为两个码点导致索引后移，`</body>` 被拆开、浏览器丢弃载荷块并报“报告数据不可用”；改为大小写不敏感正则在原文上定位。
- HTML 单文件报告移除 Quarto 预留的底部空白行和正文上下多余间距，短页面页脚贴齐视口底部，长页面滚动到页脚结束，并限制上下边界滚动回弹。
- HTML 致谢更新为华中农业大学园艺林学学院基因组实验室，英文页面同步更新。
- 修复 HTML 报告中 RequireJS 截获 PDF 转换库加载，导致图表下载提示“导出失败，请重试或减小尺寸”；转换库直接注册报告专用全局对象，兼容离线报告中的 AMD 环境。
- 网页图表 PDF 下载改为 SVG 直接转换的矢量 PDF，保留线条和可检索文字，并嵌入中文字体；修复原先以低分辨率位图嵌入 PDF、放大模糊的问题。转换库随报告打包，支持离线下载。
- 旧格式配置（无显式 `enrichment` 块）下富集结果显示"未提供结果"：自动发现在原有 `{比较名}_{UP|DOWN}.csv` 之外，支持按数据库拆分的交付命名 `{比较名}_{GO|KEGG}_{UP|DOWN}*.csv`（如 `Salt_A_vs_WTSalt_KEGG_UP_enrichments.csv`），按数据库各生成一条结果；旧命名行为不变。
- 富集气泡图的 Count 图例圆点大小不再全部相同：px.scatter 默认 `legend.itemsizing='constant'` 会压平图例符号，且 plotly 图例按 marker.size 像素值绘制（上限约 16px）；现在以 ∝√Count 的像素直径绘制并设 `itemsizing='trace'`，图例圆点按数值成比例且升序排列。
- PDF 密集散点层以 400 dpi 嵌入 SVG，保留全部点位、矢量坐标轴和标注；续表检测按表格查询首行，跳过已确定超高图表组合的重复测量，降低大量差异分析和富集结果排版时的内存开销；布局校验查询超时延长至 10 分钟。
- Quarto 失败日志包含退出码及信号提示；失败项目保存在输出目录，已完成 Python 执行的 Typst 文档可直接重试排版。
- 大量比较组的封面显示数量和前三组示例，避免元数据挤出封面；完整结果仍保留在正文。PDF 导航校验复用已读取的页面文本，避免重复解析整份文档。
- 样本图分面图注明确本面板与全部样本的数量、完整覆盖及非随机抽样；覆盖度图注明源样本数与汇总曲线数。中英文正文增加样本表与 TPM 样本范围核对，列出未匹配项，不自动修改分析样本范围。

## [0.2.1] - 2026-10-23

### 修复

- fastp、FastQ Screen、QualiMap、STAR 质控输入路径缺失或未配置时，显示缺失提示并继续生成其余报告内容。
- 统一输入校验、中英文 HTML/PDF 和网站报告的质控跳过逻辑；FastQ Screen 的 R1 或 R2 缺失时跳过整个污染检测子节。
- 在日志、溯源信息和报告清单中记录跳过项，并跳过对应的 AI 解读和 PDF 方法描述。
- 保留核心分析输入及已有路径类型、读取权限的严格校验，补充缺失输入场景的回归测试。

### 变更

- 报告引擎版本调整为 0.2.1。

## [2.0.1] - 2026-10-20

### 新增

- 双语（中文/英文）RNA 报告版本与语言切换。
- 报告运行历史、搜索和 Workspace v1 证据浏览能力（[#6337bec](https://github.com/xsx123123/bioreport/commit/6337bec)）。
- 按结果的 AI 解读与 HTML Plotly PNG 导出规范（[#39c5be8](https://github.com/xsx123123/bioreport/commit/39c5be8)、[#d227236](https://github.com/xsx123123/bioreport/commit/d227236)）。
- 静态 Mermaid 预编译、离线字体、Plotly 运行时本地缓存与共享网站输出，提升离线交付能力和 HTML 加载性能。
- HTML 表格精度控制、表达式表格渲染与报告资源审计能力。

### 变更

- 建立版本校验、CHANGELOG 和 GitHub Actions 发布流程。
- 完善 PDF 语义布局、字体、封面、报告溯源和项目文档（[#2d5ea98](https://github.com/xsx123123/bioreport/commit/2d5ea98)、[#b4a603a](https://github.com/xsx123123/bioreport/commit/b4a603a)）。
- 优化报告主题、导航与交付目录结构。
- 报告引擎版本更新至 2.0.1。

## [2.0.0] - 2026-10-15

这是配置驱动架构的重大版本更新（Beta）。

### 新增

- 配置驱动的报告引擎，统一支持 JSON/YAML 配置、模块编排和自定义 QMD 模块。
- HTML 和 Typst PDF 双格式报告交付，支持交互式图表与离线资源。
- RNA-seq 报告模块，覆盖质控、样本关系、表达、差异表达和富集结果。
- AI 配置接口、报告溯源清单、内置字体、PDF 排版和报告完整性校验能力。
- Docker 部署草稿和可扩展的共享模板目录。

### 变更

- 共享模板和核心引擎从 RNA 专属路径迁移到通用 BioReport 架构。
- 报告文件名统一为 `<project_id>_report.<格式>`，旧版配置仍由配置加载器兼容。

### 移除

- 旧版演示产物和旧布局不再参与当前生成路径，保留内容移入 `archive/`。

## 历史版本

- `v0.0.1`（2026-01-13）：项目初始化与 Quarto 报告原型（[#53d2bf3](https://github.com/xsx123123/bioreport/commit/53d2bf3)）。
- `v0.0.2`（2026-01-14 至 2026-01-15）：RNA-seq 报告、配置更新和 Web/火山图改进。
- 2026-01-27 的 `v0.0.3` 提交未形成 Git tag，因而不作为已发布版本列出。

[Unreleased]: https://github.com/xsx123123/bioreport/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/xsx123123/bioreport/releases/tag/v0.2.1
[2.0.1]: https://github.com/xsx123123/bioreport/releases/tag/v2.0.1
[2.0.0]: https://github.com/xsx123123/bioreport/releases/tag/v2.0.0
