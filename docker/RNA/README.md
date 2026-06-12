# RNAFlow Report Generator (RNA-seq 数据解读与报告生成系统)

## 📖 项目简介
RNAFlow 是一套基于 **Docker** 和 **Quarto** 构建的自动化 RNA-seq 数据分析报告生成系统。它能够将复杂的转录组分析结果（FASTP、Mapping、DEG、富集分析等）整合，并通过 **AI 解读引擎** 生成深度的实验结论，最终产出交互式的多页 HTML 报告。

本模块的核心改进是引入**统一的 YAML 配置文件** (`report_config.yaml`)：通过一份配置文件即可控制报告标题、Logo、章节、AI 开关、分析参数等，从而在同一套流程上输出不同形态的结果报告。

## ✨ 核心功能
- **统一 YAML 配置**：一份配置驱动报告类型、标题、导航、章节、AI、分析参数等。
- **多报告变体**：同一套数据和代码，可输出完整版、精简版、无 AI 版等不同报告。
- **自动化流程**：一键完成数据整合、AI 解读及网页渲染。
- **AI 智能解读**：利用大语言模型（LLM）对差异基因和富集通路进行生物学功能分析。
- **交互式报告**：基于 Quarto 生成，包含 Plotly 交互图表、Itables 数据表格。
- **Docker 容器化**：环境高度隔离，确保在不同机器上运行结果的一致性。
- **向后兼容**：旧版 `project_summary.json` 仍可运行。

## 🛠️ 环境依赖
- [Docker](https://www.docker.com/) (建议 20.10+)
- [Python 3.8+](https://www.python.org/) (用于本地调试)
- [Quarto](https://quarto.org/) (可选，容器内已集成)

## 🚀 快速上手

### 1. 构建 Docker 镜像
在项目根目录下执行：
```bash
docker build -t rnaflow-report:v1.1 .
```

### 2. 准备配置文件
推荐使用新的 YAML 配置文件。项目已提供三个示例：

| 配置文件 | 说明 |
| :--- | :--- |
| `report_config.yaml` | 完整版报告，包含 Workflow、QC、Results、AI 等全部章节 |
| `report_config.simple.yaml` | 精简版报告，隐藏 Workflow 与 AI 章节 |
| `report_config.no_ai.yaml` | 完整章节，但关闭 AI 解读 |

你可以复制其中一个并根据实际项目修改 `project` 与 `input_files` 部分。

### 3. 运行报告生成
使用 Docker 运行系统（请根据实际路径修改 `-v` 挂载）：

```bash
# 完整版报告
docker run --rm \
  -v /你的/本地/数据目录:/data \
  -v /你的/本地/输出目录:/workspace \
  -v $(pwd)/configs/report_config.yaml:/app/configs/report_config.yaml \
  rnaflow-report:v1.1 -c /app/configs/report_config.yaml -o /workspace

# 精简版报告
docker run --rm \
  -v /你的/本地/数据目录:/data \
  -v /你的/本地/输出目录:/workspace \
  -v $(pwd)/configs/report_config.simple.yaml:/app/configs/report_config.yaml \
  rnaflow-report:v1.1 -c /app/configs/report_config.yaml -o /workspace
```

### 4. 干运行（仅渲染模板，不执行 Quarto）
用于快速检查配置和模板渲染是否正确：
```bash
docker run --rm \
  -v $(pwd)/configs/report_config.yaml:/app/configs/report_config.yaml \
  rnaflow-report:v1.1 -c /app/configs/report_config.yaml -o /workspace --dry-run
```

## 📂 目录结构说明
```text
.
├── entrypoint.py                # 容器入口脚本（薄包装，调用 rnareport.cli.main）
├── rnareport/                   # Python 包：核心逻辑与脚本
│   ├── __init__.py
│   ├── __main__.py              # 支持 python -m rnareport
│   ├── cli.py                   # CLI 解析与主流程编排
│   ├── config.py                # YAML/JSON 统一配置加载 + 项目元数据
│   ├── renderer.py              # Jinja2 模板渲染
│   ├── pipeline.py              # AI 分析流程封装
│   ├── ai/                      # AI 调用引擎
│   │   ├── engine.py
│   │   └── schemas.py
│   ├── plots/                   # 可视化脚本
│   │   ├── plot_utils.py
│   │   ├── pca_plotly.py
│   │   ├── plotly_heatmap.py
│   │   ├── enrichment_plotly.py
│   │   ├── distribution_plotly.py
│   │   └── qc_vis.py
│   └── utils/                   # 工具脚本
│       ├── consolidate_rna_seq_data.py
│       ├── setup_report.py
│       ├── visualize_utils.py
│       ├── report_utils.py
│       └── prompt.txt
├── templates/                   # Quarto 模板、主题与示例数据
│   ├── _quarto.yml.j2           # Quarto 网站配置 Jinja2 模板
│   ├── _quarto.yml              # 运行时由 entrypoint.py 渲染生成
│   ├── data/                    # 示例分析结果数据
│   ├── qmd/                     # Quarto 内容文件 (.qmd)
│   │   ├── _report.qmd.j2
│   │   ├── _report.qmd
│   │   ├── index.qmd
│   │   ├── workflow.qmd
│   │   ├── qc.qmd
│   │   ├── results.qmd
│   │   └── AI.qmd
│   ├── theme/
│   └── logo/
├── configs/                     # 报告配置文件
│   ├── report_config.yaml
│   ├── report_config.simple.yaml
│   └── report_config.no_ai.yaml
├── requirements.txt             # pip 依赖清单
├── requirements.yaml            # conda/mamba 环境说明
├── pyproject.toml               # Python 包配置
├── Dockerfile                   # Docker 构建文件
├── project_summary.json         # 旧版 JSON 配置 (仍兼容)
└── README.md                    # 项目说明文档
```

## 📝 配置文件 (`report_config.yaml`) 关键字段

### `report` — 报告级设置
| 字段 | 说明 |
| :--- | :--- |
| `type` | 报告类型，例如 `rna-seq` |
| `title` | 报告主标题 |
| `subtitle` | 报告副标题 |
| `language` | 报告语言，例如 `zh` / `en` |
| `output_format` | 输出格式，目前为 `html` |
| `sections` | 报告章节列表，控制导航与内容包含 |
| `theme` | Quarto 主题文件路径 |
| `css` | 额外 CSS 文件列表 |
| `logo` | Logo 图片路径 |
| `logo_href` | Logo 点击跳转链接 |
| `announcement` | 顶部公告，设为 `null` 可关闭 |

### `project` — 项目元数据
| 字段 | 说明 |
| :--- | :--- |
| `client` | 客户/课题组名称 |
| `species` | 物种 |
| `genome_version` | 参考基因组版本 |
| `pipeline_version` | 分析流程版本 |
| `analysis_date` | 分析日期 |

### `input_files` — 输入数据路径
| 字段 | 说明 |
| :--- | :--- |
| `data_dir` | 数据根目录 |
| `qc_file` / `mapping_file` / `tpm_file` / `sample_file` | 核心统计与表达文件 |
| `fastp_report_dir` / `fastp_stats_file` | fastp 质控报告 |
| `fastq_screen_r1_dir` / `fastq_screen_r2_dir` | 污染检测报告 |
| `qualimap_dir` | QualiMap / STAR 比对质控 |
| `contrasts_file` / `deg_dir` / `enrichment_dir` | 差异分析与富集结果 |

### `analysis` — 分析参数
| 字段 | 说明 |
| :--- | :--- |
| `deg.log2fc_threshold` | 差异基因 log2FC 阈值 |
| `deg.pvalue_threshold` | 差异基因 P 值阈值 |
| `enrichment.p_cutoff` | 富集显著性阈值 |
| `heatmap.top_n` | 热图展示基因数 |
| `pca.height` / `pca.width` | PCA 图尺寸 |

### `ai` — AI 解读设置
| 字段 | 说明 |
| :--- | :--- |
| `enabled` | 是否启用 AI 解读 |
| `model` / `provider` | 模型与服务商 |
| `temperature` | 模型温度 |
| `prompt_file` | 自定义 Prompt 文件路径 |
| `deg_limit` / `enrichment_limit` | 提交给 AI 的差异基因与通路数量 |

## 🤖 AI 分析流程
在最终生成网页报告前，系统会自动执行以下步骤：
1. **数据整合 (Generate)**：从 `report_config.yaml` 引用的 CSV/TSV 文件中提取 Top 差异基因、富集通路等核心信息，生成 Markdown 格式的中间文件。
2. **AI 解读 (Report)**：将整合后的文本发送给 AI 模型，生成 `consolidated_rna_seq_report.md`。
3. **网页渲染**：Quarto 会将 AI 生成的内容自动嵌入到“AI 解读”章节中。

通过设置 `ai.enabled: false`，可完全跳过 AI 流程并隐藏 AI 章节。

## 🔄 向后兼容
- 若未提供 `/app/configs/report_config.yaml`，系统会依次回退到 `/app/report_config.yaml` 和 `/app/project_summary.json`。
- `rnareport.config.load_config()` 会自动识别 `.yaml` / `.yml` / `.json` 文件，并把旧的 `project_meta` 结构映射到新的 `project` 结构。

## ❓ 常见问题
- **AI 报告没有生成？** 请检查容器是否能够访问外网（AI API 调用需要网络），并确保 `rnareport/ai/` 下的配置正确，且 `ai.enabled` 为 `true`。
- **路径报错？** 确保 `report_config.yaml` 中的路径在 Docker 容器挂载的 `/data` 范围内。
- **报告章节未按配置隐藏？** 请确认 `report.sections` 中已移除该章节，并且重新运行了 `entrypoint.py` 以重新渲染 `_quarto.yml`。

---

**版本**: v1.1.0  
**作者**: Zhang Jian  
**最后更新**: 2026-06-12
