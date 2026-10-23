# HTML 报告展示与固定值排查

范围：中文/英文 HTML `.qmd`、Quarto 模板、共享 CSS、DataTables 渲染入口；同时检查了 PDF 模板中明显遗留的示例数字。未修改上游 CSV、统计计算和分析筛选流程。

## 已修正的固定内容

| 位置 | 原有问题 | 当前行为 |
| --- | --- | --- |
| `omics/rna/qmd/index.qmd`、`en/index.qmd` | 样本说明固定为 6 个样本、Q30 95.9%、GRCm39 | 使用实际统计与 JSON `project.genome_version`（兼容 `project.genome`） |
| 中文 `index.qmd` | Q30 < 80 时详细结论仍写“良好”；固定断言“均衡、无离群” | 使用既有 `qc_status` 统计结果；移除未经计算的样本结论 |
| 中文/英文 `modules/results/deg.qmd` | 图注默认写 P < 0.05、绝对 log2FC > 1 | 使用 `analysis.deg.pvalue_threshold`、`log2fc_threshold` |
| 中文/英文 `modules/results/samples.qmd` | 表达分布筛选阈值只在图中显示，说明未体现配置 | 文案同步显示 `analysis.distribution.threshold` |
| 中文/英文 `modules/results/heatmap.qmd` | 文案断言存在聚类树/明显色块，未说明实际基因数 | 显示图形已有 meta 中的实际基因数、聚类完成状态；解释文本不预设生物学结论 |
| 中文/英文 `workflow.qmd` | 固定声称 fastp 默认参数、STAR two-pass，以及所有高级分析均执行 | 改为工具用途与可选流程介绍；参考基因组读取配置，实际步骤以输入记录为准 |
| `bioreport/software.py` 与 workflow 模板 | fastp/Fastp、FastQ Screen/Fastq Screen 大小写使已提供版本显示“未提供” | 版本显示统一按名称匹配，保留原始软件记录 |
| PDF `modules/results/enrichment.qmd` | 示例分母“上调 1977、下调 2321”容易被误认作当前结果 | 移除示例数，说明分母读取上游结果 |

## 仍固定的计算与展示约定

以下已经定位；遵守“不改统计计算”的约束，本次没有修改算法或增加新的 JSON 字段：

- `bioreport/utils/report_utils.py:get_project_summary_stats`：总数据量按 `Reads_M.sum() * 150 / 1000` 估算，固定假设每条 read 为 **150 bp**。对非 150 bp 或可变读长输入可能不准确，后续应优先读取实际上游碱基总量。
- 同一函数：Q30 质量等级使用 90/80，比对率参考值为 70，唯一比对等级使用 80/60；属于既有评价规则，目前不是 JSON 参数。
- `omics/rna/analysis/pca_plotly.py`、`plotly_heatmap.py`：平均 TPM > 1、log2(TPM+1) 是既有分析口径；热图色阶固定 -2 到 2。表达分布的平均 TPM 阈值、火山图阈值、热图 Top N 已有 JSON 配置。
- QC 图注中的 80%、60%、1% 等为参考说明，不是实测值；不能据此推断本次各样本是否合格。软件运行参数应查看上游日志。
- 流程图仍是固定的常见 RNA-seq 路径示意，已明确标注高级分析可选；图中节点不作为“已执行”的证据。
- Q30 的 Phred 30 定义、TPM 的百万归一化、log2 转换公式等属于指标定义，不应替换为项目元数据。

## 表格问题与对应修改

当前项目为 Python itables/DataTables，没有 R `DT::datatable()`。保留现有引擎与报告结构。

| 用户问题 | 修改位置与行为 |
| --- | --- |
| 1 行距、7 字体 | `templates/theme/itables_saas.css`：统一 6px × 12px、13px、22px 行高，常规行约 34px；继承 body 字体，约束徽标和长基因列表高度 |
| 2 表头断词 | 同文件：表头 nowrap，使用 DataTables 原生横向滚动，不让长表撑开页面 |
| 3 富集列宽 | `bioreport/utils/html_table.py:table_column_defs`：Description 40%，数值列固定像素宽度并右对齐；两个渲染入口均使用 autoWidth=false |
| 4 数字 | 同文件 `NUMBER_RENDER_JS`：baseMean 一位小数；P/padj/p.adjust/qvalue 三位有效数字科学计数；log2FC/lfcSE/stat 三位小数；排序、搜索、复制和 CSV 使用原始数值 |
| 5 横线与交互 | 共享 CSS：无竖线，仅表头上/下及表尾横线；浅条纹 #f8fafc，hover #eef4ff，移除 DataTables 的排序列阴影 |
| 6 工具栏与分页 | 共享 CSS：12px 灰色工具栏，描边按钮、中性深色当前页，包含 DataTables 1/2 的选择器与深色主题 |
| 8 重复列 | `table_column_defs`：只有整列 ENSEMBL/Symbol 非空且完全一致才隐藏 Symbol，复制/CSV 同步排除；真实不同的基因符号保留，原始数据不变 |
| 全局一致 | `render_output.py:show_table`、`html_table.py:show_compact_table` 共用列定义及工具栏参数；`styles.css` 移除冲突旧规则 |

检查了仓库示例的全部 8 个 DEG CSV，ENSEMBL/Symbol 均整列一致；不是仅比较首屏。

## 验证

```bash
python -m pytest -q tests/test_html_table_presentation.py tests/test_html_dynamic_text.py tests/test_html_expression_table.py tests/test_render_output.py tests/test_plotly_download.py tests/test_plotly_runtime.py tests/test_rna_qmd_imports.py tests/test_rna_workflow_svg.py
python scripts/verify_report_tables.py <双语报告.html> --output output/table-review --config <当前配置.json>
```

浏览器验证脚本逐一打开比较组、上下调标签，检查行高、无断词、右对齐、搜索、排序、分页、复制和 CSV 精度。当前受限环境无法启动浏览器，因此实际交互、视觉高度与窄屏表现仍需在可运行 Chromium 的环境中复核。
