# 科研 PDF 报告样式与验证

RNA-seq PDF 使用专用 QMD 内容，HTML 保留原有交互模块。它们共用分析输入和绘图数据；PDF 的排版由 Quarto / Typst 完成，HTML CSS 不参与 PDF 排版。

## 可复用的排版约定

- `templates/pdf/print-style.typ`：共享页眉页码、标题、介绍段、完整图块和跨页表格。正文为 A4 纵向，左右边距 20 mm、上下边距 22 mm，正文 10.5 pt、图注和表格 9 pt；白底、深蓝标题、浅灰表格辅助线。
- `templates/pdf/print-context.typ` 在运行时生成：提供当前项目简称和可用字体。优先 Noto CJK，随后使用已安装的 Droid Sans Fallback / DejaVu Serif；可通过 `report.pdf.fonts` 明确指定字体列表。`print-body.typ` 在 Quarto 文档设置后应用字体回退。
- `templates/pdf/rna-style.typ` 留作 RNA 专用覆盖；`rna-cover.typ.j2` 负责 RNA 封面。封面隐藏页眉页码，主标题固定为“RNA-seq 转录组分析报告”。客户、物种、基因组、流程版本、项目编号、日期、报告版本、运行标识只在配置提供时显示。
- `report-intro(text)` 将介绍段与下一个结果绑定；标题本身采用 sticky 块。图块由 `report-figure(path, caption, ratio)` 统一编号，图片按比例缩放，宽度与正文一致，高度不超过 190 mm。
- 图注、编号、图片由同一个 Typst figure 管理。不要同时配置 QMD `fig-cap`，也不要为每张图手动设置分页符。章节起始分页属于文档结构；密集图在绘图阶段拆分。
- `report-table(headers, rows, numeric)` 按文本／数值分别左／右对齐，允许跨页并重复表头。长标识符在下划线处加入不可见排版断点；原始标识和文件路径保留在输入文件及旁边的来源说明中。
- 目录展示两级标题。独立选择子模块时，用章标题替代重复的小节标题。页眉优先使用 `project.short_name`，其次项目编号或报告标题，并显示该页开始处的章节；页脚使用真实 PDF 页码。
- 未产生引用时隐藏参考文献，实际引用集中在文末。

字体及回退设置参考 [Typst text 文档](https://typst.app/docs/reference/text/text/)。默认字体均从本机已安装的字体中选择；当前验证 PDF 已检查字体嵌入。

## 数据和绘图约定

`bioreport/utils/print_theme.py` 管理分组颜色、字体、静态导出及密集图的拆分。装饰色只用于排版；分组色从完整样本元数据确定，避免缺失某组时其他组变色。QC、PCA、表达分布与热图注释使用同一映射。样本按分组名称和组内元数据顺序展示；热图保留原有聚类顺序，并在图注中说明。

RNA 图表优先从 Plotly 数据重绘为 SVG，不依赖浏览器截图。点、线、文字保持矢量；大热图的色块使用 400 dpi 栅格层，文字、图例仍为矢量。多样本的小提琴图、热图、质控柱状图与曲线按最多 12 个样本拆分，保留全部数据；热图拆分不重新聚类或计算 Z-score。

富集正文默认 Top 12，可配置。按校正后 P 值升序选择，长名称按字符宽度换行，再根据行数预算拆图；同一比较方向的各图共用 P 值色标与 Count 大小比例。类别仅从输入 ID 或 ONTOLOGY 字段读取。图例保留 Gene ratio、Adjusted P value 和 Count。

火山图仍按原始 `pvalue` 与严格的 `log2FoldChange > fc` / `< -fc` 条件着色、计数。绘图沿用原来的 `-log10(P + 1e-300)`，只稳定显示极小值和零值，不改用 padj，也不改写输入文件。表格 P 值从源文件保留文本，再以 Decimal 格式化和排序；因此 `1e-400` 不会因浮点下溢被写成“输入零”。输入确实为零时显示 `0 (输入)`，缺失值显示 `NA`。

摘要仅使用样本表、QC 表、最终 STAR 比对记录和 TPM 矩阵的实际数据。平均值为有效样本算术均值；[0, 1] 比例输入换算为百分比。检出基因为至少一个样本 TPM > 1。每个 contrasts 比较单独统计 DEG，不合并计数，不据此自动判定质控通过。

正文结果使用“目的 → 核心图 → 数据摘要 → 精简表格 → 完整结果路径”。表达矩阵默认 8 行／最多 6 个样本列，差异与富集表默认 Top 10。Gene ID 与 Symbol 根据实际内容区分。

PDF 方法只说明当前模块。正文软件表只列与模块对应的输入版本，完整版本文件保留可追溯信息。DESeq2 的引用要求输入软件记录确实列出它；版本记录不等于本报告重新执行了该工具。缺失必需 DEG 时停止；富集文件缺失或没有满足阈值的条目时明确说明，并提供来源位置。

## 配置和生成

```json
{
  "report": {
    "layout": "single",
    "output_format": "pdf",
    "pdf": {
      "sample_rows": 30,
      "qc_rows": 30,
      "matrix_rows": 8,
      "matrix_columns": 6,
      "deg_rows": 10,
      "enrichment_rows": 10,
      "enrichment_top_n": 12,
      "qc_detail": "key"
    }
  }
}
```

`qc_detail: key` 保留关键曲线、柱状图和汇总表，fastp 曲线默认显示 R1/R2 过滤后数据，STAR 表默认排除 STARpass1。`all` 显示全部保存的曲线与柱状诊断图，包含 reads／过滤阶段及 STAR 阶段记录。上述行数必须为正整数；设置更大的行数允许跨页，不会压缩全表字号。

普通主机使用现有 CLI：

```bash
bioreport run -c tests/report.rna.pdf.json -o output/rna-pdf-report
```

同时输出 HTML 与 PDF 可将 `output_format` 设为 `["html", "pdf"]`。网站模式仍只支持 HTML。

## 受限环境的可复现验证

当前工作环境禁止 Jupyter 内核创建 socket；`bioreport run` 因 `PermissionError: Operation not permitted` 停止。因此增加了测试工具，顺序执行同一份组合 QMD 的真实 Python 单元并捕获显示输出，再用 Quarto `--no-execute` 完成真实排版。它不模拟分析函数，不代替生产 CLI，不执行 AI 调用，仅用于可信仓库模板的验证。

安装 `bioreport[rna,dev]` 和 Quarto；逐页预览另外需要 `pypdf`、`pypdfium2`、Pillow。然后：

```bash
python tests/render_report_inprocess.py -c tests/report.rna.pdf.json -o output/rna-pdf-review --pages
python tests/render_report_inprocess.py -c tests/report.rna.pdf.json -o output/rna-html-review --format html
python tests/create_pdf_stress.py -o output/pdf-stress
python tests/render_report_inprocess.py -c output/pdf-stress/many-samples.json -o output/pdf-stress/many-samples --pages
python tests/render_report_inprocess.py -c output/pdf-stress/full-qc.json -o output/pdf-stress/full-qc --pages
python tests/render_report_inprocess.py -c output/pdf-stress/missing-enrichment.json -o output/pdf-stress/missing-enrichment --pages
pytest -q
```

压力样例复制原有示例数值，构造 36 个重复样本、两个相反比较方向和中英文长标签，只验证布局，不代表独立生物学实验。`missing-deg.json` 预期以缺失 DEG 的错误停止；模块关闭样例应不出现未启用的方法或空参考文献。

验证输出包含 `report.pdf` / `report.html`、Python 单元输出记录 `execution.json`、Quarto 日志 `render.log`。PDF 还包含每页 PNG、联系表、书签页码记录 `review.json`，以及 cover／summary／qc／volcano／enrichment 代表性预览。人工检查后再记录验收结果。

## 本次验收记录

标准示例 `output/rna-pdf-review/report.pdf` 为 16 页，已检查全部页面：标题与首个结果相连，图与图注完整，长表续页重复表头，无图例压到柱状图的情况。`output/rna-pdf-review/verification.json` 记录 A4 尺寸、字体嵌入、20 个书签与正文页码核对、逐页预览数量和实际热图分辨率。封面、摘要、质控、火山图、富集图预览分别为该目录下的 `cover.png`、`summary.png`、`qc.png`、`volcano.png`、`enrichment.png`。

压力报告为 49 页，36 个重复样本、两个比较方向与中英文长名称均已逐页检查。完整 fastp 诊断为 12 页；关闭分析模块为 4 页，无空参考文献或虚构项目字段；缺失富集结果为 5 页，四个比较方向均有明确缺失说明；缺失必需 DEG 以 FileNotFoundError 停止，日志保存于 `output/pdf-stress/missing-deg-check.log`。

真实 HTML 渲染结果位于 `output/rna-html-review/report.html`，核对了六个章节视图、18 个交互图表、内嵌图片及样式、软件和学校 Logo 链接。测试结果为 63 项通过、2 项 Jupyter 集成测试跳过；正常 CLI 在当前 socket 限制下尚不能完成端到端执行，不能将上述受限环境验证等同于生产 CLI 已通过。

## 明确的兼容边界

- 静态小提琴密度由 Matplotlib 重绘，轮廓可能与 Plotly 略有不同；输入的 Log2(TPM+1) 数值、分组和筛选完全相同。
- MultiQC JSON 中直接支持 x/y 曲线和柱状诊断图；general-statistics 的 violin 视图由单独的汇总表承载，不复制网页控件。没有保存 JSON 时使用现有 MultiQC 解析接口，并优先读取其序列化数据集；旧版对象不提供该接口时保留第一数据集的兼容路径。
- 其他自定义 Plotly trace 使用 Kaleido 的 SVG 导出兼容路径，仍需要可运行的浏览器环境。未支持或导出失败会明确报错，不把失败占位当成成功图。
- 字体来自主机，不打包商业字体。没有 CJK 字体的主机应安装 Noto CJK 或通过 `report.pdf.fonts` 指定可嵌入的中文字体。
