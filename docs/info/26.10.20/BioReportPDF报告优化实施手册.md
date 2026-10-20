# BioReport PDF 报告优化实施手册

- 版本：v1.0（2026-10-20）
- 性质：活文档。同一主题后续迭代追加新 Part，不另起文档。
- 姊妹文档：《BioReport双语HTML性能优化实施手册.md》《BioReport报告页UI优化实施手册.md》。本手册针对 PDF（Typst）输出路径，与 HTML 路径独立，但图表生成函数（`bioreport/utils/visualize_utils.py` 等）是共享的——改图时注意两条输出路径都要回归。
- 评审依据：2026-10-20 对 `X101SC26098749-Z01-J001_report.pdf`（27 页）逐页渲染检查。

---

## 1. 问题清单（按严重度分级）

### A 级：正确性问题

| # | 位置 | 问题 |
| --- | --- | --- |
| A1 | 图 4-6 火山图 | 图注声称"为上调/下调各 Top 5 显著基因添加基因名引线标注"，实际图上无任何基因标注——图注承诺未兑现 |
| A2 | 图 4-4 / 4-5 高变异基因热图 | 聚类热图按样本列 1–12 / 13–15 拆成两图，第二张仅 3 列；聚类整体模式无法阅读，且 50 基因隐藏行名导致两图无法对应 |
| A3 | 4.4 节正文 vs 图 4-6 图注 | 正文写顶部标注"上限+"，图注与图实际为"50+"，同一页口径不一致 |
| A4 | 表 4-1 表达矩阵预览 | 8 行预览 6 行全零（按输入顺序取前 8 行），无信息量 |

### B 级：版面效率

| # | 位置 | 问题 |
| --- | --- | --- |
| B1 | 全报告图表 | 统一 12+3 拆分策略：图 3-1/3-2、3-3~3-6、3-7~3-10、3-11/3-12、4-2/4-3 的第二张都只有 3 个样本却占近一页，全报告浪费约 5~6 页；且把 Salt 组拦腰切断，割裂组间对比 |
| B2 | 第 7、9、10、12、14、16、20、23、26 页 | 半页以上空白，27 页可瘦到约 22~23 页 |
| B3 | 全部图注 | 零信息模板句"颜色与图例对应输入样本或统计类别"逐图重复；来源说明"质控图读取 MultiQC 保存的 fastp 汇总数据集……"在 QC 章节重复 4+ 次（第 7 页连续两次） |
| B4 | 图 3-11/3-12 QualiMap 覆盖曲线 | 15 条曲线完全重叠不可分辨；x 轴拉到 700X 但 100X 后全是贴地直线；图例 15 项占半页 |
| B5 | 图 3-7~3-10 FastQ Screen | R1/R2 × 两段拆分共 4 张，R1/R2 模式几乎一致，可合并 |

### C 级：细节打磨

| # | 位置 | 问题 |
| --- | --- | --- |
| C1 | 图 7-1 架构图 | 文字过小，A4 版面不可读 |
| C2 | 图 4-1 PCA | 左图标题与 Group 图例重叠；图例"AC1（组AC）"表述别扭，应为"AC1 (AC)" |
| C3 | 图 4-7/4-8 富集气泡图 | 中文报告内色标标签为英文"Adjusted P value" |
| C4 | 表 0-1 摘要统计表 | 表头"满足阈值差异基因"等折行挤压，列宽需调 |

---

## 2. 提示词 P-PDF（整段粘贴给编码 Agent）

```text
你是一名熟悉 Quarto + Typst PDF 排版的工程师。项目是基于 Python + Quarto 的生信报告
生成引擎 BioReport，PDF 由 Quarto/Typst 渲染，图表由 bioreport/utils/visualize_utils.py
等绘图函数生成，PDF 专用章节在 omics/rna/qmd/ 相关模块中。

任务：修复 PDF 报告的图表拆分与排版问题。先读现有代码（重点找图表按样本拆分的逻辑，
当前表现为每 12 个样本拆一段、15 个样本被拆成 12+3），理解实现后再改。禁止推倒重写，
禁止改动分析逻辑、统计口径与数据内容。图表生成函数同时服务 HTML 与 PDF 两条输出路径，
任何绘图函数改动必须两条路径都回归验证。

## A 级：正确性修复（必须全部完成）

1. 火山图基因标注兑现：图 4-6 图注声称有"上调/下调各 Top 5 显著基因引线标注"，
   实际图上没有。二选一：(a) 真正实现标注——按 pvalue 升序取上/下调各 Top 5，
   用带引线的文本标注（防重叠，如 adjustText 或手算偏移）；(b) 若静态图空间不足
   放弃标注，则删掉图注里这句承诺。优先 (a)，做不出再 (b) 并说明原因。
2. 聚类热图禁止拆分：高变异基因热图（图 4-4/4-5）是聚类结果的整体呈现，按样本列
   拆分后无法阅读。15 个样本列的 50 基因热图单页完全放得下——改为整图输出，
   尺寸适配版心宽度。为防未来超大项目，保留拆分逻辑但把热图类图加入"永不拆分"
   白名单；样本列超过页容量上限（如 >40 列）时才允许拆分，且必须按聚类后顺序
   连续切分、每张子图共享完整色标并显示行名。
3. 口径统一：4.4 正文"上限+"与图注"50+"统一为"50+"。全局搜索同类图注/正文
   不一致并一并修复。
4. 表达矩阵预览改有信息量的选行：表 4-1 当前按输入顺序取前 8 行、6 行全零。
   改为按全样本平均 TPM 降序取 Top 8（表注说明排序口径），展示列保持现有
   "前 6 样本 + 注明 6/15"的做法不变。

## B 级：版面效率（逐项完成）

5. 样本拆分策略重构：把当前固定 12 个/段的拆分改为按页容量动态判断——单图能放下
   就不拆。参考容量：横向条形图 ≤25 个样本、小提琴图 ≤20 个、折线图 ≤20 条曲线
   时一律不拆。确需拆分时按分组边界切（不把同一 group 切到两张图），并在每张
   子图保持一致的轴范围/色标。改完后本样例报告（15 样本）的所有图都应是单图。
6. 分页留白收敛：检查第 7、9、10、12、14、16、20、23、26 页的大面积空白。
   调整图表默认高度（当前明显偏高）与 Typst 的分页/keep 策略，目标：全书总页数
   从 27 页降到 ≤23 页，且无半页以上的非章节结尾留白。
7. 图注去重去噪：删除模板句"颜色与图例对应输入样本或统计类别"（零信息量）；
   "XX 读取 MultiQC 保存的 XX 汇总数据集；完整质控结果（数据目录内相对路径）：XX"
   这类来源说明改为每个小节只出现一次（小节末或首张图后），后续图不再重复。
8. QualiMap 覆盖曲线图改造：x 轴截断到 0–100X（图注注明截断）；15 条样本曲线
   改为"每分组均值曲线 + 分组色带（min–max 范围）"，图例只保留分组项（2 项），
   样本明细不再进图例。
9. FastQ Screen 合并：R1/R2 两段拆分共 4 张图，改为 R1/R2 双面板单图
   （上下或左右排列，共享图例），15 样本不拆分。

## C 级：细节（顺带完成）

10. 图 7-1 架构图：放大到版心全宽，提高字号权重，确保正文页可正常阅读；若 mermaid
    渲染分辨率不足，改导出高倍率 PNG/SVG 再嵌入。
11. PCA 图（图 4-1）：修复左图标题与 Group 图例重叠（图例外置顶部右侧或缩小
    标题字号）；图例标签"AC1（组AC）"改为"AC1 (AC)"。
12. 中文报告中富集气泡图色标"Adjusted P value"改为"校正后 P 值"；英文版保持英文。
13. 表 0-1 列宽调整：表头"满足阈值差异基因""padj<0.05 基因数""参与检验的基因总数"
    允许换行但不得挤压到相邻列，必要时缩短表头文案（如"检验基因总数"）。

## 验收标准（逐条自检）

- [ ] A1~A4 全部修复，火山图标注肉眼可见或图注承诺已删除
- [ ] 热图为单图，聚类模式完整可读
- [ ] 本样例报告不再出现任何"样本 13–15 / 15"式的孤儿子图
- [ ] 总页数 ≤ 23 页，无半页以上非章节结尾留白
- [ ] 同一来源说明在每个小节只出现一次
- [ ] HTML 输出路径重新生成一份报告，确认图表在 HTML 中无回归（交互、尺寸、图例正常）
- [ ] 提供改前/改后 PDF 页面对照截图

完成后简述：每个问题对应的修改文件与关键改动。
```

---

## 3. 验收 checklist（用户手测）

| 操作 | 期望现象 | 不通过时的处理 |
| --- | --- | --- |
| 翻到火山图（4.4 节） | 看到上/下调各 Top 5 基因名带引线标注；或图注已无此承诺 | 既无标注又留着承诺，打回 |
| 翻到高变异基因热图 | 单张完整热图，50 基因 × 15 样本一屏可读 | 仍拆成两图打回 |
| 对比 4.4 正文与火山图图注 | 裁剪标注口径一致（都是"50+"） | 不一致打回 |
| 看表 4-1 | 8 行都是有表达的基因，表注说明排序口径 | 仍全零行打回 |
| 快速翻全书 | 无"13–15 / 15"孤儿图；页数 ≤ 23；无半页以上空白 | 逐页记录问题页码让 Agent 修 |
| 读 QC 章节 | 来源说明每小节只出现一次；图注无"颜色与图例对应输入样本或统计类别" | 仍有重复打回 |
| 看 QualiMap 覆盖图 | x 轴 0–100X；均值+范围带；图例只有分组 | 仍 15 线重叠打回 |
| 看 FastQ Screen | R1/R2 双面板单图 | 仍 4 张图打回 |
| 看架构图（7.1 节） | 文字清晰可读 | 仍模糊打回 |
| 重新生成 HTML 版报告 | 图表交互与布局无回归 | 有回归说明绘图函数改坏了共享路径，打回 |

---

## 4. 与其他手册的协同

- 本手册的图表改动（拆分阈值、图注去重、QualiMap/FastQ Screen 重绘）落在共享绘图函数上，**HTML 报告会同步受益**：HTML 版同样存在 12+3 拆分与图注噪音。
- 与性能手册的关系：QualiMap/FastQ Screen 图数量减少也会降低 HTML 体积，与 Phase 1A 方向一致，不冲突。
- 施工顺序建议：本手册 P-PDF 可与性能 Phase 1 并行；若同一 Agent 会话施工，P-PDF 独立 commit。

---

## Part 2：实施与验收记录（2026-10-20）

### 2.1 实际修改

所有修改均位于报告展示、静态导出和模板层；保留原始 TPM、pvalue/padj、差异基因判定和聚类计算。

| 要求 | 实施文件 | 关键改动 |
| --- | --- | --- |
| A1 火山图标注 | `omics/rna/analysis/plot_utils.py`、`bioreport/utils/print_theme.py` | 保留 pvalue 升序、同值按绝对 Log2FC 降序的 Top 5 选择；引线锚点使用真实绘图坐标，修复静态导出遗漏 annotation；两侧分配独立标签位置，图例外置。 |
| A2 热图整体输出 | `bioreport/utils/print_theme.py`、中英文 PDF `modules/results/heatmap.qmd` | 热图加入独立容量策略，≤40 样本不拆；50 基因主图显示全部行名。超限采用均衡的连续切片，保留聚类后顺序、完整行名与整图色标。 |
| A3 裁剪口径 | 中文 PDF `modules/results/deg.qmd` | 默认上限说明统一为 `50+`，注明展示上限可配置；原始统计值不变。 |
| A4 表达预览 | `bioreport/utils/pdf_results.py`、中英文 PDF `modules/results/matrix.qmd` | 先按全样本平均 TPM 稳定降序，再选择前 6 个样本列、前 8 行；表注说明排序和 6/15 样本列范围。 |
| B1 动态容量 | `bioreport/utils/print_theme.py`、`omics/rna/analysis/qc_vis.py` | 横向柱图 25、分布图 20、折线图 20 的单页容量；超限按完整分组打包，保留统一数值轴范围；热图独立处理。 |
| B2 分页留白 | `templates/pdf/print-style.typ`、`templates/pdf/layout.lua`、`bioreport/utils/print_theme.py` | 降低普通图默认高度，按柱数估计横向图高度；图与题注保持完整，解除它们与后续段落的连锁粘连。较大的图表组合允许按独立图/表流动；标题仍保留首段。 |
| B3 图注与来源 | `omics/rna/analysis/qc_vis.py` | 删除零信息模板句；读取单层或唯一嵌套的 MultiQC JSON，避免逐图回退导致重复来源说明；回退路径也限制来源说明次数。 |
| B4 覆盖曲线 | `omics/rna/analysis/qc_vis.py`、`bioreport/utils/print_theme.py` | 保存的 coverage bin 上按分组计算均值/min/max；Plotly 和静态 SVG 均支持范围带；横轴 0–100X、图例仅分组，保留既有 0X 与纵轴刻度配置；HTML 单独预留标题、分组图例空间。 |
| B5 FastQ Screen | `omics/rna/analysis/qc_vis.py`、中英文 HTML/PDF `modules/qc/screen.qmd` | R1/R2 共用单图双面板；样本顺序、类别颜色、图例与数值范围一致；联合选择主要物种并将其余类别汇入 Other，原始 reads 总数保持不变；公共图例与 R1/R2 面板标题分层。 |
| C1 架构图 | `templates/shared/assets/architecture-print.zh.svg`、`architecture-print.en.svg`、中英文 PDF `about.qmd` | 增加版心全宽的打印专用矢量示意图，使用更大的半粗体文字，避免缩小复杂 Mermaid 图。 |
| C2 PCA | `omics/rna/analysis/pca_plotly.py`、`bioreport/utils/print_theme.py` | HTML 公共图例移至顶部右侧，PDF 子图图例与标题分层；悬停标识采用 `AC1 (AC)` 形式，保留样本坐标与分组。 |
| C3 富集色标 | `omics/rna/analysis/enrichment_plotly.py`、`bioreport/utils/print_theme.py` | 中文使用“校正后 P 值”，英文使用“Adjusted P value”；静态导出读取同一色标标题。 |
| C4 摘要表头 | `templates/pdf/print-style.typ` | 给长统计表头更宽的列，中文缩短为“阈值内差异基因”“检验基因总数”，保留表头换行与数值右对齐。 |

HTML 浏览器验收另修复两项离线兼容问题：`bioreport/i18n.py` 兼容旧式语言切换按钮；`templates/theme/report-pages.html` 让目录链接复用受保护的导航处理，避免 `about:srcdoc` 中 Quarto 的 `pushState` 越过浏览器的地址限制。`tests/report_editions.cjs` 与 `tests/report_navigation.cjs` 验证按钮/分段控件、切换缓存、历史地址异常回退与错误恢复。FastQ Screen 合并时同时移除了旧页签容器，确保后续章节保持独立。

### 2.2 可复现命令与产物

样例输入：`examples/X101SC26098749-Z01-J001/data`，15 样本、AC/Salt 两组。运行配置保存在 `output/pdf-optimization-20261020/config.json`，不启用远程 AI。

```bash
python -m bioreport run \
  -c output/pdf-optimization-20261020/config.json \
  -o output/pdf-optimization-20261020/final

python -m pytest -q

python tests/verify_pdf_optimization.py \
  output/pdf-optimization-20261020/before/X101SC26098749-Z01-J001_report.pdf \
  output/pdf-optimization-20261020/final/X101SC26098749-Z01-J001_report.pdf \
  --config output/pdf-optimization-20261020/config.json \
  --output output/pdf-optimization-20261020/acceptance

python tests/verify_html_browser.py \
  output/pdf-optimization-20261020/final/X101SC26098749-Z01-J001_report.html \
  --output output/pdf-optimization-20261020/html-final-validation
```

- 中文 PDF：`output/pdf-optimization-20261020/final/X101SC26098749-Z01-J001_report.pdf`，**27 → 21 页**。
- 英文 PDF：同目录 `X101SC26098749-Z01-J001_report.en.pdf`，**20 页**。
- 双语交互 HTML：同目录 `X101SC26098749-Z01-J001_report.html`。
- 改前/改后逐页截图及对照：`output/pdf-optimization-20261020/acceptance/`，含摘要、表达矩阵、热图、火山图、覆盖曲线、FastQ Screen 和架构图。
- 自动验收：`acceptance/pdf-optimization-validation.json`；中文版各非章节结尾页的尾部空白均不超过正文区域一半。封面、目录及按 PDF 顶层书签识别的章节结尾页单独标记，未忽略中间页面。
- PCA HTML 验证：`tests/verify_pca_responsive.py` 已验证 390/768/1440/1920 四种宽度下的双向重排、坐标数据不变及高分辨率 PNG 导出；结果在 `output/pca-responsive/verification.json`。
- 输入不变性：81 个输入文件的路径与 SHA256 全部与原报告一致，见 `acceptance/input-invariance.json`。
- 统计与布局验证：`final/content-validation.zh.json`、`final/content-validation.en.json`、`final/pdf-validation.zh.json`、`final/pdf-validation.en.json`；输入/交付哈希验证见 `final/provenance-validation.json`。
- 静态导出回归：`acceptance/static-layout-regression.json` 对覆盖曲线与 FastQ Screen 验证 HTML 间距微调前后的 SVG 坐标轴、子图标题及布局几何一致。
- 单元测试：**217 passed，3 skipped**；跳过项为需显式启用的测试，本次同时执行了上述真实双语 HTML/PDF 渲染与 Chromium 检查。

`verify_pdf_optimization.py` 检查页数、孤儿拆图、尾部留白、来源次数、预览基因及列数、图注口径；火山图引线、50×15 热图行名与架构图字号还通过实际页图人工检查，不以图注文本替代视觉验收。


### 2.3 最终验收结论

A1–A4、B1–B5、C1–C4 全部完成。PDF 自动验收 12 项全部通过；HTML 浏览器验证 26 张可见图表的初始化与尺寸、两张新质控图的图例隐藏/恢复、悬停和缩放、标题/图例互不重叠、双语切换、七个章节导航、ITables 与离线目录跳转全部通过，浏览器错误数为 0。

最终证据索引：

- `output/pdf-optimization-20261020/acceptance/completion-audit.json`
- `output/pdf-optimization-20261020/acceptance/README.md`（七组真实 PDF 页面对照）
- `output/pdf-optimization-20261020/html-final-validation/html-validation.json`
- `output/pdf-optimization-20261020/html-final-validation/fastq-screen.png`
- `output/pdf-optimization-20261020/html-final-validation/coverage.png`
