# RNAFlow UPDATE 交付 JSON 与 BioReport 接口核对

核对日期：2026-10-20。对象：`examples/X101SC26098749-Z01-J001_UPDATE/`。当前引擎：工作区 BioReport 2.0.1。

结论：**不一致，不能直接把本次 project_summary.json 作为当前报告配置运行。** 核对只新增本文，未修改接口实现或原始交付文件。

## 范围与复现

对照 `bioreport/config.py`、`bioreport/report.schema.json`、`omics/rna/schema.json`、模块 required_inputs、中文/英文 HTML/PDF 富集模板、文件发现函数和 Workspace API 源码，实际运行配置加载、模块选择、CSV/TSV 读取、MultiQC 数据集重建、富集绘图与文件校验。未执行完整 Quarto HTML/PDF 渲染，也未向运行中的 HTTP 服务发送请求。

```sh
python -m bioreport validate -c examples/X101SC26098749-Z01-J001_UPDATE/project_summary.json
```

实际退出码为 1，错误：`project.project_id 必须是非空字符串`。

## 已确认的不一致

| 项目 | 本次交付 | 当前接口行为 | 影响 |
| --- | --- | --- | --- |
| 项目标识 | project_meta.project_name | 旧格式转换只把 project_meta 复制到 project，随后强制要求 project.project_id | 立即拒绝加载；需显式映射 project_name → project_id |
| 路径基准 | path_base 为 .；文件路径已带 data/；data_dir 为 data/index | 旧格式转换丢弃 path_base，所有相对输入路径再拼到 data_dir 下 | 例如 data/index/data/index/multiqc_qc_general_stats.txt；除 data_dir 外的 11 项输入路径均不存在 |
| 版本识别 | schema_version 为 2.0.0 | 旧格式转换未保留或处理该版本字段 | 当前代码没有针对这个上游版本的契约分派 |
| 必需输入 | 未声明 enrichment_dir、software_versions_file | 默认 results 与 workflow 模块分别要求这两项 | 修正项目 ID 和路径后，模块检查仍然拒绝运行 |
| 富集数据入口 | 顶层 enrichment.go/kegg，按 contrasts、UP/DOWN 保存 status/table/full_table/term_count/terms/messages | 旧格式转换不保留顶层 enrichment；模板读取文件路径与 analysis.enrichment 展示参数 | 内嵌结果、状态、参数均未接入 |
| 富集文件名 | 比较组_GO_UP.csv；比较组_KEGG_UP_enrichments.csv 等 | HTML、PDF 按比较组_UP.csv / 比较组_DOWN.csv 查找，或从 files 精确映射 | 已解决：自动发现在旧命名落空后按 `{比较名}_{GO|KEGG}_{UP|DOWN}*.csv` 拆分命名查找，按数据库各生成一条结果（2026-10-24） |
| 软件版本 | 只有各 MultiQC 的 multiqc_software_versions.txt，未提供统一版本 JSON/YAML | load_software_data 只解析 YAML/JSON | 直接把 TSV 填给 software_versions_file 会解析失败；需提供真实流程版本清单 |
| 日期 | project_meta.analysis_date | 封面读取 project.report_date/date，再回退报告生成日期 | 上游分析日期不会自动作为报告日期使用；应明确两种日期语义 |
| 交付清单 | delivery_manifest.json 的 files 是原机器绝对路径 | 配置加载器不会自动导入该独立清单；当前 files 路径需可在本机访问 | 75 项原路径在本机均不存在，按 output_location 迁移到交付根目录后均存在 |

通过临时配置副本逐步验证：只添加 project_id 后，load_config 确实产生重复路径，并且 analysis 只剩默认 enrichment.top_n=12；再将 data_dir 改为交付根目录后，现有输入路径全部存在，但 selected_modules 仍报告缺少 enrichment_dir、software_versions_file。临时副本已由 TemporaryDirectory 清理。

## 统计口径差异

上游 GO/KEGG 参数为 padj_th=0.05、lfc_th=1、cutoff=0.05。当前报告 DEG 统计使用原始 pvalue，而非 padj，analysis.deg.pvalue_threshold 仅控制原始 P 的阈值；默认富集展示 cutoff 为 0.1，且不会继承顶层 enrichment 的 0.05。

以 Salt_A_vs_WTSalt 为例，使用相同 |log2FC|>1 阈值：pvalue<0.05 得到 5154 个，padj<0.05 得到 4620 个。不能把上游 padj_th 简单复制成当前 pvalue_threshold 并宣称统计口径一致。这里验证的是富集输入参数所声明的口径，未据此推断上游全部 DEG 输出只采用一种筛选规则。

stats.total_samples=15、group_count=5 与样本表一致。首页从样本表重新计算 total_groups，group_count 不是本次阻断；旧 AI 汇总仍会读取 group_count。

## 数据兼容性与完整性验证

- 样本表 15 行、5 组，每组 3 个样本；样本 ID 唯一。表达矩阵为 34688 个基因 × 15 个样本，基因 ID 唯一，样本集合与样本表完全一致。
- contrasts.csv 的 Control/Treat 列符合当前读取要求，6 个比较组全部引用已有分组。6 份 DEG 表的文件名和必需统计列符合当前读取逻辑。
- 交付根目录下的所有 input_files 声明目标实际存在，问题出在当前解析基准。
- 4 份 MultiQC JSON 均为 1.31。当前递归定位函数能找到 fastp、R1、R2 多嵌套一层的 JSON；直接重建获得 fastp 14、R1 1、R2 1、QualiMap 9，共 25 个有数据的图表数据集，无异常。额外目录嵌套本身不是兼容阻断。
- 24 个 GO/KEGG × 比较组 × 方向结果中，23 个为 available，1 个为 no_results。23 份非空结果的内嵌 terms 与对应 CSV 内容一致（统一空值表示、容忍浮点精度）；term_count 与实际行数一致，均可直接用当前 dotplot 函数绘图。
- Salt_B_vs_WTSalt 的 KEGG UP 标记 no_results、term_count=0、terms=[]。CSV 一行是 p.adjust=1、Count=0 的 No significant KEGG enrichment 占位记录，不是一个真实富集条目。其 full_table 有非显著结果，不应据 full_table 的行数推翻 no_results 状态。
- delivery_manifest.json 的 75 项在迁移基准后均存在。delivery_manifest.md5 中 72 项普通文件的 MD5 全部匹配，另外 3 项指向目录：未把目录摘要当普通文件摘要验证，也未声称已验证这些目录的聚合 MD5。

## 建议的对接契约

建议保留上游这份分 GO/KEGG 的结果结构，在 BioReport 增加明确的 RNAFlow 2.0.0 导入适配，而不是依赖旧格式通用兼容分支：

1. 明确映射 project_name → project_id；保留 analysis_date，报告生成日期单独处理。保存上游 schema_version 供溯源和版本校验。
2. 对此版本按 JSON 所在目录 + path_base 解析所有交付路径，避免再次拼接 data_dir。若暂时只生成当前格式的配置，可令 data_dir 为 . 并保留 data/... 路径。
3. 上游补充真实的 software_versions_file（当前格式为 Software/Version 记录的 JSON/YAML），并声明 enrichment_dir=data/res/Enrichments。富集结果发现问题已随拆分命名自动发现解决（2026-10-24），剩余缺口是 software_versions_file。
4. 消费 enrichment 下显式的 table/full_table/status，保留 GO/KEGG、比较组、方向三个维度；no_results 用状态表达，不把占位行算作功能条目。不要把 GO 与 KEGG 的两张表任意映射到当前单个比较组_UP.csv 槽位而丢掉其中一类。
5. 显式约定 DEG 显著性列（pvalue 或 padj）、阈值及边界运算；富集展示 cutoff 应与上游声明一致，或在报告中说明差异。
6. 交付清单采用可迁移的相对路径；保留旧机器绝对路径作为来源记录即可。上游清单与 BioReport 自身生成的交付 manifest 是不同契约，不能直接互换。

当前 Workspace HTTP API 管理数据库中已有报告、模块 evidence、解读和对话，未发现接收本次 project_summary.json 的上传/导入端点。上游 schema_version=2.0.0 也不等于 Workspace evidence 的 schema_version=1.0；二者用途不同。本次直接对接的主要检查对象是报告配置加载接口。

## 核心代码依据

- bioreport/config.py:62：旧格式转换；:158：项目 ID；:181：相对路径基准。
- omics/rna/modules.py:10、:16：默认 workflow/results 所需输入。
- omics/rna/qmd/modules/results/enrichment.qmd:15；qmd/pdf/modules/results/enrichment.qmd：富集路径约定。
- bioreport/utils/visualize_utils.py:17：软件版本文件解析。
- bioreport/utils/pdf_results.py:93：DEG 按原始 pvalue 计数。
- omics/rna/analysis/qc_vis.py:23、:89：MultiQC 定位与数据集重建。
- bioreport/api.py、bioreport/ai/evidence.py：Workspace 运行结果与 evidence 契约。
